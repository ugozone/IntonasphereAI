"""
IntonaSphere AI - check a data folder BEFORE processing it
==========================================================

    python -m modules.check_folder --folder ~/Desktop/pfc_all --speakers metadata/pfc_speaker_table_corrected.xlsx

Reads every WAV and TextGrid in the folder (changes nothing) and reports:
  - each WAV: readable, sample rate, channels, duration, clipping, near-silence
  - pairing: which TextGrid each WAV will use; TextGrids with no WAV; extra versions
    (R, m, copy ...); TextGrid length different from the WAV (wrong pairing)
  - each TextGrid: tiers present (ORT-MAU, MAU, MAS), non-French symbols (wrong WebMAUS
    language), a file name typed into the text, words different from the PFC sentence
  - per speaker: which of tw1-tw4 are present / aligned; codes missing from the speaker table
  - what the pipeline will do with each file (use your TextGrid / align with WebMAUS / skip)
Writes folder_check.xlsx and folder_check_report.txt in the folder's parent (or --out).
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Dict, List

import numpy as np
import pandas as pd
from scipy.io import wavfile

from .final_domain_visualizer import read_textgrid, match_textgrid, PFC_QUESTIONS, sentence_id

PFC_NAME = re.compile(r"^(.+?)tw([1-4])$", re.I)
NON_FRENCH = {"I", "aU", "aI", "OY", "?", "e:", "i:", "a:", "o:", "u:", "y:", "2:", "E:", "OE", "U", "Y", "6", "C", "Q", "V", "T", "D", "{"}


def _norm(s: str) -> List[str]:
    s = s.lower().replace("’", "'").replace("-", " ")
    return [w for w in re.findall(r"[a-zàâçéèêëîïôûùüÿœæ']+", s) if w]


def check_wav(p: Path) -> Dict:
    r: Dict = {}
    try:
        sr, x = wavfile.read(str(p))
    except Exception as e:
        return {"WAV_OK": False, "WAV_PROBLEM": f"cannot read: {e}"}
    ch = 1 if x.ndim == 1 else x.shape[1]
    if x.dtype == np.int16:
        y = x.astype(float) / 32768
    elif x.dtype == np.int32:
        y = x.astype(float) / 2 ** 31
    elif x.dtype == np.uint8:
        y = (x.astype(float) - 128) / 128
    else:
        y = x.astype(float)
    if y.ndim > 1:
        y = y.mean(axis=1)
    dur = len(y) / sr
    peak = float(np.max(np.abs(y))) if len(y) else 0.0
    clip = float(np.mean(np.abs(y) > 0.999)) * 100 if len(y) else 0.0
    probs = []
    if dur < 0.8:
        probs.append(f"very short ({dur:.2f} s)")
    if dur > 15:
        probs.append(f"very long ({dur:.1f} s): more than one sentence?")
    if peak < 0.001:                       # below -60 dBFS: no usable signal
        probs.append("nearly silent")
    elif peak < 0.05:                      # quiet but usable: pitch is unaffected, absolute intensity is lower
        probs.append(f"low recording level (peak {20 * np.log10(peak):.0f} dBFS): usable; intensity not comparable")
    if clip > 0.1:
        probs.append(f"clipping ({clip:.2f}% of samples)")
    r.update(WAV_OK=not any(p.startswith(("very short", "nearly")) for p in probs), SAMPLE_RATE=sr, CHANNELS=ch,
             BITS=str(x.dtype), WAV_DURATION=round(dur, 3), PEAK=round(peak, 3), WAV_PROBLEM="; ".join(probs))
    return r


def check_textgrid(tg_path: Path, wav_dur: float, stem: str, q: str) -> Dict:
    r: Dict = {}
    try:
        tg = read_textgrid(tg_path)
    except Exception as e:
        return {"TG_OK": False, "TG_PROBLEM": f"cannot read: {e}"}
    names = [t.name for t in tg.tiers]
    probs, notes = [], []
    for need in ("ORT-MAU", "MAU", "MAS"):
        if need not in names:
            alt = {"ORT-MAU": ["words", "word"], "MAS": ["syllabe", "syllable", "sylable", "syllables"],
                   "MAU": ["phones"]}[need]
            if not any(a in names for a in alt):
                (probs if need != "MAU" else notes).append(f"no {need} tier")
    if wav_dur and abs(tg.xmax - wav_dur) > 0.05:
        probs.append(f"TextGrid length {tg.xmax:.2f} s vs WAV {wav_dur:.2f} s: wrong pairing or re-cut audio")
    mau = tg.get("MAU")
    if mau is not None:
        bad = sorted({iv.label.strip() for iv in mau.intervals if iv.label.strip() in NON_FRENCH})
        if bad:
            probs.append(f"non-French phone symbols {bad}: aligned with a non-French WebMAUS model, re-align")
    ort = tg.get("ORT-MAU") or tg.get("words") or tg.get("word")
    words = [iv.label.strip() for iv in ort.intervals if iv.label.strip() and not iv.label.startswith("<")] if ort else []
    key = re.sub(r"[^a-z0-9]", "", stem.lower())
    if any(re.sub(r"[^a-z0-9]", "", w.lower()) == key or re.search(r"tw[1-4]", w.lower()) for w in words):
        notes.append("a file name is part of the aligned text (it is ignored by the pipeline)")
    kan = tg.get("KAN-MAU")
    if kan is not None and any(iv.label.replace(" ", "") in ("kts", "kts@") for iv in kan.intervals):
        notes.append("Qu'est-ce transcribed /kts/ by WebMAUS (known G2P error)")
    text = " ".join(w for w in words if not re.search(r"tw[1-4]", w.lower()))
    r["ALIGNED_TEXT"] = text
    if q in PFC_QUESTIONS and words:
        exp, got = _norm(PFC_QUESTIONS[q]), _norm(text)
        if got != exp:
            missing = [w for w in exp if w not in got]
            extra = [w for w in got if w not in exp]
            notes.append("text differs from the PFC sentence"
                         + (f"; missing: {' '.join(missing)}" if missing else "")
                         + (f"; extra: {' '.join(extra)}" if extra else "")
                         + " (fine if that is what the reader said)")
    r.update(TG_OK=not probs, TIERS=", ".join(names), TG_PROBLEM="; ".join(probs), TG_NOTE="; ".join(notes))
    return r


ASIDE = "_set_aside"


def plan_fixes(folder: Path, df: pd.DataFrame, tgs: List[Path], wavs: List[Path], orphans: List[str]) -> List[Dict]:
    """Safe, reversible actions: rename TextGrids with typos to their WAV's name, and move
    unusable or extra files into <folder>/_set_aside/ (nothing is deleted)."""
    import difflib
    acts: List[Dict] = []
    have_tg = {w.stem for w in wavs if len(df) and
               (df.loc[df.AUDIO_FILE == w.name, "TEXTGRID_USED"].astype(str) != "").any()}
    free = [w for w in wavs if w.stem not in have_tg and PFC_NAME.match(w.stem)]
    taken = set()
    for name in orphans:
        stem = Path(name).stem
        digit = re.search(r"(\d)$", stem)
        cands = [w for w in free if w.stem not in taken and (not digit or w.stem.endswith(digit.group(1)))]
        best = difflib.get_close_matches(stem.lower(), [w.stem.lower() for w in cands], n=1, cutoff=0.8)
        if best:
            w = next(w for w in cands if w.stem.lower() == best[0])
            taken.add(w.stem)
            acts.append({"ACTION": "rename", "FROM": name, "TO": w.stem + ".TextGrid",
                         "WHY": f"name typo: matches {w.name}, which has no TextGrid"})
        else:
            acts.append({"ACTION": "set aside", "FROM": name, "TO": f"{ASIDE}/{name}",
                         "WHY": "TextGrid with no matching WAV"})
    for _, r in df.iterrows():
        if str(r.get("SENTENCE", "")) == "?":
            acts.append({"ACTION": "set aside", "FROM": r.AUDIO_FILE, "TO": f"{ASIDE}/{r.AUDIO_FILE}",
                         "WHY": "not a PFC recording name (xxxtw1-4)"})
            continue
        if not r.get("WAV_OK", True):
            acts.append({"ACTION": "set aside", "FROM": r.AUDIO_FILE, "TO": f"{ASIDE}/{r.AUDIO_FILE}",
                         "WHY": f"audio unusable: {r.get('WAV_PROBLEM')}"})
        for v in [x.strip() for x in str(r.get("OTHER_TEXTGRID_VERSIONS") or "").split(",") if x.strip() and x.strip() != "nan"]:
            acts.append({"ACTION": "set aside", "FROM": v, "TO": f"{ASIDE}/{v}",
                         "WHY": f"extra version; {r.TEXTGRID_USED} is used"})
        tp = r.get("TG_PROBLEM")
        if isinstance(tp, str) and tp and r.get("TEXTGRID_USED"):
            acts.append({"ACTION": "set aside", "FROM": r.TEXTGRID_USED, "TO": f"{ASIDE}/{r.TEXTGRID_USED}",
                         "WHY": f"{tp} -> the pipeline will re-align this file with WebMAUS"})
    seen, out = set(), []
    for a_ in acts:                                    # one action per file
        if a_["FROM"] not in seen:
            seen.add(a_["FROM"]); out.append(a_)
    return out


def apply_fixes(folder: Path, acts: List[Dict], log_path: Path) -> int:
    done = []
    (folder / ASIDE).mkdir(exist_ok=True)
    for a_ in acts:
        src, dst = folder / a_["FROM"], folder / a_["TO"]
        if not src.exists():
            a_["RESULT"] = "skipped: file not found"; continue
        if dst.exists():
            a_["RESULT"] = "skipped: target already exists"; continue
        src.rename(dst)
        a_["RESULT"] = "done"; done.append(a_)
    old = pd.read_csv(log_path) if log_path.exists() else pd.DataFrame()
    pd.concat([old, pd.DataFrame(acts)], ignore_index=True).to_csv(log_path, index=False)
    return len(done)


def undo_fixes(folder: Path, log_path: Path) -> int:
    if not log_path.exists():
        print("No fix log found: nothing to undo."); return 0
    log = pd.read_csv(log_path)
    n = 0
    for _, a_ in log[log.RESULT == "done"].iloc[::-1].iterrows():
        src, dst = folder / a_["TO"], folder / a_["FROM"]
        if src.exists() and not dst.exists():
            src.rename(dst); n += 1
    log_path.rename(log_path.with_suffix(".undone.csv"))
    print(f"Undid {n} change(s).")
    return n


def main():
    ap = argparse.ArgumentParser(description="Check a data folder before running IntonaSphere")
    ap.add_argument("--folder", required=True)
    ap.add_argument("--speakers", default=None)
    ap.add_argument("--speaker-fix", action="append", default=[], metavar="TABLE_CODE=CORRECT_CODE")
    ap.add_argument("--align", choices=["none", "pfc", "any"], default="pfc",
                    help="the alignment mode you plan to use (only changes the 'pipeline will' column)")
    ap.add_argument("--out", default=None, help="where to write the report (default: next to the folder)")
    ap.add_argument("--fix", action="store_true",
                    help="propose safe fixes (renames, set-asides); add --apply to carry them out")
    ap.add_argument("--apply", action="store_true", help="with --fix: carry out the proposed fixes")
    ap.add_argument("--undo", action="store_true", help="reverse the fixes recorded in folder_fix_log.csv")
    a = ap.parse_args()
    if a.undo:
        f_ = Path(a.folder).expanduser()
        undo_fixes(f_, f_ / "folder_fix_log.csv")
        return
    folder = Path(a.folder).expanduser()
    out = Path(a.out).expanduser() if a.out else folder.parent
    files = [p for p in folder.iterdir() if not p.name.startswith(".")]
    wavs = sorted(p for p in files if p.suffix.lower() == ".wav")
    tgs = sorted(p for p in files if p.suffix.lower() == ".textgrid")
    txts = sorted(p for p in files if p.suffix.lower() == ".txt")
    others = sorted(p.name for p in files if p.suffix.lower() not in (".wav", ".textgrid", ".txt") and p.is_file())
    rows, used = [], set()
    for w in wavs:
        m = PFC_NAME.match(w.stem)
        code, q = (m.group(1).lower(), m.group(2)) if m else (w.stem.lower(), "")
        r = {"AUDIO_FILE": w.name, "SPEAKER": code, "SENTENCE": sentence_id(q) if q else "?"}
        r.update(check_wav(w))
        tg = match_textgrid(w, tgs)
        versions = [t.name for t in tgs if t.stem.lower().startswith(w.stem.lower())
                    and not t.stem[len(w.stem):len(w.stem) + 1].isdigit()]
        r["TEXTGRID_USED"] = tg.name if tg else ""
        r["OTHER_TEXTGRID_VERSIONS"] = ", ".join(v for v in versions if not tg or v != tg.name)
        if tg:
            used.add(tg.name)
            r.update(check_textgrid(tg, r.get("WAV_DURATION", 0), w.stem, q))
        has_txt = w.with_suffix(".txt").exists()
        if not r.get("WAV_OK", False):
            plan = "PROBLEM: audio unusable"
        elif tg:
            plan = "use your TextGrid" + (" (PROBLEM: see TG_PROBLEM)" if not r.get("TG_OK", True) else "")
        elif has_txt and a.align != "none":
            plan = "align with WebMAUS using your .txt"
        elif q and a.align != "none":
            plan = "align with WebMAUS using the PFC text"
        elif a.align == "any":
            plan = "speech recognition + WebMAUS (check the transcript)"
        else:
            plan = "final-domain only (automatic segmentation); no F_ToBI"
        if not q:
            plan += "  [name is not xxxtw1-4: no SENTENCE_ID]"
        r["PIPELINE_WILL"] = plan
        rows.append(r)
    df = pd.DataFrame(rows)
    orphans = [t.name for t in tgs if t.name not in used and not any(
        t.stem.lower().startswith(w.stem.lower()) for w in wavs)]

    # speakers
    sp_rows, sp_info = [], {}
    codes = sorted(set(df.SPEAKER)) if len(df) else []
    table = None
    if a.speakers:
        from .dataset_sheet import load_speakers
        table, sp_info = load_speakers(Path(a.speakers).expanduser(), "Older",
                                       dict(f.split("=", 1) for f in a.speaker_fix))
    import difflib
    for c in sorted(set(codes) | (set(table.index) if table is not None else set())):
        sub = df[df.SPEAKER == c] if len(df) else pd.DataFrame()
        have = {s: (s in set(sub.SENTENCE)) for s in ("Q1", "Q2", "Q3", "S4")}
        aligned = {s: bool(len(sub[(sub.SENTENCE == s) & (sub.TEXTGRID_USED != "")])) for s in have}
        rec = {"SPEAKER": c, **{f"{s}_WAV": "yes" if have[s] else "-" for s in have},
               **{f"{s}_TEXTGRID": "yes" if aligned[s] else ("-" if not have[s] else "no (will align)")
                  for s in have}}
        rec["ALL_3_QUESTIONS"] = all(have[s] for s in ("Q1", "Q2", "Q3"))
        if table is not None:
            if c in table.index:
                rec["IN_SPEAKER_TABLE"] = "yes"
                rec["SITE"] = table.loc[c, "SITE_ID"]
            else:
                close = difflib.get_close_matches(c, list(table.index), n=1, cutoff=0.6)
                rec["IN_SPEAKER_TABLE"] = "NO" + (f" (closest: {close[0]})" if close else "")
            if c not in codes:
                rec["IN_SPEAKER_TABLE"] = "table only: no recordings in the folder"
        sp_rows.append(rec)
    sdf = pd.DataFrame(sp_rows)

    # report
    L = [f"IntonaSphere folder check: {folder}",
         f"{len(wavs)} WAV, {len(tgs)} TextGrid, {len(txts)} txt" + (f", other files: {', '.join(others[:8])}" if others else ""), ""]
    n_q = df.SENTENCE.value_counts().to_dict() if len(df) else {}
    L.append("Recordings per sentence: " + ", ".join(f"{k}: {v}" for k, v in sorted(n_q.items())))
    if len(sdf):
        rec = sdf[sdf.get("IN_SPEAKER_TABLE", pd.Series(["yes"] * len(sdf))).astype(str).str.startswith(("yes", "NO"))] \
            if "IN_SPEAKER_TABLE" in sdf else sdf
        full = int(rec.ALL_3_QUESTIONS.sum())
        L.append(f"Speakers with recordings: {len(rec)}; with all three questions (Q1-Q3): {full}")
    probs = df[(~df.get("WAV_OK", True).astype(bool)) | (df.get("TG_OK", True).fillna(True) == False)] if len(df) else df
    L += ["", f"PROBLEMS TO FIX BEFORE PROCESSING ({len(probs)} file(s)):"]
    for _, r in probs.iterrows():
        wp = r.get("WAV_PROBLEM") if isinstance(r.get("WAV_PROBLEM"), str) and not r.get("WAV_OK", True) else ""
        tp = r.get("TG_PROBLEM") if isinstance(r.get("TG_PROBLEM"), str) else ""
        L.append(f"  {r.AUDIO_FILE}: {wp} {tp}".replace("  ", " ").rstrip())
    if orphans:
        L.append(f"  TextGrids with no matching WAV: {', '.join(orphans)}")
    if len(sdf) and "IN_SPEAKER_TABLE" in sdf:
        miss = sdf[sdf.IN_SPEAKER_TABLE.astype(str).str.startswith("NO")]
        for _, r in miss.iterrows():
            L.append(f"  speaker {r.SPEAKER}: not in the speaker table {r.IN_SPEAKER_TABLE[2:]}")
    if len(probs) == 0 and not orphans and not (len(sdf) and "IN_SPEAKER_TABLE" in sdf and
                                                 sdf.IN_SPEAKER_TABLE.astype(str).str.startswith("NO").any()):
        L.append("  none")
    low = df[df.get("WAV_PROBLEM", pd.Series([""] * len(df))).fillna("").str.contains("low recording level")] if len(df) else df
    if len(low):
        L += ["", f"Low recording level ({len(low)} file(s)) - usable, no action needed; intensity values are lower: "
              + ", ".join(low.AUDIO_FILE.head(30))]
    multi = df[df.OTHER_TEXTGRID_VERSIONS.astype(str) != ""] if len(df) else df
    if len(multi):
        L += ["", "Several TextGrid versions for one WAV (the one used is shown; move the others out):"]
        L += [f"  {r.AUDIO_FILE}: uses {r.TEXTGRID_USED}; also {r.OTHER_TEXTGRID_VERSIONS}" for _, r in multi.iterrows()]
    notes = df[df.get("TG_NOTE", pd.Series([""] * len(df))).fillna("") != ""] if len(df) else df
    if len(notes):
        L += ["", f"Notes (no action needed unless unexpected) - {len(notes)} file(s), details in folder_check.xlsx"]
    plan = df.PIPELINE_WILL.str.replace(r"\s+\(PROBLEM.*", "", regex=True).value_counts().to_dict() if len(df) else {}
    L += ["", f"What the pipeline will do (--align {a.align}):"] + [f"  {v:4d}  {k}" for k, v in plan.items()]
    if table is not None:
        only = sdf[sdf.IN_SPEAKER_TABLE.astype(str).str.startswith("table only")]
        if len(only):
            L += ["", f"In the speaker table but no recordings in this folder: {', '.join(only.SPEAKER)}"]
    if a.fix:
        acts = plan_fixes(folder, df, tgs, wavs, orphans)
        L += ["", f"PROPOSED FIXES ({len(acts)}) - nothing is deleted; moved files go to {folder.name}/{ASIDE}/:"]
        L += [f"  {x['ACTION']:9s} {x['FROM']}  ->  {x['TO']}    ({x['WHY']})" for x in acts] or ["  none"]
        L.append("  Not fixed automatically: speaker codes missing from the speaker table (decide by hand).")
        if a.apply and acts:
            n = apply_fixes(folder, acts, folder / "folder_fix_log.csv")
            L += ["", f"APPLIED {n} fix(es). Log: {folder / 'folder_fix_log.csv'}  (undo: add --undo)",
                  "Run the check again (without --fix) to confirm the folder is clean."]
        elif acts:
            L += ["", "Nothing changed yet. To carry these out, run the same command with --fix --apply"]
    txt = "\n".join(L)
    print(txt)
    out.mkdir(parents=True, exist_ok=True)
    (out / "folder_check_report.txt").write_text(txt + "\n", encoding="utf-8")
    with pd.ExcelWriter(out / "folder_check.xlsx", engine="openpyxl") as xw:
        pd.DataFrame({"REPORT": L}).to_excel(xw, sheet_name="SUMMARY", index=False)
        df.to_excel(xw, sheet_name="FILES", index=False)
        sdf.to_excel(xw, sheet_name="SPEAKERS", index=False)
    print(f"\nReport: {out / 'folder_check_report.txt'}   Details: {out / 'folder_check.xlsx'}")


if __name__ == "__main__":
    main()
