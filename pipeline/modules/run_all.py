"""
IntonaSphere AI - one command for the whole pipeline
====================================================

For every WAV in a folder, in a single pass:

  1. alignment   - uses your TextGrid if there is one; otherwise WebMAUS (French) with your
                   .txt, the PFC question text, or a speech-recognition transcript
                   (modules/auto_align.py)
  2. pitch       - tracked ONCE per file (Praat via Parselmouth, speaker-adaptive range) and
                   shared by both analyses, so both graphs show the same F0
  3. final-domain graph + cues   (modules/final_domain_visualizer.py)
  4. F_ToBI graph + annotation   (modules/ftobi_annotator.py)
  5. one Excel workbook with everything, one row per recording

    python -m modules.run_all --folder data/wavs --out outputs
    python -m modules.run_all --folder data/wavs --out outputs --no-ftobi
    python -m modules.run_all --folder data/wavs --out outputs --no-final-domain --align none

Output layout
    outputs/
      intonasphere_results.xlsx   README / ALL_TOKENS / FINAL_DOMAIN / FTOBI_TOKENS /
                                  FTOBI_SYLLABLES / ALIGNMENT / PARAMETERS
      intonasphere_results.csv    the ALL_TOKENS sheet
      final_domain/               x_final_domain.png, x_cues.TextGrid, final_domain_cues.xlsx
      ftobi/                      x_ftobi.png, x_ftobi.TextGrid, ftobi_annotations.xlsx,
                                  ftobi_praat_ranges.csv  (open with praat/check_ftobi.praat)
      aligned/                    TextGrids made by WebMAUS + alignment_log.csv

If a recording cannot be aligned, the final-domain graph is still drawn with automatic
segmentation (silences + intensity nuclei), as the visualizer always did, and the F_ToBI
step is skipped for that file (it needs words and syllables). The ALL_TOKENS sheet says
which happened for each file.

The separate commands (modules.final_domain_visualizer, modules.ftobi_annotator,
modules.auto_align) keep working exactly as before.
"""
from __future__ import annotations

from . import user_path, CSV_ENCODING

import argparse
import time
from dataclasses import asdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd

from .final_domain_visualizer import (HAVE_PARSELMOUTH, load_wav, adaptive_pitch, process_token,
                                      write_praat_check)
from .ftobi_annotator import FToBIConfig, annotate, write_tables
from .auto_align import ensure_alignments
from .pitch_range import plan_ranges
from .dataset_sheet import (DATASET_COLUMNS, load_speakers, dataset_row, codebook_df)

SHARED = ["TOKEN_ID", "SPEAKER_ID", "SENTENCE_ID", "AUDIO_FILE", "PITCH_ENGINE", "PITCH_FLOOR_HZ", "PITCH_CEILING_HZ"]

README_ROWS = [
    ("What this workbook is", "Output of one IntonaSphere AI run: one row per recording in DATASET and ALL_TOKENS."),
    ("DATASET", "The dataset of record: the 28 released headings, in order, every value computed by code (definitions in CODEBOOK)."),
    ("CODEBOOK", "Definition, unit and source of every DATASET column."),
    ("SPEAKERS", "The speaker table as used: codes corrected, spelling normalised, AGE_GROUP recomputed by the median rule."),
    ("DATASET_WARNINGS", "Recordings whose speaker is missing from the speaker table, or whose measures failed."),
    ("ALL_TOKENS", "Alignment provenance + final-domain cues + F_ToBI summary for every recording."),
    ("FINAL_DOMAIN", "Final-syllable cues (onset, peak, offset, slope, duration, contour class) - figure: final_domain/x_final_domain.png."),
    ("FTOBI_TOKENS", "F_ToBI proposal per recording (nuclear configuration, phrasing, tones, '?' count) - figure: ftobi/x_ftobi.png."),
    ("FTOBI_SYLLABLES", "Every syllable with its cues and the decision taken (evidence for the F_ToBI labels)."),
    ("ALIGNMENT", "Where each TextGrid came from (your TextGrid, WebMAUS with your text / PFC text / speech recognition)."),
    ("PARAMETERS", "Every threshold used in this run, so the run can be repeated exactly."),
    ("Verification", "Open ftobi/*_ftobi.TextGrid with praat/check_ftobi.praat; then python -m modules.validate_ftobi."),
    ("Labels", "F_ToBI labels are PROPOSALS. A '?' marks a low-confidence label: check those first."),
]


def _check_outputs_writable(*dirs: Path) -> None:
    """Stop at once (not after a long run) if a results file is open in Excel: Windows locks open files."""
    locked = []
    for d in dirs:
        if not d.exists():
            continue
        for f in list(d.glob("*.xlsx")) + list(d.glob("*.csv")):
            try:
                with open(f, "a"):
                    pass
            except PermissionError:
                locked.append(f.name)
    if locked:
        raise SystemExit("These result files are open in another program (e.g. Excel) and cannot be "
                         "overwritten:\n  " + "\n  ".join(locked) + "\nClose them, or choose another --out folder, "
                         "then run the command again.")


def run(folder: Path, out: Path, align: str = "any", final_domain: bool = True, ftobi: bool = True,
        cfg: Optional[FToBIConfig] = None, slope_threshold: float = 1.5, tier: str = "MAS",
        fixed_range: Optional[Tuple[float, float]] = None, language: str = "fra-FR",
        asr_model: str = "small", svg: bool = False, speakers_file: Optional[Path] = None,
        age_tie: str = "Older", speaker_fixes: Optional[Dict[str, str]] = None,
        speakers_sheet: Optional[str] = None, pitch_method: str = "speaker",
        first_pass_by_sex: bool = True, realign: bool = False) -> pd.DataFrame:
    cfg = cfg or FToBIConfig()
    folder, out = Path(folder), Path(out)
    fd_dir, ft_dir, al_dir = out / "final_domain", out / "ftobi", out / "aligned"
    _check_outputs_writable(out, fd_dir, ft_dir)
    t0 = time.time()
    print(f"IntonaSphere AI  |  folder: {folder}  |  alignment: {align}  |  "
          f"final-domain: {'on' if final_domain else 'off'}  |  F_ToBI: {'on' if ftobi else 'off'}  |  "
          f"pitch: {'Praat (Parselmouth)' if HAVE_PARSELMOUTH else 'built-in Praat-style tracker'}")
    speakers, sp_info = None, {}
    if speakers_file:
        speakers, sp_info = load_speakers(Path(speakers_file), age_tie, speaker_fixes, speakers_sheet)
        print(f"Speaker table: {sp_info['file']} [{sp_info['sheet']}], {sp_info['speakers']} speakers; "
              f"AGE_GROUP rule: {sp_info['age_rule']}")
    ds_rows: List[Dict] = []
    ds_warn: List[Dict] = []
    print("Step 1/2  alignment")
    if realign:
        print("Re-aligning EVERY file with WebMAUS (your TextGrids are kept only for comparison)")
    aligned = ensure_alignments(folder, al_dir, align, language, asr_model, realign=realign)
    ranges: Dict[str, Dict] = {}
    if not fixed_range:
        print(f"Pitch ranges: two-pass, pooled per {pitch_method}"
              f"{', first pass by sex' if first_pass_by_sex and speakers is not None else ''}")
        ranges = plan_ranges([a.wav for a in aligned], pitch_method, speakers, first_pass_by_sex)
    print("Step 2/2  analysis")
    fd_rows: List[Dict] = []
    ft_rows: List[Dict] = []
    syl_frames: List[pd.DataFrame] = []
    all_rows: List[Dict] = []
    for i, a in enumerate(aligned, 1):
        w, tg = a.wav, a.textgrid
        base = {"AUDIO_FILE": w.name, "TEXTGRID_USED": str(tg) if tg else "",
                "ALIGNMENT_SOURCE": a.alignment_source or ("none" if tg is None else ""),
                "TEXT_SOURCE": a.text_source or ("in TextGrid" if a.alignment_source == "user_textgrid" else ""),
                "ALIGNMENT_NOTE": a.message,
                "USER_TEXTGRID": str(a.user_textgrid) if a.user_textgrid else ""}
        note = f"  ({a.alignment_source})" if a.alignment_source else ""
        if tg is None:
            note = f"  -> final-domain with automatic segmentation, F_ToBI skipped [{a.message[:90]}]"
        print(f"[{i}/{len(aligned)}] {w.name:24s} textgrid: {tg.name if tg else 'none'}{note}")
        try:
            x, sr = load_wav(w)
            # one pitch track per file, shared by both analyses
            if fixed_range:
                rg = tuple(fixed_range)
            elif w.name in ranges:
                rg = (ranges[w.name]["floor"], ranges[w.name]["ceiling"])
            else:
                rg = None
            pitch = adaptive_pitch(x, sr, fixed=rg)
            if w.name in ranges and not fixed_range:
                r_ = ranges[w.name]
                base.update(PITCH_RANGE_METHOD=f"two-pass, pooled per {r_['method']}", PITCH_FIRST_PASS=r_["first_pass"],
                            PITCH_RANGE_GROUP=r_["group"], PITCH_PASS1_VOICED_FRAMES=r_["n_voiced"],
                            SPEAKER_MEDIAN_F0_HZ=r_["median_f0"], PITCH_QC=r_["flag"])
                if r_["flag"]:
                    ds_warn.append({"AUDIO_FILE": w.name, "WARNING": r_["flag"]})
        except Exception as e:
            all_rows.append({**base, "FINAL_DOMAIN_STATUS": "failed", "FTOBI_STATUS": "failed", "ERROR": str(e)})
            continue
        row = dict(base)
        if final_domain:
            try:
                r = process_token(w, tg, fd_dir, tier=tier, slope_threshold=slope_threshold,
                                  fixed_range=fixed_range, svg=svg, pitch=pitch)
                r.update(base)
            except Exception as e:
                r = {**base, "STATUS": "failed", "ERROR": str(e)}
            fd_rows.append(r)
            row.update({k: v for k, v in r.items() if k not in base})
            row["FINAL_DOMAIN_STATUS"] = row.pop("STATUS", "")
            row["FINAL_DOMAIN_FIGURE"] = f"final_domain/{r['FIGURE_FILE']}" if r.get("FIGURE_FILE") else ""
            row.pop("FIGURE_FILE", None)
            if "ERROR" in row:
                row["FINAL_DOMAIN_ERROR"] = row.pop("ERROR")
        if ftobi:
            if tg is None:
                ft = {**base, "STATUS": "skipped", "ERROR": "no alignment (F_ToBI needs words and syllables)"}
            else:
                try:
                    ft, sdf = annotate(w, tg, ft_dir, cfg, fixed_range, pitch=pitch)
                    ft.update(base)
                    syl_frames.append(sdf)
                except Exception as e:
                    ft = {**base, "STATUS": "failed", "ERROR": str(e)}
            ft_rows.append(ft)
            for k, v in ft.items():
                if k in base or (k in SHARED and k in row):
                    continue
                key = {"STATUS": "FTOBI_STATUS", "FIGURE_FILE": "FTOBI_FIGURE", "ERROR": "FTOBI_ERROR",
                       "TEXTGRID_IN": "FTOBI_TEXTGRID_IN"}.get(k, k)
                if key in row and key not in ("FTOBI_STATUS",):
                    key = "FTOBI_" + key
                row[key] = f"ftobi/{v}" if key == "FTOBI_FIGURE" and v else v
            for k in SHARED:
                if k not in row and k in ft:
                    row[k] = ft[k]
        # the 28-column dataset row (needs the final-domain values)
        fd_vals = fd_rows[-1] if final_domain and fd_rows else {}
        drow, warns = dataset_row(w, tg, x, sr, pitch, fd_vals, speakers)
        ds_rows.append(drow)
        ds_warn += [{"AUDIO_FILE": w.name, "WARNING": m} for m in warns]
        all_rows.append(row)

    # per-tool outputs, in the same format as the separate commands
    if final_domain and fd_rows:
        fd = pd.DataFrame(fd_rows)
        fd_dir.mkdir(parents=True, exist_ok=True)
        fd.to_csv(fd_dir / "final_domain_cues.csv", index=False, encoding=CSV_ENCODING)
        write_praat_check(fd, fd_dir)
        with pd.ExcelWriter(fd_dir / "final_domain_cues.xlsx", engine="openpyxl") as xw:
            fd.to_excel(xw, sheet_name="FINAL_DOMAIN_CUES", index=False)
    else:
        fd = pd.DataFrame()
    ftdf = write_tables(ft_rows, syl_frames, cfg, ft_dir) if ftobi and ft_rows else pd.DataFrame()
    sdf = pd.concat(syl_frames, ignore_index=True) if syl_frames else pd.DataFrame()

    # combined workbook
    all_df = pd.DataFrame(all_rows)
    # The two analyses classify the end of the utterance differently: the final-domain contour uses
    # the fitted SLOPE (rate, ST/s), F_ToBI's boundary tone uses the SIZE of the movement (ST). A
    # small, slow rise can be 'rise' for one and level ('?') for the other: flag those for checking.
    def agree(r):
        c, t = str(r.get("CONTOUR_CLASS", "")), str(r.get("T_PCT", ""))
        if c in ("", "nan", "None") or t in ("", "nan"):
            return ""
        if c in ("rise-fall", "fall-rise"):
            ts = str(r.get("T_STAR", ""))
            ok = (c == "rise-fall" and ts.startswith(("H", "L H")) and t.startswith("L")) or \
                 (c == "fall-rise" and ts.startswith("L") and t.startswith("H"))
            return ("agree" if "?" not in t + ts else "agree (F_ToBI label uncertain)") if ok else f"{c} vs {ts} {t}: check"
        want = {"rise": "H", "fall": "L"}.get(c)
        if want is None:
            return "plateau vs " + t.rstrip("?") + (" (check)" if "?" not in t else "")
        if t.lstrip("!").startswith(want):
            return "agree" if "?" not in t else "agree (F_ToBI label uncertain)"
        return f"{c} vs {t}: check"
    if "CONTOUR_CLASS" in all_df and "T_PCT" in all_df:
        all_df["CONTOUR_VS_BOUNDARY_TONE"] = all_df.apply(agree, axis=1)
    first = ["TOKEN_ID", "SPEAKER_ID", "SENTENCE_ID", "AUDIO_FILE", "ALIGNMENT_SOURCE", "TEXT_SOURCE",
             "FINAL_DOMAIN_STATUS", "CONTOUR_CLASS", "FINAL_SLOPE_ST", "F0_CHANGE_ST", "FINAL_SYLLABLE_DURATION",
             "QC_OCTAVE_JUMP", "FINAL_VOWEL_F0_COVERAGE", "QC_FINAL_VOWEL_LOW_F0", "FTOBI_STATUS", "NUCLEAR", "CONTOUR_VS_BOUNDARY_TONE", "AP_PHRASING", "BREAKS", "TONES", "N_UNCERTAIN",
             "NUC_EDGE_TONE", "NUC_EDGE_PREDICTED", "NUC_EDGE_TEST", "QC_WARNINGS",
             "FINAL_DOMAIN_FIGURE", "FTOBI_FIGURE"]
    all_df = all_df[[c for c in first if c in all_df.columns] + [c for c in all_df.columns if c not in first]]
    params = [{"STEP": "run", "PARAMETER": "alignment mode", "VALUE": align + (" + realign (every file aligned with WebMAUS)" if realign else "")},
              {"STEP": "run", "PARAMETER": "WebMAUS language", "VALUE": language},
              {"STEP": "pitch", "PARAMETER": "engine", "VALUE": "Praat (Parselmouth)" if HAVE_PARSELMOUTH else "built-in"},
              {"STEP": "pitch", "PARAMETER": "range", "VALUE": f"fixed {fixed_range}" if fixed_range else
               f"two-pass adaptive (De Looze & Hirst 2008): floor 0.75 x Q25, ceiling 1.5 x Q75 of pass-1 F0, "
               f"pooled per {pitch_method}"},
              {"STEP": "pitch", "PARAMETER": "first pass", "VALUE": "by sex: men 60-300 Hz, women 100-500 Hz, "
               "unknown 60-600 Hz" if first_pass_by_sex and speakers is not None else "60-600 Hz for everyone"},
              {"STEP": "final domain", "PARAMETER": "syllable tier", "VALUE": tier},
              {"STEP": "final domain", "PARAMETER": "slope threshold (ST/s)", "VALUE": slope_threshold}]
    params += [{"STEP": "F_ToBI", "PARAMETER": k, "VALUE": v} for k, v in asdict(cfg).items()]
    out.mkdir(parents=True, exist_ok=True)
    all_df.to_csv(out / "intonasphere_results.csv", index=False, encoding=CSV_ENCODING)
    al_log = pd.DataFrame([{"AUDIO_FILE": a.wav.name, "TEXTGRID": str(a.textgrid) if a.textgrid else "",
                            "TEXT_SOURCE": a.text_source, "ALIGNMENT_SOURCE": a.alignment_source,
                            "STATUS": a.status, "MESSAGE": a.message, "TEXT": a.text} for a in aligned])
    ds = pd.DataFrame(ds_rows, columns=DATASET_COLUMNS)
    ds.to_csv(out / "intonasphere_dataset.csv", index=False, encoding=CSV_ENCODING)
    if sp_info:
        params += [{"STEP": "dataset", "PARAMETER": "speaker table", "VALUE": f"{sp_info['file']} [{sp_info['sheet']}]"},
                   {"STEP": "dataset", "PARAMETER": "median age (all speakers in table)", "VALUE": sp_info["median_age"]},
                   {"STEP": "dataset", "PARAMETER": "AGE_GROUP rule", "VALUE": sp_info["age_rule"]},
                   {"STEP": "dataset", "PARAMETER": "speaker-code corrections",
                    "VALUE": ", ".join(f"{k} -> {v}" for k, v in sp_info["code_fixes"].items()) or "none"}]
    if not final_domain:
        ds_warn.append({"AUDIO_FILE": "(all)", "WARNING": "final-domain step off: CONTOUR_CLASS, FINAL_* and ALIGNMENT_TIME are empty"})
    with pd.ExcelWriter(out / "intonasphere_results.xlsx", engine="openpyxl") as xw:
        pd.DataFrame(README_ROWS, columns=["SHEET / TOPIC", "DESCRIPTION"]).to_excel(xw, sheet_name="README", index=False)
        ds.to_excel(xw, sheet_name="DATASET", index=False)
        codebook_df().to_excel(xw, sheet_name="CODEBOOK", index=False)
        if speakers is not None:
            speakers.reset_index().to_excel(xw, sheet_name="SPEAKERS", index=False)
        pd.DataFrame(ds_warn, columns=["AUDIO_FILE", "WARNING"]).to_excel(xw, sheet_name="DATASET_WARNINGS", index=False)
        all_df.to_excel(xw, sheet_name="ALL_TOKENS", index=False)
        if len(fd): fd.to_excel(xw, sheet_name="FINAL_DOMAIN", index=False)
        if len(ftdf): ftdf.to_excel(xw, sheet_name="FTOBI_TOKENS", index=False)
        if len(sdf): sdf.to_excel(xw, sheet_name="FTOBI_SYLLABLES", index=False)
        al_log.to_excel(xw, sheet_name="ALIGNMENT", index=False)
        pd.DataFrame(params).to_excel(xw, sheet_name="PARAMETERS", index=False)
        for ws in xw.book.worksheets:                     # readable column widths + frozen header
            ws.freeze_panes = "B2" if ws.title not in ("README", "PARAMETERS") else "A2"
            for col in ws.columns:
                width = max(len(str(c.value)) if c.value is not None else 0 for c in list(col)[:50])
                ws.column_dimensions[col[0].column_letter].width = min(max(10, width + 2), 60)

    n = len(all_df)
    ok_fd = int((all_df.get("FINAL_DOMAIN_STATUS") == "completed").sum()) if "FINAL_DOMAIN_STATUS" in all_df else 0
    ok_ft = int((all_df.get("FTOBI_STATUS") == "completed").sum()) if "FTOBI_STATUS" in all_df else 0
    print(f"\nDone in {time.time() - t0:.0f} s: {n} recordings  |  final-domain graphs: {ok_fd}  |  "
          f"F_ToBI graphs: {ok_ft}\n  -> {out / 'intonasphere_results.xlsx'}")
    return all_df


def main():
    ap = argparse.ArgumentParser(description="IntonaSphere AI: alignment + final-domain graph + F_ToBI graph, "
                                             "one row per recording")
    ap.add_argument("--folder", required=True, help="Folder with .wav files (+ optional .TextGrid / .txt)")
    ap.add_argument("--out", default="outputs")
    ap.add_argument("--align", choices=["none", "pfc", "any"], default="any",
                    help="none: use only existing TextGrids; pfc: WebMAUS for PFC names and .txt files; "
                         "any: also speech recognition for other recordings")
    ap.add_argument("--no-final-domain", action="store_true", help="skip the final-domain graph")
    ap.add_argument("--no-ftobi", action="store_true", help="skip the F_ToBI graph")
    ap.add_argument("--realign", action="store_true",
                    help="align EVERY WAV with WebMAUS (PFC text from the file name, or x.txt), ignoring existing "
                         "TextGrids; they are only recorded, for comparison with modules.compare_runs")
    ap.add_argument("--tier", default="MAS")
    ap.add_argument("--slope-threshold", type=float, default=1.5)
    ap.add_argument("--pitch-range", nargs=2, type=float, metavar=("FLOOR", "CEILING"))
    ap.add_argument("--language", default="fra-FR")
    ap.add_argument("--asr-model", default="small")
    ap.add_argument("--svg", action="store_true")
    ap.add_argument("--speakers", default=None, help="speaker table (.xlsx or .csv): Speaker code, Site, Country, "
                                                     "Region, Sex, Age")
    ap.add_argument("--pitch-method", choices=["speaker", "file"], default="speaker",
                    help="pool the first pitch pass per speaker (default) or per file (previous behaviour)")
    ap.add_argument("--no-sex-first-pass", action="store_true",
                    help="first pitch pass 60-600 Hz for everyone instead of by sex")
    ap.add_argument("--speakers-sheet", default=None, help="sheet of the speaker table (default: found automatically)")
    ap.add_argument("--age-tie", choices=["Older", "Younger"], default="Older",
                    help="group of a speaker whose age equals the median (default Older)")
    ap.add_argument("--speaker-fix", action="append", default=[], metavar="TABLE_CODE=CORRECT_CODE",
                    help="correct a speaker code in the table, e.g. --speaker-fix 81acc1=81aac1 (repeatable)")
    a = ap.parse_args()
    run(user_path(a.folder), user_path(a.out), a.align, not a.no_final_domain, not a.no_ftobi, FToBIConfig(),
        a.slope_threshold, a.tier, tuple(a.pitch_range) if a.pitch_range else None, a.language,
        a.asr_model, a.svg, user_path(a.speakers), a.age_tie,
        dict(f.split("=", 1) for f in a.speaker_fix), a.speakers_sheet, a.pitch_method,
        not a.no_sex_first_pass, a.realign)


if __name__ == "__main__":
    main()
