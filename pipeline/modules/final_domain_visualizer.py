"""
IntonaSphere AI - Final-domain visualizer
=========================================

For every question token (one WAV, optionally its WebMAUS TextGrid) this module

1. tracks F0 and intensity (Praat via Parselmouth when installed; otherwise a
   built-in autocorrelation tracker modelled on Praat's "To Pitch (ac)"),
2. sets a speaker-adaptive pitch range in two passes (floor = 0.75 x Q25,
   ceiling = 1.5 x Q75 of a first-pass track; after De Looze & Hirst 2008),
3. finds the final syllable:
     - from the WebMAUS MAS tier when a TextGrid is supplied, or
     - from an automatic segmentation it creates itself (silences +
       intensity-peak syllable nuclei, after de Jong & Wempe 2009),
4. measures the final-domain cues (F0 onset / peak / valley / offset with their
   times, slope, duration, peak alignment, intensity, contour class),
5. writes a TextGrid that adds two tiers to whatever was there:
     FINAL-DOMAIN  (interval: the final syllable, in IPA, with its word, times and duration)
     FINAL-PHONES  (interval: its phones in IPA, vowel marked; when a WebMAUS MAU tier exists)
     CONTOUR       (interval: rise / fall / plateau, fitted slope, onset->offset change, peak alignment)
     CUES          (point: onset, peak, low, offset at their exact times, with their values)
6. draws a Praat-style figure: waveform, spectrogram + F0, tiers, and a zoom
   of the final syllable with every cue labelled with its time and value,
7. exports one row per token (CSV + Excel) that links to the figure and the
   TextGrid, so every number can be checked by eye and in Praat.

Command line:
    python -m modules.final_domain_visualizer --folder path/to/wavs_and_textgrids \
        --out outputs/final_domain [--tier MAS] [--force-auto] [--slope-threshold 1.5]

Dependencies: numpy, scipy, matplotlib, pandas, openpyxl.
Optional (recommended): praat-parselmouth  -> Praat's own pitch & intensity.
"""

from __future__ import annotations

from . import user_path, CSV_ENCODING

import argparse
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from scipy.io import wavfile
from scipy import signal

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import gridspec

try:  # Praat itself, when available
    import parselmouth  # type: ignore
    HAVE_PARSELMOUTH = True
except Exception:  # pragma: no cover
    HAVE_PARSELMOUTH = False


# ---------------------------------------------------------------------------
# PFC texte lu questions (used to label the utterance tier when no TextGrid)
# ---------------------------------------------------------------------------
PFC_QUESTIONS = {
    "1": "Le Premier ministre ira-t-il à Beaulieu ?",
    "2": "Qu'est-ce qui a donc valu à Beaulieu ce grand honneur ?",
    "3": "Comment, en plus, éviter les manifestations qui ont eu tendance "
         "à se multiplier lors des visites officielles ?",
    # tw4: the opening sentence of the PFC text, a declarative (control / baseline)
    "4": "Le village de Beaulieu est en grand émoi.",
}
def sentence_id(n: str) -> str:
    """PFC sentence label from the file number: tw1-tw3 are questions (Q1-Q3), tw4 is the statement (S4)."""
    return "" if not n else (f"S{n}" if n == "4" else f"Q{n}")


PFC_FINAL_WORD = {"1": "Beaulieu", "2": "honneur", "3": "officielles", "4": "émoi"}
PAUSE_LABELS = {"", "<p:>", "<p>", "sp", "sil", "silence", "pause", "#", "<usb>"}


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------
@dataclass
class Interval:
    start: float
    end: float
    label: str


@dataclass
class Point:
    time: float
    label: str


@dataclass
class Tier:
    name: str
    kind: str  # "interval" or "point"
    intervals: List[Interval] = field(default_factory=list)
    points: List[Point] = field(default_factory=list)


@dataclass
class TextGrid:
    xmin: float
    xmax: float
    tiers: List[Tier] = field(default_factory=list)

    def get(self, name: str) -> Optional[Tier]:
        for t in self.tiers:
            if t.name.lower() == name.lower():
                return t
        return None


# ---------------------------------------------------------------------------
# TextGrid I/O (long and short Praat text formats; no external dependency)
# ---------------------------------------------------------------------------
def _read_text(path: Path) -> str:
    raw = path.read_bytes()
    for enc in ("utf-8-sig", "utf-16", "latin-1"):
        try:
            txt = raw.decode(enc)
            if "TextGrid" in txt or "ooTextFile" in txt:
                return txt
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1")


def read_textgrid(path: str | Path) -> TextGrid:
    """Parse a Praat TextGrid (long or short text format)."""
    txt = _read_text(Path(path))
    # drop long-format index lines such as 'item [1]:', 'intervals [3]:', 'points [2]:', 'item []:'
    txt = re.sub(r"(?m)^\s*(item|intervals|points)\s*\[\d*\]\s*:\s*$", "", txt)
    # tokenise: quoted strings (with "" escapes) or bare numbers/words
    tokens = re.findall(r'"((?:[^"]|"")*)"|([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)|(<exists>|<absent>)', txt)
    vals: List[str] = []
    for q, num, flag in tokens:
        if num:
            vals.append(num)
        elif flag:
            vals.append(flag)
        else:
            vals.append('"' + q.replace('""', '"'))
    it = iter(vals)

    def nxt():
        return next(it)

    def nxt_num():
        v = nxt()
        while v.startswith('"'):
            v = nxt()
        return float(v)

    def nxt_str():
        v = nxt()
        while not v.startswith('"'):
            v = nxt()
        return v[1:]

    # header strings: "ooTextFile" "TextGrid"
    nxt_str(); nxt_str()
    xmin, xmax = nxt_num(), nxt_num()
    v = nxt()  # <exists>
    n_tiers = int(nxt_num())
    tg = TextGrid(xmin, xmax)
    for _ in range(n_tiers):
        cls = nxt_str()
        name = nxt_str()
        nxt_num(); nxt_num()  # tier xmin xmax
        n = int(nxt_num())
        if cls == "IntervalTier":
            tier = Tier(name, "interval")
            for _ in range(n):
                s, e = nxt_num(), nxt_num()
                tier.intervals.append(Interval(s, e, nxt_str()))
        else:
            tier = Tier(name, "point")
            for _ in range(n):
                t = nxt_num()
                tier.points.append(Point(t, nxt_str()))
        tg.tiers.append(tier)
    return tg


def _q(s: str) -> str:
    return '"' + str(s).replace('"', '""') + '"'


def write_textgrid(tg: TextGrid, path: str | Path) -> None:
    """Write a TextGrid in Praat's long text format (UTF-8)."""
    out = ['File type = "ooTextFile"', 'Object class = "TextGrid"', "",
           f"xmin = {tg.xmin}", f"xmax = {tg.xmax}", "tiers? <exists>",
           f"size = {len(tg.tiers)}", "item []:"]
    for i, t in enumerate(tg.tiers, 1):
        out.append(f"    item [{i}]:")
        if t.kind == "interval":
            ivs = _fill_gaps(t.intervals, tg.xmin, tg.xmax)
            out += ['        class = "IntervalTier"', f"        name = {_q(t.name)}",
                    f"        xmin = {tg.xmin}", f"        xmax = {tg.xmax}",
                    f"        intervals: size = {len(ivs)}"]
            for j, iv in enumerate(ivs, 1):
                out += [f"        intervals [{j}]:", f"            xmin = {iv.start}",
                        f"            xmax = {iv.end}", f"            text = {_q(iv.label)}"]
        else:
            pts = sorted(t.points, key=lambda p: p.time)
            out += ['        class = "TextTier"', f"        name = {_q(t.name)}",
                    f"        xmin = {tg.xmin}", f"        xmax = {tg.xmax}",
                    f"        points: size = {len(pts)}"]
            for j, p in enumerate(pts, 1):
                out += [f"        points [{j}]:", f"            number = {p.time}",
                        f"            mark = {_q(p.label)}"]
    Path(path).write_text("\n".join(out) + "\n", encoding="utf-8")


def _fill_gaps(ivs: List[Interval], xmin: float, xmax: float) -> List[Interval]:
    """Praat requires interval tiers to cover xmin..xmax without gaps."""
    ivs = sorted(ivs, key=lambda i: i.start)
    out, t = [], xmin
    for iv in ivs:
        s, e = max(iv.start, t), min(iv.end, xmax)
        if e <= s:
            continue
        if s > t + 1e-9:
            out.append(Interval(t, s, ""))
        out.append(Interval(s, e, iv.label))
        t = e
    if t < xmax - 1e-9:
        out.append(Interval(t, xmax, ""))
    return out


# ---------------------------------------------------------------------------
# Audio
# ---------------------------------------------------------------------------
def load_wav(path: str | Path) -> Tuple[np.ndarray, int]:
    sr, x = wavfile.read(str(path))
    if x.dtype == np.int16:
        x = x.astype(np.float64) / 32768.0
    elif x.dtype == np.int32:
        x = x.astype(np.float64) / 2147483648.0
    elif x.dtype == np.uint8:
        x = (x.astype(np.float64) - 128) / 128.0
    else:
        x = x.astype(np.float64)
    if x.ndim > 1:
        x = x.mean(axis=1)
    return x, int(sr)


# ---------------------------------------------------------------------------
# Pitch tracking
# ---------------------------------------------------------------------------
def _pitch_parselmouth(x, sr, floor, ceiling, step):
    snd = parselmouth.Sound(x, sampling_frequency=sr)
    p = snd.to_pitch_ac(time_step=step, pitch_floor=floor, pitch_ceiling=ceiling)
    f0 = p.selected_array["frequency"].astype(float)
    f0[f0 == 0] = np.nan
    return p.xs(), f0


def _pitch_numpy(x, sr, floor, ceiling, step,
                 voicing_threshold=0.45, silence_threshold=0.03,
                 octave_cost=0.01, octave_jump_cost=0.35, vuv_cost=0.14, n_cand=6):
    """Autocorrelation pitch tracker following Boersma (1993) / Praat 'To Pitch (ac)':
    window-corrected normalised autocorrelation, Praat's candidate strengths,
    and a Viterbi path with octave-jump and voicing-transition costs."""
    win_dur = 3.0 / floor
    n_win = int(round(win_dur * sr))
    n_win += n_win % 2
    hop = int(round(step * sr))
    pad = n_win // 2
    xp = np.pad(x, (pad, pad))
    n_frames = 1 + (len(xp) - n_win) // hop
    idx = np.arange(n_win)[None, :] + hop * np.arange(n_frames)[:, None]
    frames = xp[idx]
    times = (np.arange(n_frames) * hop) / sr
    global_peak = np.max(np.abs(x)) + 1e-12
    local_peak = np.max(np.abs(frames - frames.mean(axis=1, keepdims=True)), axis=1)

    w = np.hanning(n_win)
    nfft = 1 << int(math.ceil(math.log2(2 * n_win)))
    rw = np.fft.irfft(np.abs(np.fft.rfft(w, nfft)) ** 2)[:n_win]
    rw /= rw[0]
    fr = (frames - frames.mean(axis=1, keepdims=True)) * w
    r = np.fft.irfft(np.abs(np.fft.rfft(fr, nfft, axis=1)) ** 2, axis=1)[:, :n_win]
    r0 = r[:, :1] + 1e-20
    r = r / r0
    lag_min = max(2, int(math.floor(sr / ceiling)))
    lag_max = min(int(math.ceil(sr / floor)), n_win // 2 - 1)
    r[:, : n_win // 2] = r[:, : n_win // 2] / np.maximum(rw[: n_win // 2], 1e-6)

    cand_f = np.zeros((n_frames, n_cand + 1))
    cand_s = np.full((n_frames, n_cand + 1), -np.inf)
    for i in range(n_frames):
        unv = voicing_threshold + max(0.0, 2 - (local_peak[i] / global_peak) /
                                      (silence_threshold / (1 + voicing_threshold)))
        cand_f[i, 0], cand_s[i, 0] = 0.0, unv
        seg = r[i, lag_min - 1: lag_max + 2]
        pk = np.where((seg[1:-1] > seg[:-2]) & (seg[1:-1] >= seg[2:]) & (seg[1:-1] > 0))[0] + 1
        if pk.size == 0:
            continue
        a, b, c = seg[pk - 1], seg[pk], seg[pk + 1]
        den = a - 2 * b + c
        shift = np.where(np.abs(den) > 1e-12, 0.5 * (a - c) / den, 0.0)
        lag = (pk + lag_min - 1) + shift
        val = np.minimum(b - 0.25 * (a - c) * shift, 1.0)
        tau = lag / sr
        strength = val - octave_cost * np.log2(floor * tau)
        order = np.argsort(strength)[::-1][:n_cand]
        k = len(order)
        cand_f[i, 1:1 + k] = 1.0 / tau[order]
        cand_s[i, 1:1 + k] = strength[order]

    # Viterbi (maximise strength minus transition costs)
    corr = 0.01 / step
    score = cand_s[0].copy()
    back = np.zeros((n_frames, n_cand + 1), dtype=int)
    for i in range(1, n_frames):
        fp, fc = cand_f[i - 1][:, None], cand_f[i][None, :]
        both_v = (fp > 0) & (fc > 0)
        one_v = (fp > 0) ^ (fc > 0)
        with np.errstate(divide="ignore", invalid="ignore"):
            jump = np.where(both_v, octave_jump_cost * np.abs(np.log2(fc / np.where(fp > 0, fp, 1))), 0.0)
        cost = (jump + np.where(one_v, vuv_cost, 0.0)) * corr
        tot = score[:, None] - cost
        back[i] = np.argmax(tot, axis=0)
        score = tot[back[i], np.arange(n_cand + 1)] + cand_s[i]
    path = np.zeros(n_frames, dtype=int)
    path[-1] = int(np.argmax(score))
    for i in range(n_frames - 1, 0, -1):
        path[i - 1] = back[i, path[i]]
    f0 = cand_f[np.arange(n_frames), path]
    f0 = np.where(f0 > 0, f0, np.nan)
    return times, f0


def track_pitch(x, sr, floor=75.0, ceiling=500.0, step=0.01):
    if HAVE_PARSELMOUTH:
        return _pitch_parselmouth(x, sr, floor, ceiling, step)
    return _pitch_numpy(x, sr, floor, ceiling, step)


def adaptive_pitch(x, sr, step=0.01, fixed: Optional[Tuple[float, float]] = None):
    """Two-pass, speaker-adaptive range (De Looze & Hirst 2008 style)."""
    if fixed:
        t, f = track_pitch(x, sr, fixed[0], fixed[1], step)
        return t, f, fixed
    t, f = track_pitch(x, sr, 60.0, 600.0, step)
    v = f[~np.isnan(f)]
    if v.size < 10:
        return t, f, (60.0, 600.0)
    q25, q75 = np.percentile(v, [25, 75])
    floor, ceiling = max(50.0, 0.75 * q25), min(800.0, 1.5 * q75)
    t, f = track_pitch(x, sr, floor, ceiling, step)
    return t, f, (round(floor, 1), round(ceiling, 1))


# ---------------------------------------------------------------------------
# Intensity
# ---------------------------------------------------------------------------
def track_intensity(x, sr, min_pitch=100.0, step=0.01):
    if HAVE_PARSELMOUTH:
        snd = parselmouth.Sound(x, sampling_frequency=sr)
        it = snd.to_intensity(minimum_pitch=min_pitch, time_step=step)
        return it.xs(), it.values[0].astype(float)
    n_win = int(round(3.2 / min_pitch * sr))
    hop = int(round(step * sr))
    w = np.kaiser(n_win, 20)
    pad = n_win // 2
    xp = np.pad(x, (pad, pad))
    n_frames = 1 + (len(xp) - n_win) // hop
    idx = np.arange(n_win)[None, :] + hop * np.arange(n_frames)[:, None]
    fr = xp[idx]
    fr = fr - fr.mean(axis=1, keepdims=True)
    ms = (fr ** 2 * w).sum(axis=1) / w.sum()
    db = 10 * np.log10(ms / 4e-10 + 1e-30)
    return np.arange(n_frames) * step, db


# ---------------------------------------------------------------------------
# Automatic segmentation (used when no TextGrid / no syllable tier exists)
# ---------------------------------------------------------------------------
def detect_silences(t_int, db, silence_db=-25.0, min_silent=0.10, min_sounding=0.05):
    """Like Praat 'To TextGrid (silences)': sounding = intensity above max + silence_db."""
    thr = np.max(db) + silence_db
    snd = db > thr
    segs, start = [], None
    for i, s in enumerate(snd):
        if s and start is None:
            start = t_int[i]
        if not s and start is not None:
            segs.append([start, t_int[i]]); start = None
    if start is not None:
        segs.append([start, t_int[-1]])
    merged = []
    for s, e in segs:  # bridge short silences
        if merged and s - merged[-1][1] < min_silent:
            merged[-1][1] = e
        else:
            merged.append([s, e])
    return [(s, e) for s, e in merged if e - s >= min_sounding]


def syllable_nuclei(t_int, db, t_f0, f0, sounding, silence_db=-25.0, min_dip=2.0):
    """Syllable nuclei after de Jong & Wempe (2009): intensity peaks above the
    silence threshold, separated by dips of >= min_dip dB, voiced at the peak."""
    k = np.hanning(5); k /= k.sum()
    sm = np.convolve(db, k, mode="same")
    thr = np.percentile(sm, 99) + silence_db
    peaks = signal.argrelextrema(sm, np.greater_equal, order=2)[0]
    peaks = [p for p in peaks if sm[p] > thr]
    kept: List[int] = []
    for p in peaks:
        if not kept:
            kept.append(p); continue
        q = kept[-1]
        dip = sm[q:p + 1].min()
        if sm[p] - dip >= min_dip and sm[q] - dip >= min_dip:
            kept.append(p)
        elif sm[p] > sm[q]:
            kept[-1] = p
    def voiced_at(t):
        m = np.abs(t_f0 - t) <= 0.02
        return np.any(~np.isnan(f0[m]))
    def in_sounding(t):
        return any(s <= t <= e for s, e in sounding)
    return [t_int[p] for p in kept if voiced_at(t_int[p]) and in_sounding(t_int[p])], sm


def auto_syllables(t_int, sm, nuclei, sounding) -> List[Interval]:
    """Syllable intervals: boundaries at intensity minima between nuclei,
    clipped to the sounding interval that contains them."""
    out = []
    for s, e in sounding:
        nuc = [n for n in nuclei if s <= n <= e]
        if not nuc:
            continue
        bounds = [s]
        for a, b in zip(nuc[:-1], nuc[1:]):
            m = (t_int >= a) & (t_int <= b)
            bounds.append(float(t_int[m][np.argmin(sm[m])]))
        bounds.append(e)
        for i in range(len(nuc)):
            out.append(Interval(float(bounds[i]), float(bounds[i + 1]), f"{len(out) + 1}"))
    return out


# ---------------------------------------------------------------------------
# Final-domain detection from an existing TextGrid
# ---------------------------------------------------------------------------
def _is_pause(label: str) -> bool:
    c = (label or "").strip().lower()
    return c in PAUSE_LABELS or c.startswith("<p")


def final_interval(tg: TextGrid, tier_names: List[str], file_stem: str) -> Tuple[Optional[Interval], str]:
    stem = re.sub(r"[^a-z0-9]", "", file_stem.lower())
    bad_spans = []
    ort = tg.get("ORT-MAU")
    if ort:
        for iv in ort.intervals:
            if re.sub(r"[^a-z0-9]", "", iv.label.lower()) == stem:
                bad_spans.append((iv.start, iv.end))
    for name in tier_names:
        tier = tg.get(name)
        if not tier or tier.kind != "interval":
            continue
        good = [iv for iv in tier.intervals
                if not _is_pause(iv.label)
                and re.sub(r"[^a-z0-9]", "", iv.label.lower()) != stem
                and not any(iv.start < b and iv.end > a for a, b in bad_spans)]
        if good:
            return good[-1], tier.name
    return None, ""


# ---------------------------------------------------------------------------
# Cue measurement
# ---------------------------------------------------------------------------
def st(f, ref):
    return 12.0 * np.log2(np.asarray(f, float) / ref)


TURN_ST = 1.5          # rise-fall / fall-rise: the turning point must be >= 1.5 ST beyond BOTH edges
TURN_ZONE = (0.2, 0.8) # ... and lie in the middle 60% of the voiced part of the syllable
TURN_MIN_FRAMES = 4    # ... with at least 4 voiced frames (40 ms) on each side, turn included


def classify_contour(tt, st_vals, slope, slope_threshold=1.5) -> str:
    """rise-fall / fall-rise when the F0 turns inside the syllable, otherwise rise / fall / plateau
    from the fitted slope. A turn counts when the peak (valley) lies in the middle 60% of the voiced
    span and is at least TURN_ST semitones above (below) both the onset and the offset (medians of
    the first / last 3 voiced frames). One straight line cannot describe such a contour."""
    tt, v = np.asarray(tt, float), np.asarray(st_vals, float)
    if len(v) >= 5:
        k = min(3, len(v))
        on, off = np.median(v[:k]), np.median(v[-k:])
        span = tt[-1] - tt[0]
        if span > 0:
            ip, iv = int(np.argmax(v)), int(np.argmin(v))
            pp, pv = (tt[ip] - tt[0]) / span, (tt[iv] - tt[0]) / span
            n = len(v)
            # each side of the turn needs >= TURN_MIN_FRAMES voiced frames (40 ms), so a single odd
            # onset or offset value cannot create a turn
            if TURN_ZONE[0] <= pp <= TURN_ZONE[1] and ip >= TURN_MIN_FRAMES - 1 and n - 1 - ip >= TURN_MIN_FRAMES - 1 \
                    and v[ip] - on >= TURN_ST and v[ip] - off >= TURN_ST:
                return "rise-fall"
            if TURN_ZONE[0] <= pv <= TURN_ZONE[1] and iv >= TURN_MIN_FRAMES - 1 and n - 1 - iv >= TURN_MIN_FRAMES - 1 \
                    and on - v[iv] >= TURN_ST and off - v[iv] >= TURN_ST:
                return "fall-rise"
    return "rise" if slope >= slope_threshold else ("fall" if slope <= -slope_threshold else "plateau")


def measure_cues(t_f0, f0, t_int, db, syl: Interval, ref_hz: float, slope_threshold=1.5) -> Dict:
    m = (t_f0 >= syl.start) & (t_f0 <= syl.end) & ~np.isnan(f0)
    res: Dict = {"FINAL_SYLLABLE_START": syl.start, "FINAL_SYLLABLE_END": syl.end,
                 "FINAL_SYLLABLE_DURATION": syl.end - syl.start, "FINAL_SYLLABLE_LABEL": syl.label,
                 "VOICED_FRAMES": int(m.sum())}
    im = (t_int >= syl.start) & (t_int <= syl.end)
    res["FINAL_INTENSITY_MEAN_DB"] = float(10 * np.log10(np.mean(10 ** (db[im] / 10)))) if im.any() else np.nan
    if m.sum() < 3:
        res.update(STATUS="no_voiced_f0_in_final_syllable", CONTOUR_CLASS=None)
        return res
    tt, ff = t_f0[m], f0[m]
    s = st(ff, ref_hz)
    i_pk, i_vl = int(np.argmax(ff)), int(np.argmin(ff))
    k = min(3, len(ff))                       # robust edges: median of first / last 3 voiced frames
    on_hz, off_hz = float(np.median(ff[:k])), float(np.median(ff[-k:]))
    on_t, off_t = float(np.mean(tt[:k])), float(np.mean(tt[-k:]))
    b1, b0 = np.polyfit(tt, s, 1)             # least-squares line through the voiced frames
    dur = syl.end - syl.start
    res.update(
        F0_ONSET_TIME=on_t, F0_ONSET_HZ=on_hz,
        F0_PEAK_TIME=float(tt[i_pk]), F0_PEAK_HZ=float(ff[i_pk]),
        F0_VALLEY_TIME=float(tt[i_vl]), F0_VALLEY_HZ=float(ff[i_vl]),
        F0_OFFSET_TIME=off_t, F0_OFFSET_HZ=off_hz,
        F0_MEAN_HZ=float(np.mean(ff)),
        F0_RANGE_ST=float(s.max() - s.min()),
        F0_CHANGE_ST=float(12 * np.log2(off_hz / on_hz)),
        FINAL_SLOPE_ST=float(b1),                                   # main measure (ST/s)
        FINAL_SLOPE_ENDPOINT_ST=float((s[-1] - s[0]) / dur),        # release-dataset definition
        FIT_INTERCEPT_ST=float(b0),
        PEAK_ALIGNMENT_S=float(tt[i_pk] - syl.start),
        PEAK_ALIGNMENT_PROP=float((tt[i_pk] - syl.start) / max(dur, 1e-9)),
        REF_HZ=float(ref_hz),
    )
    jumps = np.abs(np.diff(s))                 # frame-to-frame F0 jumps inside the final syllable
    res["MAX_F0_JUMP_ST"] = float(jumps.max()) if jumps.size else 0.0
    res["QC_OCTAVE_JUMP"] = bool(jumps.size and jumps.max() >= 7.0)   # >= 7 ST between 10-ms frames: likely tracking error
    sl = res["FINAL_SLOPE_ST"]
    res["CONTOUR_CLASS"] = classify_contour(tt, s, sl, slope_threshold)
    res["CONTOUR_SLOPE_CLASS"] = "rise" if sl >= slope_threshold else ("fall" if sl <= -slope_threshold else "plateau")
    res["STATUS"] = "completed"
    return res


def cue_points(c: Dict) -> List[Point]:
    """One point per measured value, with a short label (the summary goes on the CONTOUR tier)."""
    if c.get("STATUS") != "completed":
        return []
    on_t, off_t, pk_t, vl_t = c["F0_ONSET_TIME"], c["F0_OFFSET_TIME"], c["F0_PEAK_TIME"], c["F0_VALLEY_TIME"]
    on_lab, off_lab = f"onset {c['F0_ONSET_HZ']:.0f} Hz", f"offset {c['F0_OFFSET_HZ']:.0f} Hz"
    pts = []
    if abs(pk_t - on_t) <= 0.015:
        on_lab += f" (peak {c['F0_PEAK_HZ']:.0f} Hz)"
    elif abs(pk_t - off_t) <= 0.015:
        off_lab += f" (peak {c['F0_PEAK_HZ']:.0f} Hz)"
    else:
        pts.append(Point(pk_t, f"peak {c['F0_PEAK_HZ']:.0f} Hz"))
    if abs(vl_t - on_t) <= 0.015:
        on_lab += f" (low {c['F0_VALLEY_HZ']:.0f} Hz)" if "peak" not in on_lab else ""
    elif abs(vl_t - off_t) <= 0.015:
        off_lab += f" (low {c['F0_VALLEY_HZ']:.0f} Hz)" if "peak" not in off_lab else ""
    else:
        pts.append(Point(vl_t, f"low {c['F0_VALLEY_HZ']:.0f} Hz"))
    pts += [Point(on_t, on_lab), Point(off_t, off_lab)]
    lv = c.get("LAST_VOICED_TIME")
    if lv == lv and lv is not None and c["FINAL_SYLLABLE_END"] - lv > 0.03 and abs(lv - off_t) > 0.005:
        pts.append(Point(lv + 0.005, "F0 ends"))
    elif lv == lv and lv is not None and c["FINAL_SYLLABLE_END"] - lv > 0.03:
        pts[-1] = Point(off_t, off_lab + "; F0 ends here")
    return sorted(pts, key=lambda p: p.time)


def _figure_phones(t: Optional["Tier"]) -> Optional["Tier"]:
    """Copy of FINAL-PHONES for the figure: the vowel is shown as 'ø (V)' so it fits."""
    if t is None:
        return None
    return Tier(t.name, t.kind, [Interval(i.start, i.end, i.label.replace("  (vowel)", " (V)")) for i in t.intervals])


def final_vowel_coverage(tg_in, syl: Interval, t_f0, f0) -> Dict:
    """Share of the final VOWEL that has a measured F0. Utterance-final vowels are often creaky
    or fall below the pitch floor; then the contour is really measured on the onset consonants.
    QC_FINAL_VOWEL_LOW_F0 is True when less than half of the vowel has F0."""
    out: Dict = {"FINAL_VOWEL": "", "FINAL_VOWEL_START": np.nan, "FINAL_VOWEL_END": np.nan,
                 "FINAL_VOWEL_F0_COVERAGE": np.nan, "QC_FINAL_VOWEL_LOW_F0": False,
                 "LAST_VOICED_TIME": np.nan}
    m = (t_f0 >= syl.start) & (t_f0 <= syl.end) & ~np.isnan(f0)
    if m.any():
        out["LAST_VOICED_TIME"] = float(t_f0[m][-1])
    mau = tg_in.get("MAU") if tg_in is not None else None
    if mau is None:
        return out
    vowels = {"i", "e", "E", "a", "A", "O", "o", "u", "y", "2", "9", "@", "e~", "a~", "o~", "9~"}
    ipa_v = set("ieɛaɑɔouyøœə")
    vs = [iv for iv in mau.intervals if iv.start >= syl.start - 1e-4 and iv.end <= syl.end + 1e-4
          and (iv.label.strip() in vowels or any(ch in ipa_v for ch in iv.label))]
    if not vs:
        return out
    v = vs[-1]
    fr = (t_f0 >= v.start) & (t_f0 <= v.end)
    cov = float((~np.isnan(f0[fr])).mean()) if fr.any() else 0.0
    out.update(FINAL_VOWEL=v.label.strip(), FINAL_VOWEL_START=v.start, FINAL_VOWEL_END=v.end,
               FINAL_VOWEL_F0_COVERAGE=round(cov, 3), QC_FINAL_VOWEL_LOW_F0=bool(cov < 0.5))
    return out


def contour_label(c: Dict) -> str:
    if c.get("STATUS") != "completed":
        return "no voiced F0 in the final syllable"
    turn = ""
    if c["CONTOUR_CLASS"] == "rise-fall":
        turn = (f"  (up {12 * np.log2(c['F0_PEAK_HZ'] / c['F0_ONSET_HZ']):+.1f} ST to the peak, then "
                f"{12 * np.log2(c['F0_OFFSET_HZ'] / c['F0_PEAK_HZ']):+.1f} ST)")
    elif c["CONTOUR_CLASS"] == "fall-rise":
        turn = (f"  (down {12 * np.log2(c['F0_VALLEY_HZ'] / c['F0_ONSET_HZ']):+.1f} ST to the low, then "
                f"{12 * np.log2(c['F0_OFFSET_HZ'] / c['F0_VALLEY_HZ']):+.1f} ST)")
    lab = (f"{c['CONTOUR_CLASS'].upper()}{turn}  |  slope {c['FINAL_SLOPE_ST']:+.1f} ST/s (fitted)  |  "
           f"onset->offset {c['F0_CHANGE_ST']:+.1f} ST  |  peak at {c['PEAK_ALIGNMENT_S'] * 1000:.0f} ms "
           f"({c['PEAK_ALIGNMENT_PROP'] * 100:.0f}%)")
    cov = c.get("FINAL_VOWEL_F0_COVERAGE")
    if cov == cov and cov is not None:
        lab += f"  |  F0 on {cov * 100:.0f}% of the vowel"
        if c.get("QC_FINAL_VOWEL_LOW_F0"):
            lab += "  CHECK: vowel mostly without F0 (creak / below floor?)"
    return lab


def final_syllable_tiers(tg_in: Optional["TextGrid"], syl: "Interval", word_hint: str, cues: Dict,
                         auto: bool) -> List["Tier"]:
    """Readable tiers for the final syllable: FINAL-DOMAIN (IPA, word, times), FINAL-PHONES
    (its phones in IPA, vowel marked), CONTOUR (classification), CUES (measured points)."""
    try:
        from .ftobi_annotator import sampa_to_ipa
    except Exception:                                 # pragma: no cover
        sampa_to_ipa = lambda x: (x.replace(" ", ""), [])
    ipa, word = "", word_hint
    phones: List[Interval] = []
    if tg_in is not None and not auto:
        ipa = sampa_to_ipa(syl.label)[0] if syl.label else ""
        wt = tg_in.get("ORT-MAU") or tg_in.get("words") or tg_in.get("word")
        if wt is not None:
            ov = [(min(iv.end, syl.end) - max(iv.start, syl.start), iv.label) for iv in wt.intervals if iv.label.strip()]
            ov = [o for o in ov if o[0] > 0]
            if ov:
                word = max(ov)[1].strip()
        mau = tg_in.get("MAU")
        if mau is not None:
            vowels = set("ieɛaɑɔouyøœəɪʊʏ")
            for iv in mau.intervals:
                if iv.start >= syl.start - 1e-4 and iv.end <= syl.end + 1e-4 and iv.label.strip() \
                        and not iv.label.startswith("<"):
                    ph = sampa_to_ipa(iv.label)[0]
                    is_v = any(ch in vowels for ch in ph)
                    phones.append(Interval(iv.start, iv.end, f"{ph}  (vowel)" if is_v else ph))
    dur = (syl.end - syl.start) * 1000
    head = f"[{ipa}]" if ipa else "final syllable (automatic)"
    lab = f"{head}  final syllable of '{word}'  {syl.start:.3f}-{syl.end:.3f} s  ({dur:.0f} ms)"
    tiers = [Tier("FINAL-DOMAIN", "interval", [Interval(syl.start, syl.end, lab)])]
    if phones:
        tiers.append(Tier("FINAL-PHONES", "interval", phones))
    tiers += [Tier("CONTOUR", "interval", [Interval(syl.start, syl.end, contour_label(cues))]),
              Tier("CUES", "point", points=cue_points(cues))]
    return tiers


# ---------------------------------------------------------------------------
# Figure
# ---------------------------------------------------------------------------
INK, SEC, GRID = "#14213D", "#5B6472", "#D9D6CC"
F0C, SHADE = "#1F5FAF", "#F6E3B5"
CLS = {"fall": "#1F5FAF", "plateau": "#6B6A63", "rise": "#C2511F", "rise-fall": "#7A3E9D", "fall-rise": "#2E7D5B"}


def draw_figure(token_id, x, sr, t_f0, f0, rng, tiers: List[Tier], syl: Interval, cues: Dict,
                sentence: str, source_note: str, out_png: Path, out_svg: Optional[Path] = None):
    dur = len(x) / sr
    tx = np.arange(len(x)) / sr
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10})
    fig = plt.figure(figsize=(15, 8.4), dpi=150)
    n_t = len(tiers)
    gs = gridspec.GridSpec(3 + n_t, 1, height_ratios=[0.9, 2.6] + [0.38] * n_t + [0.05],
                           hspace=0.08, left=0.075, right=0.64, top=0.9, bottom=0.06)
    gr = gridspec.GridSpec(3, 1, height_ratios=[3.1, 0.55, 2.0], hspace=0.05,
                           left=0.72, right=0.985, top=0.9, bottom=0.04)
    cls = cues.get("CONTOUR_CLASS")
    title = f"{token_id}  ·  {sentence}"
    fig.text(0.06, 0.955, title, fontsize=13, fontweight="bold", color=INK)
    fig.text(0.06, 0.928, source_note, fontsize=9.5, color=SEC)

    # waveform
    axw = fig.add_subplot(gs[0])
    axw.plot(tx, x, color="#6E7686", lw=0.4)
    axw.set_xlim(0, dur); axw.set_yticks([]); axw.set_xticks([])
    axw.axvspan(syl.start, syl.end, color=SHADE, zorder=0)
    for s in ("top", "right", "left"):
        axw.spines[s].set_visible(False)

    # spectrogram + F0
    axs = fig.add_subplot(gs[1], sharex=axw)
    nper = int(0.005 * sr)
    fr, ts, S = signal.spectrogram(x, sr, window="gaussian" if False else "hann", nperseg=max(nper, 64),
                                   noverlap=max(nper, 64) - int(0.002 * sr), nfft=512, mode="psd")
    Sdb = 10 * np.log10(S + 1e-20)
    vmax = Sdb.max()
    axs.pcolormesh(ts, fr, Sdb, shading="auto", cmap="Greys", vmin=vmax - 55, vmax=vmax, rasterized=True)
    axs.set_ylim(0, 5000); axs.set_ylabel("Frequency (Hz)", color=SEC)
    axs.axvspan(syl.start, syl.end, facecolor="none", edgecolor="#D99A1E", lw=1.6, zorder=3)
    axf = axs.twinx()
    axf.plot(t_f0, f0, ".", color="white", ms=5.5, zorder=4)
    axf.plot(t_f0, f0, ".", color=F0C, ms=3.5, zorder=5)
    lo, hi = rng
    axf.set_ylim(lo, hi); axf.set_ylabel("F0 (Hz)", color=F0C)
    axf.tick_params(axis="y", colors=F0C)
    plt.setp(axs.get_xticklabels(), visible=False)

    # tiers
    axes_t = []
    for k, tier in enumerate(tiers):
        ax = fig.add_subplot(gs[2 + k], sharex=axw)
        axes_t.append(ax)
        ax.set_yticks([]); ax.set_ylim(0, 1)
        ax.text(-0.005, 0.5, tier.name, transform=ax.transAxes, ha="right", va="center", fontsize=9, color=SEC)
        ax.axvspan(syl.start, syl.end, color=SHADE, zorder=0)
        if tier.kind == "interval":
            for iv in tier.intervals:
                ax.axvline(iv.start, color=GRID, lw=0.8); ax.axvline(iv.end, color=GRID, lw=0.8)
                width_chars = (iv.end - iv.start) / dur * 95   # ~95 characters fit across the panel
                if iv.label and not _is_pause(iv.label) and width_chars >= 1.2:
                    if len(iv.label) > width_chars and len(iv.label) <= 3:
                        continue
                    lab = iv.label if len(iv.label) <= width_chars else (iv.label[: max(1, int(width_chars) - 1)] + "…")
                    fw = "bold" if abs(iv.start - syl.start) < 1e-6 and abs(iv.end - syl.end) < 1e-6 else "normal"
                    ax.text((iv.start + iv.end) / 2, 0.5, lab, ha="center", va="center", fontsize=8.5,
                            color=INK, fontweight=fw, clip_on=True)
        else:
            last_lab = -1e9
            for j, p in enumerate(sorted(tier.points, key=lambda q: q.time)):
                ax.axvline(p.time, color=F0C, lw=1.2)
                if p.time - last_lab < 0.035 * dur:
                    continue
                last_lab = p.time
                short = p.label.split(" ")[1] if p.label.startswith("F0 ") else p.label.split(" ")[0].lower()
                ax.text(p.time, 0.78 if j % 2 == 0 else 0.25, " " + short, fontsize=7.5, color=F0C, va="center",
                        ha="left", clip_on=True)
        if k < n_t - 1:
            plt.setp(ax.get_xticklabels(), visible=False)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
    axes_t[-1].set_xlabel("Time (s)", color=SEC)

    # zoom on final syllable
    pad = 0.12
    z0, z1 = max(0, syl.start - pad), min(dur, syl.end + pad)
    axz = fig.add_subplot(gr[0])
    axz.axvspan(syl.start, syl.end, color=SHADE, zorder=0)
    zm = (t_f0 >= z0) & (t_f0 <= z1)
    axz.plot(t_f0[zm], f0[zm], "o", color=F0C, ms=4, zorder=3)
    axz.set_xlim(z0, z1)
    axz.set_title("Final-syllable domain", loc="left", fontsize=11, color=INK, fontweight="bold")
    axz.set_ylabel("F0 (Hz)", color=SEC); axz.set_xlabel("Time (s)", color=SEC)
    for s in ("top", "right"):
        axz.spines[s].set_visible(False)
    if cues.get("STATUS") == "completed":
        on = (cues["F0_ONSET_TIME"], cues["F0_ONSET_HZ"]); off = (cues["F0_OFFSET_TIME"], cues["F0_OFFSET_HZ"])
        pk = (cues["F0_PEAK_TIME"], cues["F0_PEAK_HZ"]); vl = (cues["F0_VALLEY_TIME"], cues["F0_VALLEY_HZ"])
        yv = f0[zm][~np.isnan(f0[zm])]
        ylo, yhi = (yv.min(), yv.max()) if yv.size else (lo, hi)
        span = max(yhi - ylo, 20)
        axz.set_ylim(ylo - 0.45 * span, yhi + 0.45 * span)
        if cls in ("rise-fall", "fall-rise"):
            # two fitted lines, one on each side of the turning point
            turn_t = pk[0] if cls == "rise-fall" else vl[0]
            vm = (t_f0 >= syl.start) & (t_f0 <= syl.end) & ~np.isnan(f0)
            tv_, sv_ = t_f0[vm], 12 * np.log2(f0[vm] / cues["REF_HZ"])
            for part in (tv_ <= turn_t + 1e-9, tv_ >= turn_t - 1e-9):
                if part.sum() >= 2:
                    b1_, b0_ = np.polyfit(tv_[part], sv_[part], 1)
                    xl = np.linspace(tv_[part][0], tv_[part][-1], 20)
                    axz.plot(xl, cues["REF_HZ"] * 2 ** ((b0_ + b1_ * xl) / 12), "--",
                             color=CLS.get(cls, INK), lw=1.8, zorder=4)
        else:
            xl = np.linspace(on[0], off[0], 40)        # fitted line over the voiced span
            yl = cues["REF_HZ"] * 2 ** ((cues["FIT_INTERCEPT_ST"] + cues["FINAL_SLOPE_ST"] * xl) / 12)
            axz.plot(xl, yl, "--", color=CLS.get(cls, INK), lw=1.8, zorder=4, label="fitted slope")
        marks = [("onset", on, (-10, 14), "right"), ("offset", off, (-10, -30), "right")]
        if abs(pk[0] - on[0]) > 0.015 and abs(pk[0] - off[0]) > 0.015:
            marks.append(("peak", pk, (0, 16), "center"))
        if abs(vl[0] - on[0]) > 0.015 and abs(vl[0] - off[0]) > 0.015:
            marks.append(("valley", vl, (0, -26), "center"))
        for name, (tt, hz), off_xy, ha in marks:
            axz.plot(tt, hz, "o", ms=9, mfc="white", mec=INK, mew=1.6, zorder=6)
            axz.annotate(f"{name}\n{tt:.3f} s · {hz:.0f} Hz", (tt, hz), xytext=off_xy, textcoords="offset points",
                         ha=ha, fontsize=8.5, color=INK, zorder=7)
        ytxt = ylo - 0.33 * span
        axz.annotate("", xy=(syl.start, ytxt), xytext=(syl.end, ytxt),
                     arrowprops=dict(arrowstyle="<->", color=SEC, lw=1.1))
        axz.text((syl.start + syl.end) / 2, ytxt - 0.06 * span,
                 f"final syllable {cues['FINAL_SYLLABLE_DURATION'] * 1000:.0f} ms", ha="center", va="top",
                 fontsize=8.5, color=SEC)
        vs, ve = cues.get("FINAL_VOWEL_START"), cues.get("FINAL_VOWEL_END")
        if vs == vs and vs is not None:                       # the vowel inside the syllable
            axz.axvspan(vs, ve, ymin=0.13, ymax=0.16, color=SEC, alpha=0.45, lw=0, zorder=1)
            axz.text(ve + 0.004, 0.145, "vowel", transform=axz.get_xaxis_transform(), ha="left",
                     va="center", fontsize=7.5, color=SEC)
        lv = cues.get("LAST_VOICED_TIME")
        if lv == lv and lv is not None and syl.end - lv > 0.03:
            axz.axvline(lv, color=SEC, lw=1, ls=":", zorder=2)
            axz.text(lv, 0.74, " F0 ends", transform=axz.get_xaxis_transform(), fontsize=8, color=SEC)
        if cls == "rise-fall":
            head = (f"RISE-FALL   {12 * np.log2(pk[1] / on[1]):+.1f} / {12 * np.log2(off[1] / pk[1]):+.1f} ST")
        elif cls == "fall-rise":
            head = (f"FALL-RISE   {12 * np.log2(vl[1] / on[1]):+.1f} / {12 * np.log2(off[1] / vl[1]):+.1f} ST")
        else:
            head = f"{cls.upper()}   {cues['FINAL_SLOPE_ST']:+.1f} ST/s (fitted)"
        axz.text(0.02, 0.97, head, transform=axz.transAxes,
                 fontsize=15, fontweight="bold", color=CLS.get(cls, INK), va="top")
    else:
        axz.text(0.5, 0.5, "No voiced F0 in the final syllable", transform=axz.transAxes, ha="center", color=SEC)

    # cue table
    try:
        from .ftobi_annotator import sampa_to_ipa
        syl_ipa = f"[{sampa_to_ipa(syl.label)[0]}]" if syl.label and "auto" not in syl.label else syl.label
    except Exception:
        syl_ipa = syl.label
    axc = fig.add_subplot(gr[2]); axc.axis("off")
    if cues.get("STATUS") == "completed":
        cov = cues.get("FINAL_VOWEL_F0_COVERAGE")
        rows = [("Final syllable", f"{syl_ipa}  [{syl.start:.3f}–{syl.end:.3f} s]"),
                ("Duration", f"{cues['FINAL_SYLLABLE_DURATION'] * 1000:.0f} ms"),
                ("F0 on final vowel", (f"{cov * 100:.0f}%" if cov == cov and cov is not None else "n/a")
                 + ("  ⚠ check: creak or below floor?" if cues.get("QC_FINAL_VOWEL_LOW_F0") else "")),
                ("F0 onset", f"{cues['F0_ONSET_HZ']:.0f} Hz at {cues['F0_ONSET_TIME']:.3f} s"),
                ("F0 peak", f"{cues['F0_PEAK_HZ']:.0f} Hz at {cues['F0_PEAK_TIME']:.3f} s"),
                ("F0 offset", f"{cues['F0_OFFSET_HZ']:.0f} Hz at {cues['F0_OFFSET_TIME']:.3f} s"),
                ("Change onset→offset", f"{cues['F0_CHANGE_ST']:+.1f} ST"),
                ("Fitted slope", f"{cues['FINAL_SLOPE_ST']:+.1f} ST/s (endpoint {cues['FINAL_SLOPE_ENDPOINT_ST']:+.1f})"),
                ("Peak alignment", f"{cues['PEAK_ALIGNMENT_S'] * 1000:.0f} ms ({cues['PEAK_ALIGNMENT_PROP'] * 100:.0f}% of syllable)"),
                ("Intensity", f"{cues['FINAL_INTENSITY_MEAN_DB']:.1f} dB"),
                ("Contour", f"{cls}" + (f" (slope rule alone: {cues.get('CONTOUR_SLOPE_CLASS')})" if cls in ("rise-fall", "fall-rise") else "")
                 + ("   ⚠ check: F0 jump %.0f ST" % cues["MAX_F0_JUMP_ST"] if cues.get("QC_OCTAVE_JUMP") else ""))]
    else:
        rows = [("Final syllable", f"{syl_ipa}  [{syl.start:.3f}–{syl.end:.3f} s]"), ("Status", cues.get("STATUS", ""))]
    y = 0.98
    for k_, v_ in rows:
        axc.text(0.0, y, k_, fontsize=9.5, color=SEC, va="top", transform=axc.transAxes)
        axc.text(0.42, y, v_, fontsize=9.5, color=INK, va="top", transform=axc.transAxes)
        y -= 0.088

    fig.savefig(out_png, dpi=150)
    if out_svg:
        fig.savefig(out_svg)
    plt.close(fig)


# ---------------------------------------------------------------------------
# One token
# ---------------------------------------------------------------------------
def process_token(wav: Path, textgrid: Optional[Path], out_dir: Path, tier="MAS", force_auto=False,
                  slope_threshold=1.5, fixed_range: Optional[Tuple[float, float]] = None,
                  svg=False, pitch=None) -> Dict:
    """pitch: optional precomputed (times, f0, (floor, ceiling)) so that a combined run
    tracks F0 once per file; identical to what adaptive_pitch would return."""
    stem = re.sub(r"\s+copy$", "", wav.stem, flags=re.I)
    m = re.match(r"^(.+?)tw([1-4])$", stem, flags=re.I)      # PFC names only (xxxtw1/2/3 questions, tw4 statement)
    qnum = m.group(2) if m else ""
    speaker = m.group(1) if m else stem
    row: Dict = {"TOKEN_ID": f"{speaker}tw_{sentence_id(qnum)}" if qnum else stem, "SPEAKER_ID": speaker,
                 "SENTENCE_ID": sentence_id(qnum), "AUDIO_FILE": wav.name,
                 "TEXTGRID_IN": textgrid.name if textgrid else "",
                 "PITCH_ENGINE": "Praat (Parselmouth)" if HAVE_PARSELMOUTH else "built-in autocorrelation (Praat-style)"}
    x, sr = load_wav(wav)
    dur = len(x) / sr
    t_f0, f0, rng = pitch if pitch is not None else adaptive_pitch(x, sr, fixed=fixed_range)
    f0 = f0.copy()
    t_int, db = track_intensity(x, sr, min_pitch=max(rng[0], 50.0))
    row["PITCH_FLOOR_HZ"], row["PITCH_CEILING_HZ"] = rng
    voiced = f0[~np.isnan(f0)]
    ref = float(np.median(voiced)) if voiced.size else 100.0
    row["F0_MEDIAN_HZ_FILE"] = ref

    tg_in = read_textgrid(textgrid) if textgrid else None
    syl, src_tier = (None, "")
    if tg_in and not force_auto:
        syl, src_tier = final_interval(tg_in, [tier] + SYLLABLE_TIERS, stem)
    sounding = detect_silences(t_int, db)
    nuclei, sm = syllable_nuclei(t_int, db, t_f0, f0, sounding)
    auto_syl = auto_syllables(t_int, sm, nuclei, sounding)

    if syl is None:
        if not auto_syl:
            row.update(STATUS="failed", ERROR="no syllable nuclei detected")
            return row
        syl = auto_syl[-1]
        end = syl.end
        last_nuc = max(n for n in nuclei if n <= syl.end + 1e-9)
        gap, step = 0.0, float(t_f0[1] - t_f0[0])
        for tt, ff in zip(t_f0, f0):           # follow voicing past the intensity cut-off
            if tt <= last_nuc:
                continue
            if np.isnan(ff):
                gap += step
                if gap > 0.03:
                    break
            else:
                gap = 0.0
                end = max(end, tt + step / 2)
        syl = Interval(syl.start, min(end, dur), "final syl (auto)")
        auto_syl[-1] = Interval(auto_syl[-1].start, syl.end, auto_syl[-1].label)
        src_tier = "SYL-AUTO"
        row["SEGMENTATION"] = "automatic (silences + intensity nuclei)"
    else:
        row["SEGMENTATION"] = f"TextGrid tier {src_tier}"
    row["FINAL_DOMAIN_TIER"] = src_tier
    row["AUTO_SYLLABLE_COUNT"] = len(auto_syl)

    cues = measure_cues(t_f0, f0, t_int, db, syl, ref, slope_threshold)
    cues.update(final_vowel_coverage(tg_in if src_tier != "SYL-AUTO" else None, syl, t_f0, f0))
    row.update(cues)

    # Build the output TextGrid: original tiers (or automatic ones) + FINAL-DOMAIN + CUES
    tg_out = TextGrid(0.0, dur)
    if tg_in:
        tg_out.xmin, tg_out.xmax = tg_in.xmin, max(tg_in.xmax, dur)
        tg_out.tiers = list(tg_in.tiers)
    if not tg_in or src_tier == "SYL-AUTO":
        sentence = PFC_QUESTIONS.get(qnum, "")
        utt = Tier("UTT-AUTO", "interval",
                   [Interval(s, e, sentence if i == len(sounding) - 1 or len(sounding) == 1 else "…")
                    for i, (s, e) in enumerate(sounding)])
        if len(sounding) > 1:
            utt.intervals = [Interval(sounding[0][0], sounding[-1][1], sentence)]
        tg_out.tiers += [utt, Tier("SYL-AUTO", "interval", auto_syl)]
    tg_out.tiers += final_syllable_tiers(tg_in, syl, PFC_FINAL_WORD.get(qnum, "final word"), cues,
                                         auto=(src_tier == "SYL-AUTO"))
    out_dir.mkdir(parents=True, exist_ok=True)
    tg_path = out_dir / f"{stem}_cues.TextGrid"
    write_textgrid(tg_out, tg_path)

    # figure: show the most informative tiers
    show = []
    word_t = next((tg_out.get(n) for n in WORD_TIERS if tg_out.get(n) and tg_out.get(n).kind == "interval"), None)
    for t in [word_t, tg_out.get(src_tier) if src_tier != "SYL-AUTO" else None,
              tg_out.get("UTT-AUTO"), tg_out.get("SYL-AUTO"),
              _figure_phones(tg_out.get("FINAL-PHONES")) or tg_out.get("FINAL-DOMAIN"), tg_out.get("CUES")]:
        if t is not None and t not in show:
            show.append(t)
    note = (f"Pitch: {row['PITCH_ENGINE']}, speaker-adaptive range {rng[0]:.0f}–{rng[1]:.0f} Hz  ·  "
            f"final domain from {row['SEGMENTATION']}  ·  shaded = final syllable")
    png = out_dir / f"{stem}_final_domain.png"
    draw_figure(row["TOKEN_ID"], x, sr, t_f0, f0, rng, show, syl, cues,
                PFC_QUESTIONS.get(qnum, ""), note, png, out_dir / f"{stem}_final_domain.svg" if svg else None)
    row["FIGURE_FILE"] = png.name
    row["CUES_TEXTGRID"] = tg_path.name
    row["TOTAL_DURATION"] = dur
    return row


# ---------------------------------------------------------------------------
# Batch
# ---------------------------------------------------------------------------
SYLLABLE_TIERS = ["MAS", "syllabe", "syllable", "sylable", "syllables", "syll"]
WORD_TIERS = ["ORT-MAU", "words", "word", "ORT", "mots"]


def match_textgrid(wav: Path, textgrids: List[Path]) -> Optional[Path]:
    """Exact stem match first. Otherwise accept a suffixed name for the SAME token
    (e.g. 64aab1tw1R.TextGrid, 64aab1tw2m.TextGrid, 'x copy.TextGrid'), never another
    question: the character after the stem must not be a digit. Among several,
    prefer one with a syllable interval tier (MAS), then the shortest name."""
    stem = wav.stem.lower()
    exact = [t for t in textgrids if re.sub(r"\s+copy$", "", t.stem, flags=re.I).lower() == stem]
    cands = exact or [t for t in textgrids
                      if t.stem.lower().startswith(stem) and not t.stem[len(stem):len(stem) + 1].isdigit()]
    if not cands:
        return None

    def has_syll(t):
        try:
            tg = read_textgrid(t)
            return any(tg.get(n) and tg.get(n).kind == "interval" for n in SYLLABLE_TIERS)
        except Exception:
            return False
    return sorted(cands, key=lambda t: (not has_syll(t), len(t.stem)))[0]
PRAAT_CHECK_COLS = ["AUDIO_FILE", "PITCH_FLOOR_HZ", "PITCH_CEILING_HZ", "FINAL_SYLLABLE_START", "FINAL_SYLLABLE_END",
                    "FINAL_SYLLABLE_DURATION", "F0_ONSET_HZ", "F0_PEAK_HZ", "F0_OFFSET_HZ", "FINAL_SLOPE_ST",
                    "F0_CHANGE_ST", "FINAL_INTENSITY_MEAN_DB", "CONTOUR_CLASS"]


def write_praat_check(df: pd.DataFrame, out: Path) -> None:
    """Small, comma-free table read by praat/verify_final_domain.praat and draw_final_domain.praat."""
    if "STATUS" not in df.columns:
        return
    d = df[df.STATUS == "completed"]
    d[[c for c in PRAAT_CHECK_COLS if c in d.columns]].to_csv(out / "final_domain_praat_check.csv", index=False)


def run_folder(folder: str | Path, out: str | Path, **kw) -> pd.DataFrame:
    folder, out = Path(folder), Path(out)
    wavs = sorted(p for p in folder.iterdir() if p.suffix.lower() == ".wav" and not p.name.startswith("."))
    all_tgs = [p for p in folder.iterdir() if p.suffix.lower() == ".textgrid" and not p.name.startswith(".")]
    rows = []
    for i, w in enumerate(wavs, 1):
        tg = match_textgrid(w, all_tgs)
        print(f"[{i}/{len(wavs)}] {w.name}  textgrid: {tg.name if tg else 'none -> automatic'}")
        try:
            rows.append(process_token(w, tg, out, **kw))
        except Exception as e:  # keep going; the row records the failure
            rows.append({"AUDIO_FILE": w.name, "STATUS": "failed", "ERROR": str(e)})
    df = pd.DataFrame(rows)
    first = ["TOKEN_ID", "SPEAKER_ID", "SENTENCE_ID", "STATUS", "CONTOUR_CLASS", "QC_OCTAVE_JUMP", "FINAL_SLOPE_ST",
             "FINAL_SLOPE_ENDPOINT_ST", "F0_CHANGE_ST", "FINAL_SYLLABLE_DURATION", "FINAL_SYLLABLE_START",
             "FINAL_SYLLABLE_END", "F0_ONSET_TIME", "F0_ONSET_HZ", "F0_PEAK_TIME", "F0_PEAK_HZ",
             "F0_VALLEY_TIME", "F0_VALLEY_HZ", "F0_OFFSET_TIME", "F0_OFFSET_HZ", "PEAK_ALIGNMENT_S",
             "PEAK_ALIGNMENT_PROP", "FINAL_INTENSITY_MEAN_DB", "SEGMENTATION", "FINAL_DOMAIN_TIER",
             "PITCH_ENGINE", "PITCH_FLOOR_HZ", "PITCH_CEILING_HZ", "AUDIO_FILE", "TEXTGRID_IN",
             "CUES_TEXTGRID", "FIGURE_FILE"]
    df = df[[c for c in first if c in df.columns] + [c for c in df.columns if c not in first]]
    out.mkdir(parents=True, exist_ok=True)
    df.to_csv(out / "final_domain_cues.csv", index=False, encoding=CSV_ENCODING)
    write_praat_check(df, out)
    with pd.ExcelWriter(out / "final_domain_cues.xlsx", engine="openpyxl") as xw:
        df.to_excel(xw, sheet_name="FINAL_DOMAIN_CUES", index=False)
    print(f"\nDone: {len(df)} tokens -> {out}")
    return df


def main():
    ap = argparse.ArgumentParser(description="IntonaSphere AI final-domain visualizer")
    ap.add_argument("--folder", required=True, help="Folder with .wav (and optional same-name .TextGrid) files")
    ap.add_argument("--out", default="outputs/final_domain")
    ap.add_argument("--tier", default="MAS", help="Syllable tier in the WebMAUS TextGrid")
    ap.add_argument("--force-auto", action="store_true", help="Ignore TextGrids; segment automatically")
    ap.add_argument("--slope-threshold", type=float, default=1.5, help="ST/s boundary for rise/fall vs plateau")
    ap.add_argument("--pitch-range", nargs=2, type=float, metavar=("FLOOR", "CEILING"),
                    help="Fixed pitch range in Hz instead of the speaker-adaptive two-pass range")
    ap.add_argument("--svg", action="store_true", help="Also save each figure as SVG")
    a = ap.parse_args()
    run_folder(user_path(a.folder), user_path(a.out), tier=a.tier, force_auto=a.force_auto, slope_threshold=a.slope_threshold,
               fixed_range=tuple(a.pitch_range) if a.pitch_range else None, svg=a.svg)


if __name__ == "__main__":
    main()
