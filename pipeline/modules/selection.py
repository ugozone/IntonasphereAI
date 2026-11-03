"""
IntonaSphere AI - token selection (quality control)
===================================================

Turns the measurements of one run into a keep / exclude decision for every token, with the
reason, following the quality-control rules of the dissertation methodology (Chapter 3):

Exclusion (a token is excluded only for a technical reason, never because of its value)
  (a) no F0 can be measured in the final syllable, so no terminal movement exists;
  (b) the file contains more than the target sentence: detected when the articulation rate
      falls below MIN_ARTICULATION_RATE syllables per second, and CONFIRMED BY LISTENING
      (the automatic decision is "Check by listening"; record the result in the overrides file);
  (c) the reader does not produce the target sentence: the final word group is missing, or it
      is repeated or contains a hesitation or self-repair, because the nuclear configuration
      that is analysed is realised on exactly that stretch of speech.
Flags (the token is kept, and marked FLAGGED = yes for the sensitivity analysis)
  - F0 on less than half of the final vowel             (QC_FINAL_VOWEL_LOW_F0)
  - an F0 jump of 7 semitones or more in the final syllable  (QC_OCTAVE_JUMP)
  - a final syllable longer than LONG_FINAL_SYLLABLE_S
  - disagreement between the contour class and the proposed boundary tone
Other decisions
  - Repair, then reassess   no alignment, or the final-domain analysis failed
  - Pending - no data       a planned speaker x sentence (from the speaker table) with no recording
  - Pending - metadata      the speaker is not in the speaker table

Hesitations and repetitions EARLIER in the sentence do not lead to exclusion (they are noted).
The transcript check relies on the word tier of the TextGrid: it can only find a hesitation
that is in the transcription, so TextGrids made by WebMAUS from the PFC text are noted as such.

Manual decisions live in an overrides file (CSV) that is read on every run and never
overwritten, so decisions survive re-runs:
    TOKEN_ID, CHECKED (yes/no), MANUAL_DECISION, MANUAL_NOTE
MANUAL_DECISION: Include / Exclude, or e.g. "Not available" for an S4 that does not exist;
blank keeps the automatic decision.

Used automatically by modules.run_all (sheets SELECTION, TOKEN_FLOW, TOKEN_FLOW_BY_SITE), and
on its own, without re-measuring anything, after you have edited the overrides file:

    python -m modules.selection --results outputs/intonasphere_results.xlsx
    python -m modules.selection --results outputs/intonasphere_results.xlsx --overrides my_decisions.csv
"""
from __future__ import annotations

from . import user_path, CSV_ENCODING
from .i18n import t as tr, add_lang_option

import argparse
import re
import unicodedata
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

# --------------------------------------------------------------------------- settings
MIN_ARTICULATION_RATE = 2.0      # syll/s; below this the file may contain more than the sentence
LONG_FINAL_SYLLABLE_S = 0.600    # final syllable longer than this is flagged
LOW_F0_COVERAGE = 0.5            # share of the final vowel with F0 (computed by the final-domain step)
FINAL_WORD_GROUPS = {            # where the nuclear configuration is realised
    "Q1": "à Beaulieu", "Q2": "grand honneur", "Q3": "visites officielles", "S4": "grand émoi"}
QUESTIONS = ("Q1", "Q2", "Q3")
STATEMENT = "S4"
SENTENCES = QUESTIONS + (STATEMENT,)
FILLERS = {"euh", "heu", "hum", "hm", "ben", "bah", "eh"}

INCLUDE, EXCLUDE, CHECK, REPAIR = "Include", "Exclude", "Check by listening", "Repair, then reassess"
PENDING_DATA, PENDING_META = "Pending – no data", "Pending – metadata"
DECISION_ORDER = [INCLUDE, CHECK, REPAIR, EXCLUDE, PENDING_DATA, PENDING_META]
OVERRIDE_COLUMNS = ["TOKEN_ID", "CHECKED", "MANUAL_DECISION", "MANUAL_NOTE"]

SELECTION_COLUMNS = [
    "TOKEN_ID", "SPEAKER_ID", "SITE_ID", "CONTINENT", "AGE", "AGE_GROUP", "SEX", "SENTENCE_ID",
    "SENTENCE_TEXT", "TRANSCRIPT_SOURCE", "SPEECH_RATE_SYLL_PER_SEC", "FINAL_SYLLABLE_DURATION",
    "FINAL_VOWEL_F0_COVERAGE", "QC_OCTAVE_JUMP", "CONTOUR_VS_BOUNDARY_TONE",
    "EXCLUSION_CHECKS", "FLAGS", "FLAGGED", "NOTES", "AUTO_DECISION", "AUTO_REASON",
    "CHECKED", "MANUAL_DECISION", "MANUAL_NOTE", "SELECTION_DECISION",
    "COMPLETE_CASE_SET", "RQ4_SET", "AUDIO_FILE",
]
SELECTION_PARAMETERS = [
    ("selection", "exclusion (a)", "no F0 in the final syllable"),
    ("selection", "exclusion (b)", f"articulation rate < {MIN_ARTICULATION_RATE} syll/s -> 'Check by listening'; "
                                   "confirm Exclude in the overrides file"),
    ("selection", "exclusion (c)", "final word group missing, repeated, or with a hesitation/self-repair: "
                                   + ", ".join(f"{k} '{v}'" for k, v in FINAL_WORD_GROUPS.items())),
    ("selection", "flags (token kept)", f"final-vowel F0 coverage < {LOW_F0_COVERAGE}; F0 jump >= 7 ST; "
                                        f"final syllable > {LONG_FINAL_SYLLABLE_S} s; contour class vs boundary tone"),
    ("selection", "hesitation words", ", ".join(sorted(FILLERS))),
]


# --------------------------------------------------------------------------- transcript check
def norm_words(text) -> List[str]:
    """Lower-case, accents and punctuation removed, hyphens and elisions split."""
    if not isinstance(text, str):
        return []
    t = unicodedata.normalize("NFKD", text.lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = re.sub(r"[’'\-]", " ", t)
    t = re.sub(r"<[^>]*>", " ", t)                 # WebMAUS / Praat markers such as <p:>
    t = re.sub(r"[^a-z0-9 ]", " ", t)
    return t.split()


def _find_all(words: List[str], seq: List[str]) -> List[int]:
    n = len(seq)
    return [i for i in range(len(words) - n + 1) if words[i:i + n] == seq]


def _repeated_bigrams(words: List[str]) -> set:
    seen, rep = set(), set()
    for bg in zip(words, words[1:]):
        (rep if bg in seen else seen).add(bg)
    return rep


def check_final_group(text, sentence: str) -> Tuple[Optional[bool], List[str], List[str]]:
    """(final group intact?, exclusion reasons, notes). None if the sentence is unknown."""
    group = FINAL_WORD_GROUPS.get(sentence)
    if group is None:
        return None, [], []
    words = norm_words(text)
    if not words:
        return False, ["no transcript"], []
    final = norm_words(group)
    k = len(final)
    occ = _find_all(words, final)
    tail = words[-(k + 3):]                          # the final group and the three words before it
    rep = _repeated_bigrams(words)
    excl, notes = [], []
    if words[-k:] != final:
        excl.append(f"final word group '{group}' missing or incomplete")
    if len(occ) > 1:
        excl.append(f"final word group '{group}' repeated")
    if any(bg in rep for bg in zip(tail, tail[1:])) or any(w in FILLERS for w in tail):
        excl.append("hesitation or self-repair in the final word group")
    if not excl and (any(w in FILLERS for w in words) or rep):
        notes.append("hesitation or repetition earlier in the sentence (kept: final word group intact)")
    return not excl, excl, notes


# --------------------------------------------------------------------------- decisions
def _num(v) -> Optional[float]:
    try:
        f = float(v)
        return None if np.isnan(f) else f
    except (TypeError, ValueError):
        return None


def _blank(v) -> bool:
    """Empty cell, whether it came from the run itself or was read back from Excel/CSV."""
    return v is None or (isinstance(v, float) and np.isnan(v)) or str(v).strip() in ("", "nan", "None", "NaN")


def _true(v) -> bool:
    return str(v).strip().lower() in ("true", "1", "yes")


def decide(r: Dict, have_speakers: bool) -> Tuple[str, str, List[str], List[str], List[str]]:
    """Automatic decision for one measured token: (decision, reason, exclusion checks, flags, notes)."""
    excl: List[str] = []
    flags: List[str] = []
    notes: List[str] = []
    sent = str(r.get("SENTENCE_ID") or "")
    if have_speakers and _blank(r.get("SITE_ID")):
        return PENDING_META, "speaker not in the speaker table (correct the code with --speaker-fix)", [], [], []
    status = "" if _blank(r.get("FINAL_DOMAIN_STATUS")) else str(r.get("FINAL_DOMAIN_STATUS")).strip()
    if _blank(r.get("TEXTGRID_FILE")):
        return REPAIR, "no alignment (TextGrid): align the recording, then run again", [], [], []
    if status not in ("completed", "no_voiced_f0_in_final_syllable"):
        return REPAIR, f"final-domain analysis did not complete ({status or 'not run'})", [], [], []
    # (a) no F0 in the final syllable
    if status == "no_voiced_f0_in_final_syllable":
        excl.append("(a) no F0 in the final syllable")
    # (c) target sentence not produced / final word group affected (PFC sentences only)
    if sent in SENTENCES:
        ok, why, n = check_final_group(r.get("SENTENCE_TEXT"), sent)
        excl += [f"(c) {w}" for w in why]
        notes += n
    else:
        notes.append("not a PFC target sentence: final-word-group check (c) not applied")
    if excl:
        return EXCLUDE, "; ".join(excl), excl, flags, notes
    # (b) file may contain more than the sentence: confirm by listening
    rate = _num(r.get("SPEECH_RATE_SYLL_PER_SEC"))
    check_b = rate is not None and rate < MIN_ARTICULATION_RATE
    # flags (token kept)
    cov = _num(r.get("FINAL_VOWEL_F0_COVERAGE"))
    if _true(r.get("QC_FINAL_VOWEL_LOW_F0")) or (cov is not None and cov < LOW_F0_COVERAGE):
        flags.append("F0 on less than half of the final vowel")
    if _true(r.get("QC_OCTAVE_JUMP")):
        flags.append("F0 jump of 7 ST or more in the final syllable")
    dur = _num(r.get("FINAL_SYLLABLE_DURATION"))
    if dur is not None and dur > LONG_FINAL_SYLLABLE_S:
        flags.append(f"final syllable longer than {LONG_FINAL_SYLLABLE_S * 1000:.0f} ms")
    if not _blank(r.get("CONTOUR_VS_BOUNDARY_TONE")) and "check" in str(r.get("CONTOUR_VS_BOUNDARY_TONE")):
        flags.append("contour class and proposed boundary tone disagree")
    if check_b:
        return CHECK, (f"(b) articulation rate {rate:.2f} syll/s < {MIN_ARTICULATION_RATE}: the file may contain "
                       "more than the sentence; listen, then record Include or Exclude"), excl, flags, notes
    if flags:
        return INCLUDE, "kept, flagged: " + "; ".join(flags), excl, flags, notes
    return INCLUDE, "meets all criteria" + (" (" + notes[0] + ")" if notes else ""), excl, flags, notes


def _transcript_source(r: Dict) -> str:
    src = str(r.get("ALIGNMENT_SOURCE") or "")
    text = str(r.get("TEXT_SOURCE") or "")
    if src == "user_textgrid":
        return "your TextGrid"
    if src.startswith("webmaus") or "webmaus" in src.lower():
        return f"WebMAUS from {text or 'text'}" + (" (hesitations not transcribed)" if "pfc" in text.lower() else "")
    return src or ""


def read_overrides(path: Optional[Path]) -> pd.DataFrame:
    if not path or not Path(path).exists():
        return pd.DataFrame(columns=OVERRIDE_COLUMNS).set_index("TOKEN_ID")
    ov = pd.read_csv(path, dtype=str, encoding=CSV_ENCODING).fillna("")
    ov.columns = [c.strip().upper() for c in ov.columns]
    for c in OVERRIDE_COLUMNS:
        if c not in ov.columns:
            ov[c] = ""
    return ov.drop_duplicates("TOKEN_ID", keep="last").set_index("TOKEN_ID")


def select(dataset: pd.DataFrame, all_tokens: Optional[pd.DataFrame] = None,
           speakers: Optional[pd.DataFrame] = None, overrides: Optional[pd.DataFrame] = None,
           plan_s4: bool = True) -> pd.DataFrame:
    """One SELECTION row per token (and per planned speaker x sentence without a recording)."""
    ds = dataset.copy()
    if all_tokens is not None and len(all_tokens):
        keep = [c for c in ("AUDIO_FILE", "ALIGNMENT_SOURCE", "TEXT_SOURCE", "FINAL_DOMAIN_STATUS",
                            "FINAL_VOWEL_F0_COVERAGE", "QC_FINAL_VOWEL_LOW_F0", "QC_OCTAVE_JUMP",
                            "CONTOUR_VS_BOUNDARY_TONE") if c in all_tokens.columns]
        ds = ds.merge(all_tokens[keep].drop_duplicates("AUDIO_FILE"), on="AUDIO_FILE", how="left")
    have_sp = speakers is not None and len(speakers) > 0
    rows = []
    for _, r in ds.iterrows():
        r = r.to_dict()
        dec, why, excl, flags, notes = decide(r, have_sp)
        r.update(AUTO_DECISION=dec, AUTO_REASON=why, EXCLUSION_CHECKS="; ".join(excl),
                 FLAGS="; ".join(flags), FLAGGED="yes" if flags else "no", NOTES="; ".join(notes),
                 TRANSCRIPT_SOURCE=_transcript_source(r))
        rows.append(r)
    # planned speaker x sentence without a recording
    if have_sp:
        have = {(str(r.get("SPEAKER_ID") or "").lower().removesuffix("tw"), r.get("SENTENCE_ID")) for r in rows}
        planned = QUESTIONS + ((STATEMENT,) if plan_s4 else ())
        for code, sp in speakers.iterrows():
            for s in planned:
                if (str(code).lower(), s) in have:
                    continue
                rows.append({"TOKEN_ID": f"{code}tw_{s}", "SPEAKER_ID": f"{code}tw", "SENTENCE_ID": s,
                             **{c: sp.get(c) for c in ("SITE_ID", "CONTINENT", "AGE", "AGE_GROUP", "SEX")},
                             "AUTO_DECISION": PENDING_DATA, "FLAGGED": "no",
                             "AUTO_REASON": "no recording of this sentence in the folder "
                                            "(record 'Not available' if the speaker has none)"})
    sel = pd.DataFrame(rows)
    for c in SELECTION_COLUMNS:
        if c not in sel.columns:
            sel[c] = None
    # manual decisions
    ov = overrides if overrides is not None else read_overrides(None)
    sel["CHECKED"] = sel["TOKEN_ID"].map(ov["CHECKED"]).fillna("").replace("", "no")
    sel["MANUAL_DECISION"] = sel["TOKEN_ID"].map(ov["MANUAL_DECISION"]).fillna("")
    sel["MANUAL_NOTE"] = sel["TOKEN_ID"].map(ov["MANUAL_NOTE"]).fillna("")
    sel["SELECTION_DECISION"] = np.where(sel["MANUAL_DECISION"].str.strip() != "",
                                         sel["MANUAL_DECISION"].str.strip(), sel["AUTO_DECISION"])
    # analysis sets
    code = sel["SPEAKER_ID"].astype(str).str.lower().str.replace(r"tw$", "", regex=True)
    inc = sel["SELECTION_DECISION"].eq(INCLUDE)
    n_q = sel[inc & sel["SENTENCE_ID"].isin(QUESTIONS)].groupby(code[inc]).size()
    has_s4 = set(code[inc & sel["SENTENCE_ID"].eq(STATEMENT)])
    sel["COMPLETE_CASE_SET"] = code.map(lambda c: "yes" if n_q.get(c, 0) == len(QUESTIONS) else "no")
    sel["RQ4_SET"] = code.map(lambda c: "yes" if c in has_s4 and n_q.get(c, 0) > 0 else "no")
    order = {s: i for i, s in enumerate(SENTENCES)}
    sel = sel.assign(_o=sel["SENTENCE_ID"].map(order).fillna(9)) \
             .sort_values(["CONTINENT", "SITE_ID", "SPEAKER_ID", "_o"], na_position="last").drop(columns="_o")
    return sel[SELECTION_COLUMNS].reset_index(drop=True)


# --------------------------------------------------------------------------- summaries
def token_flow(sel: pd.DataFrame) -> pd.DataFrame:
    """Decisions by sentence (Q1, Q2, Q3, S4 and all), plus the analysis sets."""
    sents = [s for s in SENTENCES if s in set(sel["SENTENCE_ID"])]
    def row(label, mask):
        return [label, int(mask.sum())] + [int((mask & sel["SENTENCE_ID"].eq(s)).sum()) for s in sents]
    dec = sel["SELECTION_DECISION"]
    rows = [row("Tokens (recorded or planned)", pd.Series(True, index=sel.index))]
    for d in DECISION_ORDER + sorted(set(dec) - set(DECISION_ORDER)):
        if (dec == d).any() or d in (INCLUDE, EXCLUDE):
            rows.append(row(d, dec == d))
    rows.append(row("  of which included and flagged", dec.eq(INCLUDE) & sel["FLAGGED"].eq("yes")))
    out = pd.DataFrame(rows, columns=["STEP", "ALL"] + sents)
    inc = dec.eq(INCLUDE)
    extra = pd.DataFrame([
        ["Speakers with at least one included token", sel.loc[inc, "SPEAKER_ID"].nunique()],
        ["Speakers in the complete-case set (Q1-Q3 all included)",
         sel.loc[sel["COMPLETE_CASE_SET"].eq("yes"), "SPEAKER_ID"].nunique()],
        ["Speakers in the RQ4 set (S4 and at least one question included)",
         sel.loc[sel["RQ4_SET"].eq("yes"), "SPEAKER_ID"].nunique()]], columns=["STEP", "ALL"])
    return pd.concat([out, extra], ignore_index=True).astype({c: "Int64" for c in ["ALL"] + sents})


def token_flow_by_site(sel: pd.DataFrame) -> pd.DataFrame:
    """Included, flagged, excluded and pending tokens by site and sentence."""
    s = sel.copy()
    s["SITE_ID"] = s["SITE_ID"].fillna("(not in speaker table)")
    s["DECISION"] = np.where(s["SELECTION_DECISION"].eq(INCLUDE) & s["FLAGGED"].eq("yes"),
                             "Include (flagged)", s["SELECTION_DECISION"])
    t = pd.crosstab([s["SITE_ID"], s["SENTENCE_ID"]], s["DECISION"])
    cols = [c for c in [INCLUDE, "Include (flagged)", CHECK, REPAIR, EXCLUDE, PENDING_DATA, PENDING_META]
            if c in t.columns] + [c for c in t.columns if c not in DECISION_ORDER + ["Include (flagged)"]]
    t = t[cols]
    t["TOTAL"] = t.sum(axis=1)
    return t.reset_index()


def parameters_rows() -> List[Dict]:
    return [{"STEP": a, "PARAMETER": b, "VALUE": c} for a, b, c in SELECTION_PARAMETERS]


def ensure_overrides_file(path: Path) -> Path:
    """Create an empty overrides file if there is none (an existing one is never touched)."""
    path = Path(path)
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(columns=OVERRIDE_COLUMNS).to_csv(path, index=False, encoding=CSV_ENCODING)
    return path


# --------------------------------------------------------------------------- command line
def main():
    ap = argparse.ArgumentParser(description=tr('Re-apply the token-selection rule to an existing run '
                                                '(after editing the overrides file), without re-measuring.'))
    add_lang_option(ap)
    ap.add_argument("--results", required=True, help=tr('intonasphere_results.xlsx of a run'))
    ap.add_argument("--overrides", default=None,
                    help=tr('CSV of manual decisions (default: manual_overrides.csv next to the results)'))
    ap.add_argument("--no-plan-s4", action="store_true", help=tr('do not add pending S4 rows for speakers without S4'))
    ap.add_argument("--out", default=None, help=tr('output workbook (default: intonasphere_selection.xlsx next to the results)'))
    a = ap.parse_args()
    res = user_path(a.results)
    xl = pd.ExcelFile(res)
    ds = xl.parse("DATASET")
    at = xl.parse("ALL_TOKENS") if "ALL_TOKENS" in xl.sheet_names else None
    sp = xl.parse("SPEAKERS").set_index("CODE") if "SPEAKERS" in xl.sheet_names else None
    ov_path = ensure_overrides_file(user_path(a.overrides) if a.overrides else res.with_name("manual_overrides.csv"))
    sel = select(ds, at, sp, read_overrides(ov_path), plan_s4=not a.no_plan_s4)
    out = user_path(a.out) if a.out else res.with_name("intonasphere_selection.xlsx")
    flow, by_site = token_flow(sel), token_flow_by_site(sel)
    with pd.ExcelWriter(out, engine="openpyxl") as xw:
        sel.to_excel(xw, sheet_name="SELECTION", index=False)
        flow.to_excel(xw, sheet_name="TOKEN_FLOW", index=False)
        by_site.to_excel(xw, sheet_name="TOKEN_FLOW_BY_SITE", index=False)
        pd.DataFrame(parameters_rows()).to_excel(xw, sheet_name="PARAMETERS", index=False)
    sel.to_csv(out.with_suffix(".csv"), index=False, encoding=CSV_ENCODING)
    print(flow.to_string(index=False))
    print(tr('\nOverrides read from {ov_path}\n  -> {out}', ov_path=ov_path, out=out))


if __name__ == "__main__":
    main()
