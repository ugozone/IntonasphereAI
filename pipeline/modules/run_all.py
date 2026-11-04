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
  6. token selection: keep / exclude / check, with the reason, for every token, following the
     quality-control rules of the methodology (modules/selection.py; manual decisions are read
     from manual_overrides.csv and never overwritten)

    python -m modules.run_all --folder data/wavs --out outputs
    python -m modules.run_all --folder data/wavs --out outputs --no-ftobi
    python -m modules.run_all --folder data/wavs --out outputs --no-final-domain --align none

Output layout
    outputs/
      intonasphere_results.xlsx   README / ALL_TOKENS / FINAL_DOMAIN / FTOBI_TOKENS /
                                  FTOBI_SYLLABLES / ALIGNMENT / PARAMETERS
      intonasphere_results.csv    the ALL_TOKENS sheet
      intonasphere_selection.csv  the SELECTION sheet (decision and reason for every token)
      manual_overrides.csv        your manual decisions (created empty once, never overwritten)
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

from .final_domain_visualizer import (RESCUE_FLOOR_HZ, RESCUE_MAX_JUMP_ST, RESCUE_CONTEXT_S, RESCUE_MIN_COVERAGE,
                                      HAVE_PARSELMOUTH, load_wav, adaptive_pitch, process_token,
                                      write_praat_check)
from .ftobi_annotator import FToBIConfig, annotate, write_tables
from .auto_align import ensure_alignments
from .pitch_range import plan_ranges
from .dataset_sheet import (DATASET_COLUMNS, load_speakers, dataset_row, codebook_df)
from .i18n import t as tr, add_lang_option
from . import selection as selection_rule

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
    ("SELECTION", "Keep / exclude decision and its reason for every token (and every planned speaker x sentence "
                  "without a recording). SELECTION_DECISION = your MANUAL_DECISION if you gave one, else AUTO_DECISION."),
    ("TOKEN_FLOW", "Tokens per decision, by sentence; speakers in the complete-case set (Q1-Q3) and the RQ4 set (S4)."),
    ("TOKEN_FLOW_BY_SITE", "Included, flagged, tune-only, excluded and pending tokens by site and sentence, with the "
                           "re-tracked (low floor) and creaky final syllables."),
    ("Tune vs measures", "USE_FOR_TUNE = yes for Include and 'Include – tune only' (creaky or low ending that can be "
                         "labelled); USE_FOR_MEASURES = yes for Include only. SENSITIVITY_SET = Include, not flagged, "
                         "not re-tracked: run the main analyses again on it."),
    ("Manual decisions", "Edit manual_overrides.csv (TOKEN_ID, CHECKED, MANUAL_DECISION, MANUAL_NOTE), then "
                         "python -m modules.selection --results <this workbook> to update the decisions without re-measuring."),
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
        raise SystemExit(tr('These result files are open in another program (e.g. Excel) and cannot be overwritten:\n  ') + "\n  ".join(locked) + tr('\nClose them, or choose another --out folder, then run the command again.'))


def run(folder: Path, out: Path, align: str = "any", final_domain: bool = True, ftobi: bool = True,
        cfg: Optional[FToBIConfig] = None, slope_threshold: float = 1.5, tier: str = "MAS",
        fixed_range: Optional[Tuple[float, float]] = None, language: str = "fra-FR",
        asr_model: str = "small", svg: bool = False, speakers_file: Optional[Path] = None,
        age_tie: str = "Older", speaker_fixes: Optional[Dict[str, str]] = None,
        speakers_sheet: Optional[str] = None, pitch_method: str = "speaker",
        first_pass_by_sex: bool = True, realign: bool = False, measure_domain: str = "final",
        overrides_file: Optional[Path] = None, plan_s4: bool = True) -> pd.DataFrame:
    cfg = cfg or FToBIConfig()
    folder, out = Path(folder), Path(out)
    fd_dir, ft_dir, al_dir = out / "final_domain", out / "ftobi", out / "aligned"
    _check_outputs_writable(out, fd_dir, ft_dir)
    t0 = time.time()
    print(tr('IntonaSphere AI  |  folder: {folder}  |  alignment: {align}  |  final-domain: {value}  |  F_ToBI: {value2}  |  pitch: {value3}', folder=folder, align=align, value=tr('on') if final_domain else tr('off'), value2=tr('on') if ftobi else tr('off'), value3='Praat (Parselmouth)' if HAVE_PARSELMOUTH else tr('built-in Praat-style tracker')))
    speakers, sp_info = None, {}
    if speakers_file:
        speakers, sp_info = load_speakers(Path(speakers_file), age_tie, speaker_fixes, speakers_sheet)
        print(tr('Speaker table: {file} [{sheet}], {speakers} speakers; AGE_GROUP rule: {age_rule}', file=sp_info['file'], sheet=sp_info['sheet'], speakers=sp_info['speakers'], age_rule=sp_info['age_rule']))
    ds_rows: List[Dict] = []
    ds_warn: List[Dict] = []
    print(tr('Step 1/2  alignment'))
    if realign:
        print(tr('Re-aligning EVERY file with WebMAUS (your TextGrids are kept only for comparison)'))
    aligned = ensure_alignments(folder, al_dir, align, language, asr_model, realign=realign)
    ranges: Dict[str, Dict] = {}
    if not fixed_range:
        print(tr('Pitch ranges: two-pass, pooled per {pitch_method}{value}', pitch_method=tr(pitch_method), value=tr(', first pass by sex') if first_pass_by_sex and speakers is not None else ''))
        ranges = plan_ranges([a.wav for a in aligned], pitch_method, speakers, first_pass_by_sex)
    print(tr('Step 2/2  analysis'))
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
            note = tr('  -> final-domain with automatic segmentation, F_ToBI skipped [{message}]', message=a.message[:90])
        print(tr('[{i}/{n_aligned}] {name:24s} textgrid: {value}{note}', i=i, n_aligned=len(aligned), name=w.name, value=tg.name if tg else 'none', note=note))
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
                                  fixed_range=fixed_range, svg=svg, pitch=pitch,
                                  measure_domain=measure_domain)
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
             "QC_OCTAVE_JUMP", "FINAL_VOWEL_F0_COVERAGE", "QC_FINAL_VOWEL_LOW_F0", "LOW_FLOOR_RESCUE", "CREAKY_FINAL", "RESCUE_NOTE", "FTOBI_STATUS", "NUCLEAR", "CONTOUR_VS_BOUNDARY_TONE", "AP_PHRASING", "BREAKS", "TONES", "N_UNCERTAIN",
             "NUC_EDGE_TONE", "NUC_EDGE_PREDICTED", "NUC_EDGE_TEST", "QC_WARNINGS",
             "FINAL_DOMAIN_FIGURE", "FTOBI_FIGURE"]
    all_df = all_df[[c for c in first if c in all_df.columns] + [c for c in all_df.columns if c not in first]]
    params = [{"STEP": "run", "PARAMETER": "input folder", "VALUE": str(folder)},
              {"STEP": "run", "PARAMETER": "alignment mode", "VALUE": align + (" + realign (every file aligned with WebMAUS)" if realign else "")},
              {"STEP": "run", "PARAMETER": "WebMAUS language", "VALUE": language},
              {"STEP": "pitch", "PARAMETER": "engine", "VALUE": "Praat (Parselmouth)" if HAVE_PARSELMOUTH else "built-in"},
              {"STEP": "pitch", "PARAMETER": "range", "VALUE": f"fixed {fixed_range}" if fixed_range else
               f"two-pass adaptive (De Looze & Hirst 2008): floor 0.75 x Q25, ceiling 1.5 x Q75 of pass-1 F0, "
               f"pooled per {pitch_method}"},
              {"STEP": "pitch", "PARAMETER": "first pass", "VALUE": "by sex: men 60-300 Hz, women 100-500 Hz, "
               "unknown 60-600 Hz" if first_pass_by_sex and speakers is not None else "60-600 Hz for everyone"},
              {"STEP": "final domain", "PARAMETER": "syllable tier", "VALUE": tier},
              {"STEP": "final domain", "PARAMETER": "low-floor rescue", "VALUE":
               f"when the final syllable has < 3 voiced frames or F0 on < {RESCUE_MIN_COVERAGE:.0%} of its vowel: "
               f"re-track that syllable only with a {RESCUE_FLOOR_HZ:.0f} Hz floor and the speaker ceiling; "
               f"accepted only if no jump >= {RESCUE_MAX_JUMP_ST:.0f} ST from {RESCUE_CONTEXT_S:.1f} s before the "
               f"syllable (LOW_FLOOR_RESCUE); otherwise CREAKY_FINAL"},
              {"STEP": "final domain", "PARAMETER": "slope threshold (ST/s)", "VALUE": slope_threshold},
              {"STEP": "final domain", "PARAMETER": "measure domain", "VALUE":
               "final syllable + whole phrase (PHRASE_* columns)" if measure_domain == "both" else "final syllable only"}]
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
    # token selection (quality control); manual decisions from the overrides file
    ov_path = selection_rule.ensure_overrides_file(Path(overrides_file) if overrides_file else out / "manual_overrides.csv")
    sel = selection_rule.select(ds, all_df, speakers, selection_rule.read_overrides(ov_path), plan_s4=plan_s4)
    sel.to_csv(out / "intonasphere_selection.csv", index=False, encoding=CSV_ENCODING)
    sel_flow, sel_site = selection_rule.token_flow(sel), selection_rule.token_flow_by_site(sel)
    params += selection_rule.parameters_rows()
    params.append({"STEP": "selection", "PARAMETER": "overrides file", "VALUE": str(ov_path)})
    with pd.ExcelWriter(out / "intonasphere_results.xlsx", engine="openpyxl") as xw:
        pd.DataFrame([(tr(k), tr(v)) for k, v in README_ROWS], columns=["SHEET / TOPIC", "DESCRIPTION"]).to_excel(xw, sheet_name="README", index=False)
        ds.to_excel(xw, sheet_name="DATASET", index=False)
        codebook_df().to_excel(xw, sheet_name="CODEBOOK", index=False)
        if speakers is not None:
            speakers.reset_index().to_excel(xw, sheet_name="SPEAKERS", index=False)
        pd.DataFrame(ds_warn, columns=["AUDIO_FILE", "WARNING"]).to_excel(xw, sheet_name="DATASET_WARNINGS", index=False)
        all_df.to_excel(xw, sheet_name="ALL_TOKENS", index=False)
        if len(fd): fd.to_excel(xw, sheet_name="FINAL_DOMAIN", index=False)
        if len(ftdf): ftdf.to_excel(xw, sheet_name="FTOBI_TOKENS", index=False)
        if len(sdf): sdf.to_excel(xw, sheet_name="FTOBI_SYLLABLES", index=False)
        sel.to_excel(xw, sheet_name="SELECTION", index=False)
        sel_flow.to_excel(xw, sheet_name="TOKEN_FLOW", index=False)
        sel_site.to_excel(xw, sheet_name="TOKEN_FLOW_BY_SITE", index=False)
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
    n_inc = int(sel["SELECTION_DECISION"].isin(selection_rule.USABLE_FOR_TUNE).sum())
    n_tune = int(sel["SELECTION_DECISION"].eq(selection_rule.TUNE_ONLY).sum())
    print(tr('\nDone in {value:.0f} s: {n} recordings  |  final-domain graphs: {ok_fd}  |  F_ToBI graphs: {ok_ft}  |  tokens included: {n_inc}, of which tune only: {n_tune} (see SELECTION / TOKEN_FLOW)\n  -> {value2}', value=time.time() - t0, n=n, ok_fd=ok_fd, ok_ft=ok_ft, n_inc=n_inc, n_tune=n_tune, value2=out / 'intonasphere_results.xlsx'))
    return all_df


def main():
    ap = argparse.ArgumentParser(description=tr('IntonaSphere AI: alignment + final-domain graph + F_ToBI graph, one row per recording'))
    add_lang_option(ap)
    ap.add_argument("--folder", required=True, help=tr('Folder with .wav files (+ optional .TextGrid / .txt)'))
    ap.add_argument("--out", default="outputs")
    ap.add_argument("--align", choices=["none", "pfc", "any"], default="any",
                    help=tr('none: use only existing TextGrids; pfc: WebMAUS for PFC names and .txt files; any: also speech recognition for other recordings'))
    ap.add_argument("--no-final-domain", action="store_true", help=tr('skip the final-domain graph'))
    ap.add_argument("--no-ftobi", action="store_true", help=tr('skip the F_ToBI graph'))
    ap.add_argument("--realign", action="store_true",
                    help=tr('align EVERY WAV with WebMAUS (PFC text from the file name, or x.txt), ignoring existing TextGrids; they are only recorded, for comparison with modules.compare_runs'))
    ap.add_argument("--tier", default="MAS")
    ap.add_argument("--slope-threshold", type=float, default=1.5)
    ap.add_argument("--pitch-range", nargs=2, type=float, metavar=("FLOOR", "CEILING"))
    ap.add_argument("--language", default="fra-FR",
                    help=tr("WebMAUS alignment language (default fra-FR); the language of messages is --lang"))
    ap.add_argument("--asr-model", default="small")
    ap.add_argument("--svg", action="store_true")
    ap.add_argument("--speakers", default=None, help=tr('speaker table (.xlsx or .csv): Speaker code, Site, Country, Region, Sex, Age'))
    ap.add_argument("--pitch-method", choices=["speaker", "file"], default="speaker",
                    help=tr('pool the first pitch pass per speaker (default) or per file (previous behaviour)'))
    ap.add_argument("--no-sex-first-pass", action="store_true",
                    help=tr('first pitch pass 60-600 Hz for everyone instead of by sex'))
    ap.add_argument("--speakers-sheet", default=None, help=tr('sheet of the speaker table (default: found automatically)'))
    ap.add_argument("--age-tie", choices=["Older", "Younger"], default="Older",
                    help=tr('group of a speaker whose age equals the median (default Older)'))
    ap.add_argument("--speaker-fix", action="append", default=[], metavar="TABLE_CODE=CORRECT_CODE",
                    help=tr('correct a speaker code in the table, e.g. --speaker-fix 81acc1=81aac1 (repeatable)'))
    ap.add_argument("--measure", choices=["final", "both"], default="final",
                    help=tr('final = final-syllable cues only (default); both = also measure the whole phrase (PHRASE_F0_ONSET/MAX/MIN/OFFSET_HZ, PHRASE_F0_RANGE_ST, PHRASE_F0_CHANGE_ST, PHRASE_SLOPE_ST)'))
    ap.add_argument("--overrides", default=None,
                    help=tr('CSV of manual token decisions (default: OUT/manual_overrides.csv, created empty if missing)'))
    ap.add_argument("--no-plan-s4", action="store_true",
                    help=tr('do not list a pending S4 row for speakers in the speaker table who have no S4 recording'))
    a = ap.parse_args()
    run(user_path(a.folder), user_path(a.out), a.align, not a.no_final_domain, not a.no_ftobi, FToBIConfig(),
        a.slope_threshold, a.tier, tuple(a.pitch_range) if a.pitch_range else None, a.language,
        a.asr_model, a.svg, user_path(a.speakers), a.age_tie,
        dict(f.split("=", 1) for f in a.speaker_fix), a.speakers_sheet, a.pitch_method,
        not a.no_sex_first_pass, a.realign, a.measure, user_path(a.overrides), not a.no_plan_s4)


if __name__ == "__main__":
    main()
