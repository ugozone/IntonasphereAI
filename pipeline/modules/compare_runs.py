"""
IntonaSphere AI - compare two runs (e.g. your TextGrids vs. re-aligned with WebMAUS)
===================================================================================

    python -m modules.compare_runs --a ~/Desktop/pfc_results --b ~/Desktop/pfc_results_realigned

A and B are output folders of modules.run_all on the same recordings. Typical use:
    A = run with your own TextGrids           (python -m modules.run_all ... )
    B = run with every file re-aligned         (python -m modules.run_all ... --realign)
Only recordings present in both runs are compared. Reported (summary + one row per file):
  - final-syllable boundaries: start / end difference (ms), share within 20 ms and 50 ms
  - final-syllable duration difference
  - contour class: agreement and Cohen's kappa (also for the 3-way slope class)
  - fitted slope, F0 onset / peak / offset: median absolute difference, correlation
  - F_ToBI nuclear configuration: agreement and kappa
Output: compare_runs.xlsx and compare_runs_report.txt in folder B (or --out).
"""
from __future__ import annotations

from . import user_path, CSV_ENCODING

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from .validate_ftobi import kappa


def load(folder: Path) -> pd.DataFrame:
    x = folder / "intonasphere_results.xlsx"
    if x.exists():
        return pd.read_excel(x, sheet_name="ALL_TOKENS")
    c = folder / "intonasphere_results.csv"
    if c.exists():
        return pd.read_csv(c, encoding=CSV_ENCODING)
    raise SystemExit(f"No intonasphere_results.xlsx/.csv in {folder}")


def main():
    ap = argparse.ArgumentParser(description="Compare two IntonaSphere runs on the same recordings")
    ap.add_argument("--a", required=True, help="first results folder (e.g. with your TextGrids)")
    ap.add_argument("--b", required=True, help="second results folder (e.g. --realign)")
    ap.add_argument("--label-a", default="your TextGrids")
    ap.add_argument("--label-b", default="re-aligned (WebMAUS)")
    ap.add_argument("--out", default=None)
    ap.add_argument("--include-unaligned", action="store_true",
                    help="also compare files that had no alignment in one of the runs (normally left out)")
    ap.add_argument("--only-user-textgrids", action="store_true",
                    help="compare only recordings for which run A used your own TextGrid")
    a = ap.parse_args()
    A, B = load(user_path(a.a)), load(user_path(a.b))
    if a.only_user_textgrids and "ALIGNMENT_SOURCE" in A:
        A = A[A.ALIGNMENT_SOURCE == "user_textgrid"]
    m = A.merge(B, on="AUDIO_FILE", suffixes=("_A", "_B"))
    n_all = len(m)
    if "ALIGNMENT_SOURCE_A" in m and not a.include_unaligned:
        # a file without any alignment in a run falls back to automatic segmentation in both runs,
        # which would agree with itself and inflate the agreement; compare aligned files only
        al = lambda c: m[c].fillna("").astype(str).str.strip().str.lower().isin(["", "none", "nan"])
        m = m[~al("ALIGNMENT_SOURCE_A") & ~al("ALIGNMENT_SOURCE_B")].reset_index(drop=True)
    out = user_path(a.out) if a.out else user_path(a.b)
    L = [f"IntonaSphere: comparison of two runs",
         f"A = {a.label_a}: {a.a}", f"B = {a.label_b}: {a.b}",
         f"Recordings in both runs: {n_all}; compared (aligned in both runs): {len(m)}"
         + (" (A restricted to your own TextGrids)" if a.only_user_textgrids else ""), ""]
    rows = []

    def num(col):
        return pd.to_numeric(m.get(f"{col}_A"), errors="coerce"), pd.to_numeric(m.get(f"{col}_B"), errors="coerce")

    per = pd.DataFrame({"AUDIO_FILE": m.AUDIO_FILE})
    for c in ("ALIGNMENT_SOURCE_A", "ALIGNMENT_SOURCE_B"):
        if c in m:
            per[c] = m[c]
    if "FINAL_SYLLABLE_START_A" in m:
        sa, sb = num("FINAL_SYLLABLE_START"); ea, eb = num("FINAL_SYLLABLE_END"); da, db = num("FINAL_SYLLABLE_DURATION")
        ds, de, dd = (sb - sa) * 1000, (eb - ea) * 1000, (db - da) * 1000
        per["START_DIFF_MS"], per["END_DIFF_MS"], per["DURATION_DIFF_MS"] = ds.round(1), de.round(1), dd.round(1)
        for name, d in (("final-syllable start", ds), ("final-syllable end", de)):
            v = d.dropna().abs()
            if len(v):
                rows += [(f"{name}: median |difference| (ms)", round(float(v.median()), 1)),
                         (f"{name}: within 20 ms", f"{(v <= 20).mean():.0%}"),
                         (f"{name}: within 50 ms", f"{(v <= 50).mean():.0%}")]
        v = dd.dropna().abs()
        if len(v):
            rows.append(("final-syllable duration: median |difference| (ms)", round(float(v.median()), 1)))
    for col, unit in (("FINAL_SLOPE_ST", "ST/s"), ("F0_ONSET_HZ", "Hz"), ("F0_PEAK_HZ", "Hz"), ("F0_OFFSET_HZ", "Hz")):
        if f"{col}_A" in m:
            x, y = num(col)
            ok = x.notna() & y.notna()
            per[f"{col}_A"], per[f"{col}_B"] = x.round(2), y.round(2)
            if ok.sum() >= 3:
                rows += [(f"{col}: median |difference| ({unit})", round(float((x[ok] - y[ok]).abs().median()), 2)),
                         (f"{col}: correlation r", round(float(np.corrcoef(x[ok], y[ok])[0, 1]), 3))]
    for col, name in (("CONTOUR_CLASS", "contour class"), ("CONTOUR_SLOPE_CLASS", "contour class, slope rule only (3-way)"),
                      ("NUCLEAR", "F_ToBI nuclear configuration")):
        if f"{col}_A" in m:
            x = m[f"{col}_A"].fillna("").astype(str).str.strip()
            y = m[f"{col}_B"].fillna("").astype(str).str.strip()
            ok = ~x.isin(["", "nan"]) & ~y.isin(["", "nan"])
            per[f"{col}_A"], per[f"{col}_B"] = x.where(ok, ""), y.where(ok, "")
            if ok.sum():
                rows += [(f"{name}: agreement (n={int(ok.sum())})", f"{(x[ok] == y[ok]).mean():.0%}"),
                         (f"{name}: Cohen's kappa", round(kappa(x[ok].tolist(), y[ok].tolist()), 3))]
                if col == "CONTOUR_CLASS":
                    ct = pd.crosstab(x[ok].rename(f"A: {a.label_a}"), y[ok].rename(f"B: {a.label_b}"))
    if "CONTOUR_CLASS_A" in per:
        per["CONTOUR_SAME"] = np.where(per["CONTOUR_CLASS_A"] == per["CONTOUR_CLASS_B"], "yes", "NO")
    summ = pd.DataFrame(rows, columns=["MEASURE", "VALUE"])
    L += [f"{r[0]:62s} {r[1]}" for r in rows]
    if "CONTOUR_SAME" in per:
        diff = per[per.CONTOUR_SAME == "NO"]
        if len(diff):
            L += ["", f"Recordings whose contour class differs ({len(diff)}): look at both graphs in Praat"]
            L += [f"  {r.AUDIO_FILE}: {r.CONTOUR_CLASS_A} -> {r.CONTOUR_CLASS_B}" for _, r in diff.head(40).iterrows()]
    txt = "\n".join(L)
    print(txt)
    out.mkdir(parents=True, exist_ok=True)
    (out / "compare_runs_report.txt").write_text(txt + "\n", encoding="utf-8")
    with pd.ExcelWriter(out / "compare_runs.xlsx", engine="openpyxl") as xw:
        summ.to_excel(xw, sheet_name="SUMMARY", index=False)
        per.to_excel(xw, sheet_name="PER_FILE", index=False)
        if "ct" in locals():
            ct.to_excel(xw, sheet_name="CONTOUR_CROSSTAB")
    print(f"\nReport: {out / 'compare_runs_report.txt'}   Details: {out / 'compare_runs.xlsx'}")


if __name__ == "__main__":
    main()
