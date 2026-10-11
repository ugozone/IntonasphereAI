"""
IntonaSphere AI - self-test on your own computer
================================================

    python -m modules.selftest --folder test_data

If the folder has no WAV files, two synthetic test recordings are created in it first
(test_data/make_test_data.py; no real speaker or corpus data, so the repository can be public):
    synth_question.wav  + synth_question.TextGrid    (WAV + TextGrid route; F_ToBI)
    synth_statement.wav + synth_statement.txt        (WAV + .txt -> WebMAUS route)
To test with real speech, point --folder at a small folder of your own recordings, e.g.
    xxx1tw1.wav + xxx1tw1.TextGrid          (WAV + your TextGrid)
    xxx1tw2.wav                             (PFC name, no TextGrid -> WebMAUS with PFC text)
    my_sentence.wav + my_sentence.txt       (any name + text file -> WebMAUS with your text)
    other_recording.wav                     (nothing else -> speech recognition -> WebMAUS)

It checks, in order, and writes selftest_report.txt (send it back if anything fails):
  1. Python and the required / optional packages
  2. Praat pitch through Parselmouth (otherwise the built-in tracker is used)
  3. Internet access to WebMAUS (one real alignment, French)
  4. Speech recognition (only if faster-whisper is installed)
  5. The full pipeline (modules.run_all) on the folder
  6. The outputs: graphs, TextGrids readable by Praat's format, workbook sheets
Nothing in the input folder is changed, except x.asr.txt files written by speech recognition.
"""
from __future__ import annotations

import argparse
import importlib
import platform
import shutil
import sys
import time
import traceback
from pathlib import Path

LINES = []


def log(status: str, what: str, detail: str = ""):
    line = f"[{status:4s}] {what}" + (f"  -  {detail}" if detail else "")
    LINES.append(line)
    print(line)


def check_packages():
    req = ["numpy", "scipy", "pandas", "matplotlib", "openpyxl", "requests"]
    opt = {"parselmouth": "praat-parselmouth (Praat's own pitch; strongly recommended)",
           "faster_whisper": "faster-whisper (only for recordings with no TextGrid and no .txt)"}
    ok = True
    for m in req:
        try:
            mod = importlib.import_module(m)
            log("PASS", f"package {m}", getattr(mod, "__version__", ""))
        except Exception:
            log("FAIL", f"package {m}", f"pip install {m}")
            ok = False
    for m, why in opt.items():
        try:
            mod = importlib.import_module(m)
            log("PASS", f"package {m}", getattr(mod, "__version__", ""))
        except Exception:
            log("WARN", f"package {m} not installed", why)
    return ok


def check_webmaus(folder: Path, work: Path):
    from .auto_align import webmaus, pfc_text, read_txt
    from .final_domain_visualizer import read_textgrid
    wavs = sorted(folder.glob("*.wav"))
    pick = None
    for w in wavs:
        t = read_txt(w.with_suffix(".txt")) if w.with_suffix(".txt").exists() else pfc_text(w)
        if t:
            pick = (w, t); break
    if pick is None:
        log("SKIP", "WebMAUS", "no WAV with a .txt or a PFC name in the folder")
        return
    w, t = pick
    dest = work / f"{w.stem}_webmaus_test.TextGrid"
    t0 = time.time()
    try:
        how = webmaus(w, t, dest, retries=1)
        tg = read_textgrid(dest)
        names = [x.name for x in tg.tiers]
        need = ["ORT-MAU", "MAU", "MAS"]
        miss = [n for n in need if n not in names]
        log("PASS" if not miss else "FAIL", f"WebMAUS alignment of {w.name} ({time.time() - t0:.0f} s)",
            f"service: {how}; tiers: {', '.join(names)}" + (f"; MISSING {miss}" if miss else ""))
        mau = tg.get("MAU")
        foreign = sorted({iv.label for iv in mau.intervals if iv.label in {"I", "aU", "?", "e:", "i:", "a:"}}) if mau else []
        log("WARN" if foreign else "PASS", "WebMAUS used the French model",
            f"non-French symbols {foreign}" if foreign else "no German/English SAMPA symbols")
    except Exception as e:
        log("FAIL", "WebMAUS alignment", f"{e}"[:400] + "  (internet? firewall? BAS server down? "
            "-> files WITH a TextGrid still work; try again later or use --align none)")


def check_asr(folder: Path):
    try:
        importlib.import_module("faster_whisper")
    except Exception:
        log("SKIP", "speech recognition", "faster-whisper not installed")
        return
    from .auto_align import asr_text, pfc_text
    wavs = [w for w in sorted(folder.glob("*.wav"))]
    if not wavs:
        return
    w = wavs[0]
    t0 = time.time()
    try:
        txt = asr_text(w)
        ref = pfc_text(w)
        log("PASS", f"speech recognition on {w.name} ({time.time() - t0:.0f} s)", f"'{txt[:90]}'"
            + (f"  | expected: '{ref[:60]}'" if ref else ""))
    except Exception as e:
        log("FAIL", "speech recognition", str(e)[:300])


def check_pipeline(folder: Path, out: Path, align: str):
    from .run_all import run
    from .final_domain_visualizer import read_textgrid
    import pandas as pd
    try:
        df = run(folder, out, align=align)
    except Exception:
        log("FAIL", "pipeline modules.run_all", traceback.format_exc()[-600:])
        return
    n = len(df)
    fd_ok = int((df.get("FINAL_DOMAIN_STATUS") == "completed").sum())
    ft_ok = int((df.get("FTOBI_STATUS") == "completed").sum())
    log("PASS" if fd_ok == n else "WARN", "final-domain graphs", f"{fd_ok}/{n}")
    log("PASS" if ft_ok == n else "WARN", "F_ToBI graphs", f"{ft_ok}/{n}"
        + ("" if ft_ok == n else "  (files without alignment are skipped: see ALIGNMENT sheet)"))
    for _, r in df.iterrows():
        if r.get("FINAL_DOMAIN_STATUS") != "completed" or r.get("FTOBI_STATUS") != "completed":
            note = r.get("FTOBI_ERROR") if isinstance(r.get("FTOBI_ERROR"), str) else r.get("ALIGNMENT_NOTE", "")
            log("INFO", f"  {r['AUDIO_FILE']}", f"alignment={r.get('ALIGNMENT_SOURCE')} text={r.get('TEXT_SOURCE')} "
                f"final-domain={r.get('FINAL_DOMAIN_STATUS')} F_ToBI={r.get('FTOBI_STATUS')} {str(note)[:150]}")
    bad = []
    for tg in list((out / "ftobi").glob("*_ftobi.TextGrid")) + list((out / "final_domain").glob("*_cues.TextGrid")):
        try:
            read_textgrid(tg)
        except Exception as e:
            bad.append(f"{tg.name}: {e}")
    log("PASS" if not bad else "FAIL", "output TextGrids re-read in Praat format", "; ".join(bad)[:300] or "all readable")
    pngs = len(list(out.rglob("*.png")))
    log("PASS" if pngs else "FAIL", "graphs written", f"{pngs} PNG files")
    try:
        sheets = pd.ExcelFile(out / "intonasphere_results.xlsx").sheet_names
        need = {"README", "ALL_TOKENS", "ALIGNMENT", "PARAMETERS"}
        log("PASS" if need <= set(sheets) else "FAIL", "workbook", ", ".join(sheets))
    except Exception as e:
        log("FAIL", "workbook", str(e))
    if "CONTOUR_VS_BOUNDARY_TONE" in df:
        chk = df["CONTOUR_VS_BOUNDARY_TONE"].astype(str).str.contains("check").sum()
        log("INFO", "contour vs boundary tone", f"{chk} file(s) marked 'check' (look at them in Praat)")


def main():
    ap = argparse.ArgumentParser(description="IntonaSphere AI self-test")
    ap.add_argument("--folder", required=True, help="small test folder (WAVs, optional TextGrids / .txt)")
    ap.add_argument("--out", default="outputs_selftest")
    ap.add_argument("--align", choices=["none", "pfc", "any"], default="any")
    ap.add_argument("--skip-network", action="store_true", help="do not contact WebMAUS")
    a = ap.parse_args()
    folder, out = Path(a.folder), Path(a.out)
    if not any(p.suffix.lower() == ".wav" for p in folder.glob("*")) and (folder / "make_test_data.py").exists():
        import runpy
        runpy.run_path(str(folder / "make_test_data.py"), run_name="__main__")
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    log("INFO", "system", f"Python {sys.version.split()[0]} on {platform.platform()}")
    log("INFO", "test folder", f"{folder.resolve()}  ({len(list(folder.glob('*.wav')))} WAV, "
        f"{len(list(folder.glob('*.TextGrid')))} TextGrid, {len(list(folder.glob('*.txt')))} txt)")
    print("\n1. packages"); ok = check_packages()
    if not ok:
        log("FAIL", "stopping", "install the missing packages first: pip install -r requirements.txt")
    else:
        print("\n2. pitch engine")
        from .final_domain_visualizer import HAVE_PARSELMOUTH
        log("PASS" if HAVE_PARSELMOUTH else "WARN", "pitch engine",
            "Praat via Parselmouth" if HAVE_PARSELMOUTH else "built-in tracker (pip install praat-parselmouth)")
        print("\n3. WebMAUS")
        if a.skip_network or a.align == "none":
            log("SKIP", "WebMAUS", "--skip-network / --align none")
        else:
            check_webmaus(folder, out)
        print("\n4. speech recognition")
        if a.align == "any":
            check_asr(folder)
        else:
            log("SKIP", "speech recognition", f"--align {a.align}")
        print("\n5-6. full pipeline")
        check_pipeline(folder, out / "run", "none" if a.skip_network else a.align)
    fails = sum(l.startswith("[FAIL") for l in LINES)
    warns = sum(l.startswith("[WARN") for l in LINES)
    summary = f"\nRESULT: {'ALL PASSED' if not fails else str(fails) + ' FAILED'}, {warns} warning(s)"
    print(summary)
    (out / "selftest_report.txt").write_text("\n".join(LINES) + "\n" + summary + "\n", encoding="utf-8")
    print(f"Report: {out / 'selftest_report.txt'}   Outputs to inspect: {out / 'run'}")


if __name__ == "__main__":
    main()
