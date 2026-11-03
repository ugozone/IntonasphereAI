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

from . import user_path, CSV_ENCODING

import argparse
import importlib
import platform
import shutil
import sys
import time
import traceback
from pathlib import Path
from .i18n import t as tr, add_lang_option

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
            log("PASS", tr('package {m}', m=m), getattr(mod, "__version__", ""))
        except Exception:
            log("FAIL", tr('package {m}', m=m), tr('pip install {m}', m=m))
            ok = False
    for m, why in opt.items():
        try:
            mod = importlib.import_module(m)
            log("PASS", tr('package {m}', m=m), getattr(mod, "__version__", ""))
        except Exception:
            log("WARN", tr('package {m} not installed', m=m), why)
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
        log("SKIP", tr('WebMAUS'), tr('no WAV with a .txt or a PFC name in the folder'))
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
        log("PASS" if not miss else "FAIL", tr('WebMAUS alignment of {name} ({value:.0f} s)', name=w.name, value=time.time() - t0),
            tr('service: {how}; tiers: {join}', how=how, join=', '.join(names)) + (tr('; MISSING {miss}', miss=miss) if miss else ""))
        mau = tg.get("MAU")
        foreign = sorted({iv.label for iv in mau.intervals if iv.label in {"I", "aU", "?", "e:", "i:", "a:"}}) if mau else []
        log("WARN" if foreign else "PASS", tr('WebMAUS used the French model'),
            tr('non-French symbols {foreign}', foreign=foreign) if foreign else tr('no German/English SAMPA symbols'))
    except Exception as e:
        log("FAIL", tr('WebMAUS alignment'), f"{e}"[:400] + tr('  (internet? firewall? BAS server down? -> files WITH a TextGrid still work; try again later or use --align none)'))


def check_asr(folder: Path):
    try:
        importlib.import_module("faster_whisper")
    except Exception:
        log("SKIP", tr('speech recognition'), tr('faster-whisper not installed'))
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
        log("PASS", tr('speech recognition on {name} ({value:.0f} s)', name=w.name, value=time.time() - t0), f"'{txt[:90]}'"
            + (tr("  | expected: '{value}'", value=ref[:60]) if ref else ""))
    except Exception as e:
        log("FAIL", tr('speech recognition'), str(e)[:300])


def check_pipeline(folder: Path, out: Path, align: str):
    from .run_all import run
    from .final_domain_visualizer import read_textgrid
    import pandas as pd
    try:
        df = run(folder, out, align=align)
    except Exception:
        log("FAIL", tr('pipeline modules.run_all'), traceback.format_exc()[-600:])
        return
    n = len(df)
    fd_ok = int((df.get("FINAL_DOMAIN_STATUS") == "completed").sum())
    ft_ok = int((df.get("FTOBI_STATUS") == "completed").sum())
    log("PASS" if fd_ok == n else "WARN", tr('final-domain graphs'), f"{fd_ok}/{n}")
    log("PASS" if ft_ok == n else "WARN", tr('F_ToBI graphs'), f"{ft_ok}/{n}"
        + ("" if ft_ok == n else tr('  (files without alignment are skipped: see ALIGNMENT sheet)')))
    for _, r in df.iterrows():
        if r.get("FINAL_DOMAIN_STATUS") != "completed" or r.get("FTOBI_STATUS") != "completed":
            note = r.get("FTOBI_ERROR") if isinstance(r.get("FTOBI_ERROR"), str) else r.get("ALIGNMENT_NOTE", "")
            log("INFO", f"  {r['AUDIO_FILE']}", tr('alignment={get} text={get2} final-domain={get3} F_ToBI={get4} {value}', get=r.get('ALIGNMENT_SOURCE'), get2=r.get('TEXT_SOURCE'), get3=r.get('FINAL_DOMAIN_STATUS'), get4=r.get('FTOBI_STATUS'), value=str(note)[:150]))
    bad = []
    for tg in list((out / "ftobi").glob("*_ftobi.TextGrid")) + list((out / "final_domain").glob("*_cues.TextGrid")):
        try:
            read_textgrid(tg)
        except Exception as e:
            bad.append(f"{tg.name}: {e}")
    log("PASS" if not bad else "FAIL", tr('output TextGrids re-read in Praat format'), "; ".join(bad)[:300] or tr("all readable"))
    pngs = len(list(out.rglob("*.png")))
    log("PASS" if pngs else "FAIL", tr('graphs written'), tr('{pngs} PNG files', pngs=pngs))
    try:
        sheets = pd.ExcelFile(out / "intonasphere_results.xlsx").sheet_names
        need = {"README", "ALL_TOKENS", "ALIGNMENT", "PARAMETERS", "SELECTION", "TOKEN_FLOW"}
        log("PASS" if need <= set(sheets) else "FAIL", tr('workbook'), ", ".join(sheets))
    except Exception as e:
        log("FAIL", tr('workbook'), str(e))
    try:
        from .selection import SELECTION_COLUMNS, DECISION_ORDER
        sel = pd.read_excel(out / "intonasphere_results.xlsx", sheet_name="SELECTION")
        ok = list(sel.columns) == SELECTION_COLUMNS and len(sel) >= n and \
            sel["SELECTION_DECISION"].isin(DECISION_ORDER).all() and sel["AUTO_REASON"].notna().all()
        log("PASS" if ok else "FAIL", tr('token selection'),
            ", ".join(f"{k}: {v}" for k, v in sel["SELECTION_DECISION"].value_counts().items()))
    except Exception as e:
        log("FAIL", tr('token selection'), str(e))
    if "CONTOUR_VS_BOUNDARY_TONE" in df:
        chk = df["CONTOUR_VS_BOUNDARY_TONE"].astype(str).str.contains("check").sum()
        log("INFO", tr('contour vs boundary tone'), tr("{chk} file(s) marked 'check' (look at them in Praat)", chk=chk))


def main():
    ap = argparse.ArgumentParser(description=tr('IntonaSphere AI self-test'))
    add_lang_option(ap)
    ap.add_argument("--folder", required=True, help=tr('small test folder (WAVs, optional TextGrids / .txt)'))
    ap.add_argument("--out", default="outputs_selftest")
    ap.add_argument("--align", choices=["none", "pfc", "any"], default="any")
    ap.add_argument("--skip-network", action="store_true", help=tr('do not contact WebMAUS'))
    a = ap.parse_args()
    folder, out = user_path(a.folder), user_path(a.out)
    if not any(p.suffix.lower() == ".wav" for p in folder.glob("*")) and (folder / "make_test_data.py").exists():
        import runpy
        runpy.run_path(str(folder / "make_test_data.py"), run_name="__main__")
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    log("INFO", tr('system'), tr('Python {value} on {platform}', value=sys.version.split()[0], platform=platform.platform()))
    log("INFO", tr('test folder'), tr('{resolve}  ({n_items} WAV, {n_items2} TextGrid, {n_items3} txt)', resolve=folder.resolve(), n_items=len(list(folder.glob('*.wav'))), n_items2=len(list(folder.glob('*.TextGrid'))), n_items3=len(list(folder.glob('*.txt')))))
    print(tr('\n1. packages')); ok = check_packages()
    if not ok:
        log("FAIL", tr('stopping'), tr('install the missing packages first: pip install -r requirements.txt'))
    else:
        print(tr('\n2. pitch engine'))
        from .final_domain_visualizer import HAVE_PARSELMOUTH
        log("PASS" if HAVE_PARSELMOUTH else "WARN", tr('pitch engine'),
            tr('Praat via Parselmouth') if HAVE_PARSELMOUTH else tr('built-in tracker (pip install praat-parselmouth)'))
        print(tr('\n3. WebMAUS'))
        if a.skip_network or a.align == "none":
            log("SKIP", tr('WebMAUS'), tr('--skip-network / --align none'))
        else:
            check_webmaus(folder, out)
        print(tr('\n4. speech recognition'))
        if a.align == "any":
            check_asr(folder)
        else:
            log("SKIP", tr('speech recognition'), tr('--align {align}', align=a.align))
        print(tr('\n5-6. full pipeline'))
        check_pipeline(folder, out / "run", "none" if a.skip_network else a.align)
    fails = sum(l.startswith("[FAIL") for l in LINES)
    warns = sum(l.startswith("[WARN") for l in LINES)
    summary = tr('\nRESULT: {value}, {warns} warning(s)', value=tr('ALL PASSED') if not fails else tr('{n} FAILED', n=fails), warns=warns)
    print(summary)
    (out / "selftest_report.txt").write_text("\n".join(LINES) + "\n" + summary + "\n", encoding="utf-8")
    print(tr('Report: {value}   Outputs to inspect: {value2}', value=out / 'selftest_report.txt', value2=out / 'run'))
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
