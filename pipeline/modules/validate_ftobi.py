"""
IntonaSphere AI - agreement between the F_ToBI proposals and a human annotator
=============================================================================

The annotator opens each <stem>_ftobi.TextGrid in Praat (check_ftobi.praat),
corrects the tones, breaks and AP / ip / IP tiers, and saves the result as
<stem>_checked.TextGrid. This script then measures how far the automatic
proposals had to be corrected, which is the validation figure the paper reports.

Measures (reference = the checked TextGrid)
-------------------------------------------
breaks     exact agreement, Cohen's kappa and linear-weighted kappa on the break
           index after every word (0-4; '?' and 'p' diacritics ignored), plus
           the confusion matrix
boundaries precision / recall / F1 for AP (break >= 2), ip (>= 3), IP (4)
tones      per category - pitch accents (H*, L*, H+!H*), Hi, phrase tones (H-, L-),
           boundary tones (H%, L%, !H%), lows (aL, L): detection precision / recall
           with a +/- 80 ms window, and label agreement (kappa) on matched points
nuclear    agreement on the nuclear configuration (last T* + T% of each IP)
'?' flags  agreement for confident vs '?' proposals: if '?' does its job, most
           corrections fall on '?' labels

It also compares boundary TIMES with any hand-annotated TextGrid whose AP / IP
tiers are point or interval tiers (e.g. one annotated before this tool existed):
    python -m modules.validate_ftobi --auto outputs/ftobi --checked checked/ [--tol 0.08]
    python -m modules.validate_ftobi --boundaries-only auto.TextGrid hand.TextGrid
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from .final_domain_visualizer import read_textgrid, TextGrid, Tier


# ---------------------------------------------------------------------------
def kappa(a: List, b: List, weights: Optional[str] = None, cats: Optional[List] = None) -> float:
    if not a:
        return float("nan")
    cats = cats or sorted(set(a) | set(b), key=str)
    k = len(cats)
    if k < 2:
        return float("nan") if len(set(a) | set(b)) < 2 else 1.0
    idx = {c: i for i, c in enumerate(cats)}
    m = np.zeros((k, k))
    for x, y in zip(a, b):
        m[idx[x], idx[y]] += 1
    n = m.sum()
    if weights == "linear":
        w = 1 - np.abs(np.subtract.outer(np.arange(k), np.arange(k))) / (k - 1)
    else:
        w = np.eye(k)
    po = (w * m).sum() / n
    pe = (w * np.outer(m.sum(1), m.sum(0))).sum() / n ** 2
    return float((po - pe) / (1 - pe)) if pe < 1 else float("nan")


def prf(tp: int, fp: int, fn: int) -> Tuple[float, float, float]:
    p = tp / (tp + fp) if tp + fp else float("nan")
    r = tp / (tp + fn) if tp + fn else float("nan")
    f = 2 * p * r / (p + r) if p == p and r == r and p + r else float("nan")
    return p, r, f


def tier(tg: TextGrid, name: str) -> Optional[Tier]:
    for t in tg.tiers:
        if t.name == name:
            return t
    return tg.get(name)


def bnum(label: str) -> Optional[int]:
    m = re.match(r"\s*([0-4])", label or "")
    return int(m.group(1)) if m else None


def tone_cat(label: str) -> str:
    l = label.replace("?", "").strip()
    if l.startswith("Hi"):
        return "Hi"
    if l in ("aL", "L"):
        return "low"
    if "%" in l:
        return "boundary"
    if l.endswith("-"):
        return "phrase"
    if "*" in l:
        return "accent"
    return "other"


def clean(label: str) -> str:
    return label.replace("?", "").strip()


# ---------------------------------------------------------------------------
def compare_pair(auto: TextGrid, ref: TextGrid, tol: float) -> Dict:
    out: Dict = {"break_pairs": [], "tone_rows": [], "nuclear": []}
    # breaks: by word order when the word tiers agree, otherwise by time
    ab, rb = tier(auto, "breaks"), tier(ref, "breaks")
    if ab and rb:
        used = set()
        for p in ab.points:
            j = min(range(len(rb.points)), key=lambda k: abs(rb.points[k].time - p.time), default=None)
            if j is None or j in used or abs(rb.points[j].time - p.time) > tol:
                continue
            used.add(j)
            a, r = bnum(p.label), bnum(rb.points[j].label)
            if a is not None and r is not None:
                out["break_pairs"].append((a, r, "?" in p.label))
    # tones
    at, rt = tier(auto, "tones"), tier(ref, "tones")
    if at and rt:
        a_pts = [(p.time, p.label) for p in at.points if p.label.strip()]
        r_pts = [(p.time, p.label) for p in rt.points if p.label.strip()]
        used = set()
        for rtime, rlab in r_pts:
            cands = [k for k, (t, l) in enumerate(a_pts) if k not in used and abs(t - rtime) <= tol
                     and tone_cat(l) == tone_cat(rlab)]
            if cands:
                k = min(cands, key=lambda k: abs(a_pts[k][0] - rtime))
                used.add(k)
                out["tone_rows"].append({"category": tone_cat(rlab), "ref": clean(rlab), "auto": clean(a_pts[k][1]),
                                         "auto_uncertain": "?" in a_pts[k][1], "status": "matched"})
            else:
                out["tone_rows"].append({"category": tone_cat(rlab), "ref": clean(rlab), "auto": "",
                                         "auto_uncertain": False, "status": "missed"})
        for k, (t, l) in enumerate(a_pts):
            if k not in used:
                out["tone_rows"].append({"category": tone_cat(l), "ref": "", "auto": clean(l),
                                         "auto_uncertain": "?" in l, "status": "extra"})

        # nuclear configuration = last accent + following boundary tone in the utterance
        def nuc(pts):
            acc = [l for _, l in pts if tone_cat(l) == "accent"]
            bnd = [l for _, l in pts if tone_cat(l) == "boundary"]
            return (clean(acc[-1]) if acc else "") + " " + (clean(bnd[-1]) if bnd else "")
        out["nuclear"].append((nuc(a_pts), nuc(r_pts)))
    return out


def boundary_times(tg: TextGrid, names: List[str]) -> List[float]:
    for n in names:
        t = tier(tg, n)
        if t is None:
            continue
        if t.kind == "point":
            return sorted(p.time for p in t.points)
        return sorted(iv.end for iv in t.intervals if iv.label.strip())
    return []


def speech_end(tg: TextGrid) -> float:
    for n in ("words", "word", "ORT-MAU", "mots"):
        t = tier(tg, n)
        if t is not None and t.kind == "interval":
            ends = [iv.end for iv in t.intervals if iv.label.strip()]
            if ends:
                return max(ends)
    return tg.xmax


def boundary_agreement(auto: TextGrid, ref: TextGrid, tol: float) -> pd.DataFrame:
    rows = []
    for level, names in (("AP", ["AP", "Accentual Phrase(AP)"]), ("ip", ["ip"]), ("IP", ["IP"])):
        a, r = boundary_times(auto, names), boundary_times(ref, names)
        if not r:
            continue
        # the end of the utterance is trivially a boundary: drop it (end of each file's last word)
        a = [x for x in a if x < speech_end(auto) - 0.05]
        r = [x for x in r if x < speech_end(ref) - 0.05]
        used, tp = set(), 0
        for x in r:
            j = [k for k, y in enumerate(a) if k not in used and abs(y - x) <= tol]
            if j:
                used.add(min(j, key=lambda k: abs(a[k] - x))); tp += 1
        p, rc, f = prf(tp, len(a) - tp, len(r) - tp)
        rows.append({"LEVEL": level, "REF_BOUNDARIES": len(r), "AUTO_BOUNDARIES": len(a), "MATCHED": tp,
                     "PRECISION": p, "RECALL": rc, "F1": f, "REF_TIMES": " ".join(f"{x:.3f}" for x in r),
                     "AUTO_TIMES": " ".join(f"{x:.3f}" for x in a)})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
def run(auto_dir: Path, checked_dir: Path, out: Path, tol: float) -> Dict[str, pd.DataFrame]:
    pairs = []
    for c in sorted(checked_dir.glob("*_checked.TextGrid")):
        stem = c.name[: -len("_checked.TextGrid")]
        a = auto_dir / f"{stem}_ftobi.TextGrid"
        if a.exists():
            pairs.append((stem, a, c))
    if not pairs:
        raise SystemExit("No <stem>_checked.TextGrid with a matching <stem>_ftobi.TextGrid found.")
    br, tones, nucs, bounds = [], [], [], []
    for stem, a, c in pairs:
        A, R = read_textgrid(a), read_textgrid(c)
        res = compare_pair(A, R, tol)
        br += [(stem,) + x for x in res["break_pairs"]]
        tones += [dict(TOKEN=stem, **x) for x in res["tone_rows"]]
        nucs += [(stem,) + x for x in res["nuclear"]]
        b = boundary_agreement(A, R, tol); b.insert(0, "TOKEN", stem); bounds.append(b)

    bdf = pd.DataFrame(br, columns=["TOKEN", "AUTO", "REF", "AUTO_UNCERTAIN"])
    tdf = pd.DataFrame(tones)
    ndf = pd.DataFrame(nucs, columns=["TOKEN", "AUTO", "REF"])
    summary = []
    if len(bdf):
        a, r = bdf.AUTO.tolist(), bdf.REF.tolist()
        summary += [("breaks: word junctures compared", len(bdf)),
                    ("breaks: exact agreement", float(np.mean(bdf.AUTO == bdf.REF))),
                    ("breaks: Cohen's kappa", kappa(a, r, cats=[0, 1, 2, 3, 4])),
                    ("breaks: linear-weighted kappa", kappa(a, r, "linear", cats=[0, 1, 2, 3, 4]))]
        for lev, name in ((2, "AP"), (3, "ip"), (4, "IP")):
            tp = int(((bdf.AUTO >= lev) & (bdf.REF >= lev)).sum())
            fp = int(((bdf.AUTO >= lev) & (bdf.REF < lev)).sum())
            fn = int(((bdf.AUTO < lev) & (bdf.REF >= lev)).sum())
            p, rc, f = prf(tp, fp, fn)
            summary += [(f"{name} boundary (break >= {lev}): precision", p), (f"{name} boundary: recall", rc),
                        (f"{name} boundary: F1", f)]
        for unc, lab in ((False, "confident"), (True, "'?'")):
            s = bdf[bdf.AUTO_UNCERTAIN == unc]
            if len(s):
                summary.append((f"breaks: agreement on {lab} proposals (n={len(s)})", float(np.mean(s.AUTO == s.REF))))
    if len(tdf):
        for cat in ["accent", "Hi", "phrase", "boundary", "low"]:
            s = tdf[tdf.category == cat]
            if not len(s):
                continue
            tp = int((s.status == "matched").sum()); fp = int((s.status == "extra").sum()); fn = int((s.status == "missed").sum())
            p, rc, f = prf(tp, fp, fn)
            m = s[s.status == "matched"]
            summary += [(f"tones {cat}: detection precision", p), (f"tones {cat}: detection recall", rc),
                        (f"tones {cat}: label agreement on matched (n={len(m)})",
                         float(np.mean(m.ref == m.auto)) if len(m) else float("nan")),
                        (f"tones {cat}: label kappa on matched", kappa(m.auto.tolist(), m.ref.tolist()) if len(m) else float("nan"))]
        m = tdf[tdf.status == "matched"]
        for unc, lab in ((False, "confident"), (True, "'?'")):
            s = m[m.auto_uncertain == unc]
            if len(s):
                summary.append((f"tones: label agreement on {lab} proposals (n={len(s)})", float(np.mean(s.ref == s.auto))))
    if len(ndf):
        summary += [("nuclear configuration: exact agreement", float(np.mean(ndf.AUTO == ndf.REF))),
                    ("nuclear configuration: kappa", kappa(ndf.AUTO.tolist(), ndf.REF.tolist()))]
    sdf = pd.DataFrame(summary, columns=["MEASURE", "VALUE"])
    conf = pd.crosstab(bdf.AUTO, bdf.REF, rownames=["auto"], colnames=["checked"]) if len(bdf) else pd.DataFrame()
    bnd = pd.concat(bounds, ignore_index=True) if bounds else pd.DataFrame()
    out.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(out / "ftobi_validation.xlsx", engine="openpyxl") as xw:
        sdf.to_excel(xw, sheet_name="SUMMARY", index=False)
        conf.to_excel(xw, sheet_name="BREAK_CONFUSION")
        bdf.to_excel(xw, sheet_name="BREAKS", index=False)
        tdf.to_excel(xw, sheet_name="TONES", index=False)
        ndf.to_excel(xw, sheet_name="NUCLEAR", index=False)
        bnd.to_excel(xw, sheet_name="BOUNDARY_TIMES", index=False)
    print(sdf.to_string(index=False))
    return {"summary": sdf, "breaks": bdf, "tones": tdf, "nuclear": ndf, "boundaries": bnd}


def main():
    ap = argparse.ArgumentParser(description="Agreement between F_ToBI proposals and checked TextGrids")
    ap.add_argument("--auto", help="folder with <stem>_ftobi.TextGrid")
    ap.add_argument("--checked", help="folder with <stem>_checked.TextGrid")
    ap.add_argument("--out", default="outputs/ftobi_validation")
    ap.add_argument("--tol", type=float, default=0.08, help="time window (s) for matching points")
    ap.add_argument("--boundaries-only", nargs=2, metavar=("AUTO_TG", "HAND_TG"),
                    help="compare AP / ip / IP boundary times of two TextGrids")
    a = ap.parse_args()
    if a.boundaries_only:
        df = boundary_agreement(read_textgrid(a.boundaries_only[0]), read_textgrid(a.boundaries_only[1]), a.tol)
        print(df.to_string(index=False))
        return
    run(Path(a.auto), Path(a.checked), Path(a.out), a.tol)


if __name__ == "__main__":
    main()
