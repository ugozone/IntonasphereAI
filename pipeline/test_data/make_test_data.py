"""
Builds the synthetic test recordings used by the self-test (no real speaker, no corpus data).

    python test_data/make_test_data.py

synth_question.wav  + synth_question.TextGrid   "la banane"  rising final F0   (WAV + TextGrid route)
synth_statement.wav + synth_statement.txt       "la banane"  falling final F0  (WAV + .txt -> WebMAUS route)

The voice is a glottal pulse train shaped by fixed /a/ formants, with a noise burst for each
consonant, so the pitch tracker, the syllable segmentation and the contour classes can be tested.
WebMAUS will still align it, although it is not real French speech.
"""
from __future__ import annotations

import wave
from pathlib import Path

import numpy as np
from scipy.signal import lfilter

SR = 16000
HERE = Path(__file__).resolve().parent
# (phone SAMPA, duration s, voiced?)
PHONES = [("l", 0.06, True), ("a", 0.14, True), ("b", 0.05, False), ("a", 0.15, True),
          ("n", 0.06, True), ("a", 0.30, True), ("n", 0.07, True)]
SYLLABLES = [("l a", 0, 2), ("b a", 2, 4), ("n a n", 4, 7)]       # phone index ranges


def formant(x, f, bw):
    r = np.exp(-np.pi * bw / SR)
    a = [1, -2 * r * np.cos(2 * np.pi * f / SR), r * r]
    return lfilter([1 - r], a, x)


def synth(f0_end_ratio: float):
    lead, tail = 0.25, 0.30
    dur = sum(p[1] for p in PHONES)
    n = int((lead + dur + tail) * SR)
    t = np.arange(n) / SR
    # F0: 190 Hz, gently declining, then a final rise or fall over the last syllable
    f0 = np.full(n, 190.0) - 15 * (t - lead) / dur
    start_last = lead + sum(p[1] for p in PHONES[:4])
    k = t >= start_last
    prog = np.clip((t[k] - start_last) / (lead + dur - start_last), 0, 1)
    f0[k] = f0[k] * (1 + (f0_end_ratio - 1) * prog)
    phase = np.cumsum(f0 / SR)
    pulses = np.diff(np.floor(phase), prepend=0.0)
    voice = formant(formant(formant(pulses, 700, 90), 1200, 110), 2600, 160)
    voice = voice / np.max(np.abs(voice))
    noise = formant(np.random.default_rng(1).normal(0, 1, n), 3000, 800)
    noise = noise / np.max(np.abs(noise))
    out = np.zeros(n)
    times, cur = [], lead
    for ph, d, voiced in PHONES:
        a, b = int(cur * SR), int((cur + d) * SR)
        if voiced:
            out[a:b] = voice[a:b] * (1.0 if ph == "a" else 0.35)
        else:
            out[a:b] = noise[a:b] * 0.08
        times.append((cur, cur + d, ph))
        cur += d
    ramp = int(0.01 * SR)
    env = np.ones(n)
    for s, e, _ in times:                       # smooth phone edges
        a, b = int(s * SR), int(e * SR)
        env[a:a + ramp] = np.minimum(env[a:a + ramp], np.linspace(0.3, 1, ramp))
    out *= env
    out = 0.6 * out / np.max(np.abs(out))
    return out, times, lead + dur + tail


def write_wav(path: Path, x):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes((x * 32767).astype("<i2").tobytes())


def tier(name, total, items):
    """items: list of (start, end, label) covering speech; gaps are filled with empty intervals."""
    iv, cur = [], 0.0
    for s, e, lab in items:
        if s > cur + 1e-6:
            iv.append((cur, s, ""))
        iv.append((s, e, lab)); cur = e
    if cur < total - 1e-6:
        iv.append((cur, total, ""))
    lines = [f'    item [{{}}]:', '        class = "IntervalTier"', f'        name = "{name}"',
             '        xmin = 0', f'        xmax = {total:.4f}', f'        intervals: size = {len(iv)}']
    for k, (s, e, lab) in enumerate(iv, 1):
        lines += [f'        intervals [{k}]:', f'            xmin = {s:.4f}', f'            xmax = {e:.4f}',
                  f'            text = "{lab}"']
    return lines


def write_textgrid(path: Path, times, total):
    words = [(times[0][0], times[1][1], "la"), (times[2][0], times[-1][1], "banane")]
    phones = times
    syl = [(times[a][0], times[b - 1][1], lab) for lab, a, b in SYLLABLES]
    tiers = [tier("ORT-MAU", total, words), tier("MAU", total, phones), tier("MAS", total, syl)]
    out = ['File type = "ooTextFile"', 'Object class = "TextGrid"', '', 'xmin = 0', f'xmax = {total:.4f}',
           'tiers? <exists>', f'size = {len(tiers)}', 'item []:']
    for i, t in enumerate(tiers, 1):
        t = list(t); t[0] = t[0].format(i); out += t
    path.write_text("\n".join(out) + "\n", encoding="utf-8")


def main():
    x, times, total = synth(1.45)             # final rise of about +6 ST
    write_wav(HERE / "synth_question.wav", x)
    write_textgrid(HERE / "synth_question.TextGrid", times, total)
    x, times, total = synth(0.72)             # final fall of about -6 ST
    write_wav(HERE / "synth_statement.wav", x)
    (HERE / "synth_statement.txt").write_text("la banane\n", encoding="utf-8")
    print("Wrote synth_question.wav/.TextGrid and synth_statement.wav/.txt in", HERE)


if __name__ == "__main__":
    main()
