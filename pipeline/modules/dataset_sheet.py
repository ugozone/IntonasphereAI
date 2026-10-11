"""
IntonaSphere AI - the 28-column dataset sheet
=============================================

Builds the dataset of record with exactly the headings of the released PFC dataset,
in the same order, every value computed by code from the recording, its TextGrid,
the final-domain analysis and the speaker table. A CODEBOOK sheet defines each column.

    TOKEN_ID SPEAKER_ID SITE_ID COUNTRY CONTINENT REGION_GROUP AGE AGE_GROUP SEX GENDER_LABEL
    QUESTION_TYPE SENTENCE_ID SENTENCE_TEXT CONTOUR_CLASS F0_MEAN_ST F0_RANGE_ST FINAL_SLOPE_ST
    FINAL_SYLLABLE_DURATION TOTAL_DURATION INTENSITY_MEAN PLATEAU_DURATION ALIGNMENT_TIME
    SYLLABLE_COUNT SPEECH_RATE_SYLL_PER_SEC AUDIO_FILE TEXTGRID_FILE EXTRACTION_START EXTRACTION_END

Speaker metadata (SITE_ID ... GENDER_LABEL) come from a speaker table (Excel or CSV) with
the columns Speaker code, Site, Country, Region, Sex, Age (names are matched loosely).
AGE_GROUP is NOT copied from that table: it is recomputed from AGE with one rule, the
median split stated in the project's coding rationale (median of all speakers in the table;
a speaker exactly at the median goes to the group set by `age_tie`, default "Older").
"""
from __future__ import annotations

from . import user_path, CSV_ENCODING

import difflib
import re
import unicodedata
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from .final_domain_visualizer import read_textgrid, track_intensity, PFC_QUESTIONS, sentence_id

DATASET_COLUMNS = [
    "TOKEN_ID", "SPEAKER_ID", "SITE_ID", "COUNTRY", "CONTINENT", "REGION_GROUP", "AGE", "AGE_GROUP", "SEX",
    "GENDER_LABEL", "QUESTION_TYPE", "SENTENCE_ID", "SENTENCE_TEXT", "CONTOUR_CLASS", "F0_MEAN_ST",
    "F0_RANGE_ST", "FINAL_SLOPE_ST", "FINAL_SYLLABLE_DURATION", "TOTAL_DURATION", "INTENSITY_MEAN",
    "PLATEAU_DURATION", "ALIGNMENT_TIME", "SYLLABLE_COUNT", "SPEECH_RATE_SYLL_PER_SEC", "AUDIO_FILE",
    "TEXTGRID_FILE", "EXTRACTION_START", "EXTRACTION_END",
]

QUESTION_TYPES = {"1": "polar_inversion", "2": "wh_qu_est_ce_qui", "3": "wh_comment_infinitive", "4": "declarative"}
PLATEAU_BAND_ST = 1.0          # F0 stays within this band (ST) -> plateau
PAUSE_MIN_S = 0.10             # silent intervals at least this long are pauses (excluded from speech rate)
PFC_NAME = re.compile(r"^(.+?)tw([1-4])$", re.I)

CODEBOOK = [
    ("TOKEN_ID", "speaker code + 'tw_Q' + question number (PFC), otherwise the file name", "-", "file name"),
    ("SPEAKER_ID", "PFC speaker code followed by 'tw' (texte lu), as in the released dataset", "-", "file name"),
    ("SITE_ID", "recording site (town) from the speaker table, spelling normalised", "-", "speaker table: Site"),
    ("COUNTRY", "country of the site", "-", "speaker table: Country"),
    ("CONTINENT", "Africa or Europe", "-", "speaker table: Region"),
    ("REGION_GROUP", "region group used for analysis; = CONTINENT unless the speaker table has a 'Region group' column", "-", "speaker table"),
    ("AGE", "age in years at recording", "years", "speaker table: Age"),
    ("AGE_GROUP", "Younger / Older: median split of AGE over all speakers in the speaker table (median and tie rule in PARAMETERS)", "-", "computed from AGE"),
    ("SEX", "F or M (corpus coding)", "-", "speaker table: Sex"),
    ("GENDER_LABEL", "Female / Male (reader-friendly label of SEX)", "-", "computed from SEX"),
    ("QUESTION_TYPE", "Q1 polar question with complex inversion; Q2 wh-question with qu'est-ce qui; Q3 wh-question comment + infinitive; S4 declarative statement (opening sentence of the PFC text, control)", "-", "question number"),
    ("SENTENCE_ID", "Q1, Q2, Q3 (questions) or S4 (statement, declarative control)", "-", "file name"),
    ("SENTENCE_TEXT", "the words actually aligned (word tier of the TextGrid), else the PFC question", "-", "TextGrid / PFC text"),
    ("CONTOUR_CLASS", "rise-fall / fall-rise when F0 turns inside the final syllable (peak or low in the middle 60% of the voiced part, >= 1.5 ST beyond both onset and offset); otherwise rise / fall / plateau from FINAL_SLOPE_ST and the slope threshold (1.5 ST/s)", "-", "final-domain analysis"),
    ("F0_MEAN_ST", "mean F0 over the voiced frames of the utterance (EXTRACTION_START to _END), semitones re 100 Hz", "ST re 100 Hz", "Praat pitch"),
    ("F0_RANGE_ST", "F0 range of the utterance: 95th minus 5th percentile of the voiced frames (robust to tracking errors)", "ST", "Praat pitch"),
    ("FINAL_SLOPE_ST", "least-squares slope of F0 (semitones) over the voiced frames of the final syllable", "ST/s", "final-domain analysis"),
    ("FINAL_SYLLABLE_DURATION", "duration of the final syllable (WebMAUS MAS tier, or automatic segmentation)", "s", "final-domain analysis"),
    ("TOTAL_DURATION", "utterance duration: start of first word to end of last word (internal pauses included)", "s", "TextGrid"),
    ("INTENSITY_MEAN", "mean intensity over the utterance (energy average, as Praat 'Get mean')", "dB", "Praat intensity"),
    ("PLATEAU_DURATION", f"longest stretch of consecutive voiced frames in the final syllable whose F0 stays within {PLATEAU_BAND_ST} ST", "s", "final-domain analysis"),
    ("ALIGNMENT_TIME", "time of the F0 peak in the final syllable, measured from the syllable onset", "s", "final-domain analysis"),
    ("SYLLABLE_COUNT", "syllables in the utterance (WebMAUS MAS tier; vowel-less pieces merged into their neighbour), else automatic nuclei", "count", "TextGrid"),
    ("SPEECH_RATE_SYLL_PER_SEC", f"articulation rate: SYLLABLE_COUNT / (TOTAL_DURATION - silent pauses >= {PAUSE_MIN_S} s)", "syll/s", "TextGrid"),
    ("AUDIO_FILE", "the WAV file", "-", "-"),
    ("TEXTGRID_FILE", "the TextGrid used (yours, or made by WebMAUS); empty = automatic segmentation", "-", "-"),
    ("EXTRACTION_START", "start of the analysed span (first word)", "s", "TextGrid"),
    ("EXTRACTION_END", "end of the analysed span (last word)", "s", "TextGrid"),
]


# ---------------------------------------------------------------------------
# Speaker table
# ---------------------------------------------------------------------------
def _key(s: str) -> str:
    s = unicodedata.normalize("NFD", str(s).strip().lower())
    return "".join(ch for ch in s if unicodedata.category(ch) != "Mn")


def _find_col(df: pd.DataFrame, *names: str) -> Optional[str]:
    lk = {_key(c).replace(" ", "").replace("_", ""): c for c in df.columns}
    for n in names:
        k = _key(n).replace(" ", "").replace("_", "")
        if k in lk:
            return lk[k]
    return None


def load_speakers(path: Path, age_tie: str = "Older", fixes: Optional[Dict[str, str]] = None,
                  sheet_name: Optional[str] = None) -> Tuple[pd.DataFrame, Dict]:
    """Read and normalise the speaker table. Returns (table indexed by code, info).
    fixes: corrections of speaker codes in the table, e.g. {"81acc1": "81aac1"}."""
    path = Path(path)
    if path.suffix.lower() in (".xlsx", ".xls"):
        xl = pd.ExcelFile(path)
        best, df, sheet = None, None, ""
        for s in ([sheet_name] if sheet_name else xl.sheet_names):
            d = xl.parse(s)
            if not _find_col(d, "Age"):
                continue
            # prefer a real speaker table: a 'Speaker code' column, one row per speaker, most rows
            score = (2 if _find_col(d, "Speaker code", "speaker_code") else
                     1 if _find_col(d, "speaker", "code", "speaker_id") else 0,
                     0 if _find_col(d, "TOKEN_ID") else 1, len(d))
            if score[0] and (best is None or score > best):
                best, df, sheet = score, d, s
        if df is None:
            raise ValueError(f"no sheet with a speaker-code and an Age column in {path.name}")
    else:
        df = None
        for enc in (CSV_ENCODING, "cp1252", "latin-1"):     # Excel on Windows saves CSV as cp1252
            try:
                df = pd.read_csv(path, encoding=enc); break
            except UnicodeDecodeError:
                continue
        sheet = ""
    c_code = _find_col(df, "Speaker code", "speaker_code", "speaker", "code", "speaker_id")
    df = df[df[c_code].notna() & (df[c_code].astype(str).str.strip() != "")].reset_index(drop=True)
    c = {k: _find_col(df, *v) for k, v in {
        "site": ("Site", "town", "site_id"), "country": ("Country",), "region": ("Region", "continent"),
        "group": ("Region group", "region_group"), "sex": ("Sex", "gender"), "age": ("Age",),
        "agegroup": ("Age group", "age_group")}.items()}
    out = pd.DataFrame({"CODE": df[c_code].astype(str).str.strip().str.lower()})
    fixes = {k.strip().lower(): v.strip().lower() for k, v in (fixes or {}).items()}
    out["CODE_IN_TABLE"] = out["CODE"]
    out["CODE"] = out["CODE"].map(lambda c: fixes.get(c, c))
    # site / country spelling: use the most frequent spelling among case/accent variants
    for col, src in (("SITE_ID", "site"), ("COUNTRY", "country"), ("CONTINENT", "region")):
        vals = df[c[src]].astype(str).str.strip() if c[src] else pd.Series([""] * len(df))
        canon = {}
        for v in vals:
            canon.setdefault(_key(v), []).append(v)
        best = {k: max(set(vs), key=lambda x: (vs.count(x), x[:1].isupper(), any(ord(ch) > 127 for ch in x)))
                for k, vs in canon.items()}
        out[col] = [best[_key(v)] for v in vals]
    out["REGION_GROUP"] = df[c["group"]].astype(str).str.strip() if c["group"] else out["CONTINENT"]
    out["AGE"] = pd.to_numeric(df[c["age"]], errors="coerce")
    sex = df[c["sex"]].astype(str).str.strip().str.upper().str[0] if c["sex"] else ""
    out["SEX"] = sex
    out["GENDER_LABEL"] = out["SEX"].map({"F": "Female", "M": "Male"}).fillna("")
    median = float(np.nanmedian(out["AGE"]))
    tie_older = age_tie.lower().startswith("o")
    older = (out["AGE"] > median) | ((out["AGE"] == median) & tie_older)
    out["AGE_GROUP"] = np.where(out["AGE"].isna(), "", np.where(older, "Older", "Younger"))
    if c["agegroup"]:
        orig = df[c["agegroup"]].astype(str).str.strip().str.capitalize()
        out["AGE_GROUP_IN_TABLE"] = orig
        out["AGE_GROUP_CHANGED"] = orig != out["AGE_GROUP"]
    dup = out["CODE"][out["CODE"].duplicated()].tolist()
    info = {"file": path.name, "sheet": sheet, "speakers": len(out), "median_age": median,
            "age_rule": f"Older if AGE > {median:g}, or = {median:g} ({'Older' if tie_older else 'Younger'}); else Younger",
            "duplicates": dup, "code_fixes": {k: v for k, v in fixes.items()}}
    return out.drop_duplicates("CODE").set_index("CODE"), info


# ---------------------------------------------------------------------------
# One token
# ---------------------------------------------------------------------------
def speaker_code(stem: str) -> Tuple[str, str]:
    m = PFC_NAME.match(re.sub(r"\s+copy$", "", stem, flags=re.I))
    return (m.group(1).lower(), m.group(2)) if m else (stem.lower(), "")


def _intervals(tg, names):
    for n in names:
        for t in tg.tiers:
            if t.name == n and t.kind == "interval":
                return t.intervals
    return None


def _is_pause(lab: str) -> bool:
    l = (lab or "").strip().lower()
    return l == "" or l.startswith("<p") or l in {"sil", "#", "<usb>", "_"}


def utterance_measures(wav_x, sr, pitch, textgrid: Optional[Path], fd: Dict, stem: str) -> Dict:
    """Utterance-level values for the dataset sheet (see CODEBOOK)."""
    t_f0, f0, rng = pitch
    res: Dict = {}
    dur = len(wav_x) / sr
    start, end, words, n_syl, pauses = 0.0, dur, [], None, []
    if textgrid is not None:
        tg = read_textgrid(textgrid)
        key = re.sub(r"[^a-z0-9]", "", stem.lower())
        wt = _intervals(tg, ["ORT-MAU", "words", "word", "ORT", "mots"]) or []
        words = [iv for iv in wt if not _is_pause(iv.label) and re.sub(r"[^a-z0-9]", "", iv.label.lower()) != key]
        if words:
            start, end = words[0].start, words[-1].end
        st = _intervals(tg, ["MAS", "syllabe", "syllable", "sylable", "syllables"])
        if st is not None:
            try:                                   # same syllable units as the F_ToBI step
                from .ftobi_annotator import build_units
                _, syls, _ = build_units(tg, stem, [])
                n_syl = len([s for s in syls if start - 1e-6 <= s.start and s.end <= end + 1e-6])
            except Exception:
                n_syl = len([iv for iv in st if not _is_pause(iv.label)])
            pauses = [(iv.start, iv.end) for iv in st if _is_pause(iv.label)
                      and iv.start >= start - 1e-6 and iv.end <= end + 1e-6]
        for a, b in zip(words[:-1], words[1:]):        # gaps between words count as pauses too
            if b.start - a.end > 1e-3:
                pauses.append((a.end, b.start))
    else:
        n_syl = fd.get("AUTO_SYLLABLE_COUNT")
    # merge overlapping pauses, keep those >= PAUSE_MIN_S
    pauses = sorted(pauses)
    merged: List[List[float]] = []
    for a, b in pauses:
        if merged and a <= merged[-1][1] + 1e-6:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    pause_time = sum(b - a for a, b in merged if b - a >= PAUSE_MIN_S)

    res["SENTENCE_TEXT"] = " ".join(w.label.strip() for w in words) if words else ""
    res["EXTRACTION_START"], res["EXTRACTION_END"] = round(start, 4), round(end, 4)
    res["TOTAL_DURATION"] = round(end - start, 4)
    res["SYLLABLE_COUNT"] = int(n_syl) if n_syl is not None and n_syl == n_syl else None
    speech = (end - start) - pause_time
    res["SPEECH_RATE_SYLL_PER_SEC"] = round(res["SYLLABLE_COUNT"] / speech, 3) \
        if res["SYLLABLE_COUNT"] and speech > 0 else None
    m = (t_f0 >= start) & (t_f0 <= end) & ~np.isnan(f0)
    if m.sum() >= 3:
        s = 12 * np.log2(f0[m] / 100.0)
        res["F0_MEAN_ST"] = round(float(np.mean(s)), 3)
        res["F0_RANGE_ST"] = round(float(np.percentile(s, 95) - np.percentile(s, 5)), 3)
    t_int, db = track_intensity(wav_x, sr, min_pitch=max(rng[0], 50.0))
    im = (t_int >= start) & (t_int <= end)
    res["INTENSITY_MEAN"] = round(float(10 * np.log10(np.mean(10 ** (db[im] / 10)))), 3) if im.any() else None
    # plateau inside the final syllable
    a, b = fd.get("FINAL_SYLLABLE_START"), fd.get("FINAL_SYLLABLE_END")
    res["PLATEAU_DURATION"] = None
    if a is not None and b is not None and a == a:
        fm = (t_f0 >= a) & (t_f0 <= b)
        vals = 12 * np.log2(np.where(np.isnan(f0[fm]), np.nan, f0[fm]) / 100.0)
        best, i = 0, 0
        while i < len(vals):
            if np.isnan(vals[i]):
                i += 1; continue
            lo = hi = vals[i]; j = i
            while j + 1 < len(vals) and not np.isnan(vals[j + 1]) and \
                    max(hi, vals[j + 1]) - min(lo, vals[j + 1]) <= PLATEAU_BAND_ST:
                j += 1; lo, hi = min(lo, vals[j]), max(hi, vals[j])
            best = max(best, j - i + 1)
            i += 1
        step = float(t_f0[1] - t_f0[0]) if len(t_f0) > 1 else 0.01
        res["PLATEAU_DURATION"] = round(best * step, 3) if best >= 2 else 0.0
    return res


def dataset_row(wav: Path, textgrid: Optional[Path], wav_x, sr, pitch, fd: Dict,
                speakers: Optional[pd.DataFrame]) -> Tuple[Dict, List[str]]:
    """One row with exactly DATASET_COLUMNS, plus a list of warnings."""
    warn: List[str] = []
    code, q = speaker_code(wav.stem)
    row = {c: None for c in DATASET_COLUMNS}
    row["TOKEN_ID"] = f"{code}tw_{sentence_id(q)}" if q else wav.stem
    row["SPEAKER_ID"] = f"{code}tw" if q else code
    row["SENTENCE_ID"] = sentence_id(q)
    row["QUESTION_TYPE"] = QUESTION_TYPES.get(q, "")
    if speakers is not None:
        if code in speakers.index:
            sp = speakers.loc[code]
            for col in ("SITE_ID", "COUNTRY", "CONTINENT", "REGION_GROUP", "AGE", "AGE_GROUP", "SEX", "GENDER_LABEL"):
                v = sp[col]
                row[col] = int(v) if col == "AGE" and v == v else v
        else:
            close = difflib.get_close_matches(code, list(speakers.index), n=1, cutoff=0.6)
            warn.append(f"speaker '{code}' not in the speaker table" + (f" (did you mean '{close[0]}'?)" if close else ""))
    try:
        um = utterance_measures(wav_x, sr, pitch, textgrid, fd, wav.stem)
    except Exception as e:
        um = {}
        warn.append(f"utterance measures failed: {e}")
    row.update({k: v for k, v in um.items() if k in row})
    if not row["SENTENCE_TEXT"] and q:
        row["SENTENCE_TEXT"] = PFC_QUESTIONS.get(q, "")
    for k_out, k_in in (("CONTOUR_CLASS", "CONTOUR_CLASS"), ("FINAL_SLOPE_ST", "FINAL_SLOPE_ST"),
                        ("FINAL_SYLLABLE_DURATION", "FINAL_SYLLABLE_DURATION"), ("ALIGNMENT_TIME", "PEAK_ALIGNMENT_S")):
        v = fd.get(k_in)
        row[k_out] = round(float(v), 4) if isinstance(v, (int, float, np.floating)) and v == v else v
    row["AUDIO_FILE"] = wav.name
    row["TEXTGRID_FILE"] = textgrid.name if textgrid else ""
    return row, warn


def codebook_df() -> pd.DataFrame:
    return pd.DataFrame(CODEBOOK, columns=["COLUMN", "DEFINITION", "UNIT", "SOURCE"])
