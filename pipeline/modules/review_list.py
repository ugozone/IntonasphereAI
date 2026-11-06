"""
IntonaSphere AI - list of tokens to check by ear and eye (for praat/review_tokens.praat)
========================================================================================

Reads the SELECTION sheet of a run and writes review_list.tsv: one row per token to check, with
the full paths of its recording and of the TextGrid the run used, the stretch of time to zoom to
and what to look for. praat/review_tokens.praat then opens the tokens one at a time, writes your
decision to manual_overrides.csv and saves a corrected TextGrid (after a backup copy).

    python -m modules.review_list --results outputs/intonasphere_results.xlsx --folder data/wavs

Tasks (all by default; choose with --tasks 1,2):
  1  "Include – tune only" tokens: the final syllable has no usable F0 even after re-tracking it
     with a 50 Hz floor (low or creaky ending). Listen: if the nuclear configuration can be
     labelled (usually L%), keep it for tune choice; Exclude only if it cannot. Check the
     final-syllable boundary too (a wrong boundary is a measurement error, not creak)
  2  tokens to check by listening: the file may contain more than the sentence
  3  included tokens whose TextGrid was made by WebMAUS from the PFC text (not from a .txt of what
     the reader said), so a hesitation in the final word group would not be in the transcript:
     listen to the final word group
  4  included tokens whose final-syllable F0 was re-tracked with a 50 Hz floor: check that the new
     pitch line follows the voice (if it follows creak or noise, choose Tune only)
Tokens that already have a line with CHECKED = yes in the overrides file are left out
(use --all to list them again).
"""
from __future__ import annotations

from . import user_path, CSV_ENCODING
from .i18n import t as tr, add_lang_option

import argparse
from pathlib import Path
from typing import List

import pandas as pd

from . import selection as sel_rule

REVIEW_COLUMNS = ["ORDER", "TASK", "TOKEN_ID", "SITE_ID", "AUDIO_PATH", "TEXTGRID_PATH", "ZOOM_START", "ZOOM_END",
                  "FINAL_SYLLABLE_START", "FINAL_SYLLABLE_END", "WHAT_TO_DO", "WHY_LISTED"]
CONTEXT_BEFORE_S = 1.5      # seconds shown before the final syllable (tasks 1 and 3)
CONTEXT_AFTER_S = 0.3


def _num(v):
    try:
        f = float(v)
        return None if f != f else f
    except (TypeError, ValueError):
        return None


def instructions(task: int) -> str:
    return {
        1: tr("The final syllable has no usable F0, even with a 50 Hz pitch floor: a low or creaky ending. "
              "Listen to the end of the sentence. Choose 'Tune only' if you can label the nuclear "
              "configuration (usually a fall to L%); choose Exclude only if you cannot; choose 'TextGrid "
              "corrected' if the final-syllable boundary was wrong and you moved it. If the file goes on after the "
              "sentence (breath or room noise, no pulses), drag the end of the last word to where the voice stops and "
              "choose 'Cut the noise after the last word'."),
        2: tr("The articulation rate is below 2 syllables per second: the file may contain more than the "
              "sentence. Play the whole file. Include if it holds only its sentence, otherwise Exclude."),
        3: tr("This TextGrid was made by WebMAUS from the PFC text, so a hesitation would not be in the "
              "transcript. Listen to the final word group. Exclude only if it is repeated or contains a "
              "hesitation or self-repair; otherwise Include."),
        4: tr("The F0 of the final syllable was re-tracked with a 50 Hz floor. Look at the pitch line on "
              "the final syllable with the 50-500 Hz range. Include if it follows the voice; choose "
              "'Tune only' if it follows creak or noise."),
    }[task]


def build(results: Path, folder: Path, tasks: List[int], overrides: Path, include_checked: bool) -> pd.DataFrame:
    xl = pd.ExcelFile(results)
    sel = xl.parse("SELECTION")
    at = xl.parse("ALL_TOKENS")
    fd = xl.parse("FINAL_DOMAIN") if "FINAL_DOMAIN" in xl.sheet_names else pd.DataFrame(columns=["AUDIO_FILE"])
    ds = xl.parse("DATASET")
    sel = sel[sel["AUDIO_FILE"].notna()].copy()
    tg_used = dict(zip(at["AUDIO_FILE"], at.get("TEXTGRID_USED", pd.Series([""] * len(at)))))
    fd = fd.drop_duplicates("AUDIO_FILE").set_index("AUDIO_FILE")
    ends = dict(zip(ds["AUDIO_FILE"], ds["EXTRACTION_END"]))
    ov = sel_rule.read_overrides(overrides)
    checked = set(ov.index[ov["CHECKED"].str.strip().str.lower().eq("yes")]) if len(ov) else set()

    reason = sel["AUTO_REASON"].fillna("")
    task_of = pd.Series(0, index=sel.index)
    task_of[sel["AUTO_DECISION"].eq(sel_rule.TUNE_ONLY)
            | (sel["AUTO_DECISION"].eq(sel_rule.EXCLUDE) & reason.str.startswith("(a)"))] = 1   # (older runs: Exclude)
    task_of[sel["AUTO_DECISION"].eq(sel_rule.CHECK)] = 2
    task_of[(task_of == 0) & sel["AUTO_DECISION"].eq(sel_rule.INCLUDE)
            & sel["TRANSCRIPT_SOURCE"].fillna("").str.startswith("WebMAUS")
            & sel["TRANSCRIPT_SOURCE"].fillna("").str.contains("hesitation")] = 3   # not when aligned from your own .txt
    if "LOW_FLOOR_RESCUE" in sel:
        task_of[(task_of == 0) & sel["AUTO_DECISION"].eq(sel_rule.INCLUDE)
                & sel["LOW_FLOOR_RESCUE"].astype(str).str.lower().eq("yes")] = 4
    rows = []
    for i, r in sel[task_of.isin(tasks)].iterrows():
        if r["TOKEN_ID"] in checked and not include_checked:
            continue
        task = int(task_of[i])
        wav = folder / r["AUDIO_FILE"]
        a = _num(fd["FINAL_SYLLABLE_START"].get(r["AUDIO_FILE"])) if "FINAL_SYLLABLE_START" in fd else None
        b = _num(fd["FINAL_SYLLABLE_END"].get(r["AUDIO_FILE"])) if "FINAL_SYLLABLE_END" in fd else None
        end = _num(ends.get(r["AUDIO_FILE"]))
        if task == 2 or (a is None and end is None):
            z0, z1 = 0.0, 0.0                                   # 0 / 0 = show the whole file
        else:
            right = b if b is not None else end
            left = a if a is not None else right
            z0, z1 = max(0.0, left - CONTEXT_BEFORE_S), right + CONTEXT_AFTER_S
        rows.append({"TASK": task, "TOKEN_ID": r["TOKEN_ID"], "SITE_ID": r.get("SITE_ID", ""),
                     "AUDIO_PATH": str(wav), "TEXTGRID_PATH": str(tg_used.get(r["AUDIO_FILE"], "") or ""),
                     "ZOOM_START": round(z0, 3), "ZOOM_END": round(z1, 3),
                     "FINAL_SYLLABLE_START": "" if a is None else round(a, 3),
                     "FINAL_SYLLABLE_END": "" if b is None else round(b, 3),
                     "WHAT_TO_DO": instructions(task), "WHY_LISTED": r["AUTO_REASON"]})
    out = pd.DataFrame(rows, columns=[c for c in REVIEW_COLUMNS if c != "ORDER"])
    out = out.sort_values(["TASK", "SITE_ID", "TOKEN_ID"]).reset_index(drop=True)
    out.insert(0, "ORDER", range(1, len(out) + 1))
    return out


def main():
    ap = argparse.ArgumentParser(description=tr("List the tokens to check by ear and eye, for praat/review_tokens.praat"))
    add_lang_option(ap)
    ap.add_argument("--results", required=True, help=tr("intonasphere_results.xlsx of a run"))
    ap.add_argument("--folder", default=None,
                    help=tr("folder with the recordings (the --folder of run_all; default: as recorded in PARAMETERS)"))
    ap.add_argument("--tasks", default="1,2,3,4", help=tr("which checks to list, e.g. 1,2 (default: 1,2,3,4)"))
    ap.add_argument("--overrides", default=None,
                    help=tr("CSV of manual decisions (default: manual_overrides.csv next to the results)"))
    ap.add_argument("--all", action="store_true", help=tr("also list tokens already marked CHECKED = yes"))
    ap.add_argument("--out", default=None, help=tr("output file (default: review_list.tsv next to the results)"))
    a = ap.parse_args()
    res = user_path(a.results)
    folder = user_path(a.folder) if a.folder else None
    if folder is None:
        params = pd.read_excel(res, sheet_name="PARAMETERS")
        hit = params.loc[params["PARAMETER"].eq("input folder"), "VALUE"]
        if hit.empty:
            raise SystemExit(tr("This run does not record its input folder: give it with --folder"))
        folder = Path(str(hit.iloc[0]))
    ov = sel_rule.ensure_overrides_file(user_path(a.overrides) if a.overrides else res.with_name("manual_overrides.csv"))
    tasks = [int(x) for x in str(a.tasks).replace(" ", "").split(",") if x]
    lst = build(res, folder, tasks, ov, a.all)
    out = user_path(a.out) if a.out else res.with_name("review_list.tsv")
    lst.fillna("-").replace("", "-").to_csv(out, sep="\t", index=False, encoding="utf-8")   # Praat: no empty cells
    missing = [p for p in lst["AUDIO_PATH"] if not Path(p).exists()]
    for task in sorted(set(lst["TASK"])):
        print(tr("task {task}: {n} token(s)", task=task, n=int((lst["TASK"] == task).sum())))
    if missing:
        print(tr("WARNING: {n} recording(s) not found in {folder}; check --folder", n=len(missing), folder=folder))
    print(tr("\n{n} token(s) to check -> {out}\nIn Praat: Open > Open Praat script... praat/review_tokens.praat, "
             "then Run, and give it this file and {ov}", n=len(lst), out=out, ov=ov))


if __name__ == "__main__":
    main()
