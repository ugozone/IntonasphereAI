"""
IntonaSphere AI - pitch range for each recording
================================================

Two-pass, speaker-adaptive range (after De Looze & Hirst 2008):
  pass 1  track F0 with a broad range chosen by sex (from the speaker table):
              men 60-300 Hz, women 100-500 Hz, unknown 60-600 Hz
  pass 2  floor = 0.75 x Q25, ceiling = 1.5 x Q75 of the pass-1 F0 values (frames more than
          8 ST from the median, i.e. octave errors, left out), floor never below 50 Hz; track again
  QC      a speaker whose median F0 is unusual for the sex in the table is flagged, and the
          broad 60-600 Hz first pass is used for that speaker instead
The pass-1 values are pooled
  per SPEAKER (default): all of a speaker's recordings (tw1-tw4) together -> one range per
                         speaker, applied to each of their tokens
  per FILE:              each recording on its own (the previous behaviour)
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from .final_domain_visualizer import load_wav, track_pitch
from .dataset_sheet import speaker_code

FIRST_PASS = {"M": (60.0, 300.0), "F": (100.0, 500.0), "": (60.0, 600.0)}


def plan_ranges(wavs: List[Path], method: str = "speaker", speakers: Optional[pd.DataFrame] = None,
                by_sex: bool = True, log=print) -> Dict[str, Dict]:
    """Return {wav file name: {floor, ceiling, first_pass, group, method, sex, n_voiced}}."""
    groups: Dict[str, List[Path]] = {}
    for w in wavs:
        g = speaker_code(w.stem)[0] if method == "speaker" else w.stem
        groups.setdefault(g, []).append(w)
    plan: Dict[str, Dict] = {}
    for g, files in groups.items():
        code = speaker_code(files[0].stem)[0]
        sex = ""
        if by_sex and speakers is not None and code in speakers.index:
            s = str(speakers.loc[code, "SEX"]).upper()[:1]
            sex = s if s in ("M", "F") else ""
        def pass1(lo, hi):
            pooled = []
            for w in files:
                try:
                    x, sr = load_wav(w)
                    _, f = track_pitch(x, sr, lo, hi)
                    pooled.append(f[~np.isnan(f)])
                except Exception as e:
                    log(f"  pitch pass 1 failed for {w.name}: {e}")
            v = np.concatenate(pooled) if pooled else np.array([])
            return v, (float(np.median(v)) if v.size else float("nan"))

        lo, hi = FIRST_PASS[sex]
        v, med = pass1(lo, hi)
        # voice unusual for the sex in the speaker table (typical medians: men ~85-155 Hz,
        # women ~165-255 Hz)? Then the sex-based first pass could clip the range, so redo the
        # first pass with the broad 60-600 Hz range and flag the speaker for a metadata check.
        flag = ""
        if sex == "M" and med == med and med > 165:
            flag = f"median F0 {med:.0f} Hz is high for a male voice"
        elif sex == "F" and med == med and med < 150:
            flag = f"median F0 {med:.0f} Hz is low for a female voice"
        if flag:
            lo, hi = FIRST_PASS[""]
            v, med = pass1(lo, hi)
            flag += f": broad 60-600 Hz first pass used instead (median then {med:.0f} Hz); verify SEX in the speaker table (if it is correct, no action is needed)"
            log(f"  {g}: {flag}")
        if v.size >= 10:
            # drop octave errors (halving / doubling) before the quartiles: keep frames within
            # 8 semitones of the speaker's median (De Looze & Hirst's quartiles are sensitive to them)
            v = v[(v > med / 1.587) & (v < med * 1.587)]
            q25, q75 = np.percentile(v, [25, 75])
            floor, ceiling = max(50.0, 0.75 * q25), min(800.0, 1.5 * q75)
        else:
            floor, ceiling = lo, hi
        for w in files:
            plan[w.name] = {"flag": flag, "median_f0": round(med, 1) if med == med else None,"floor": round(float(floor), 1), "ceiling": round(float(ceiling), 1),
                            "first_pass": f"{lo:.0f}-{hi:.0f} Hz ({'broad: voice unusual for sex' if flag else 'male' if sex == 'M' else 'female' if sex == 'F' else 'sex unknown'})",
                            "group": g, "method": method, "sex": sex, "n_voiced": int(v.size)}
    return plan
