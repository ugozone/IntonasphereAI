"""Checks the low-floor rescue of the final syllable (modules/final_domain_visualizer.py) on
synthetic voices: a low ending is recovered, an ending that jumps (octave error / creak) is not.

    cd pipeline && python tests/test_rescue.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np

import modules.final_domain_visualizer as fdv
from modules.final_domain_visualizer import (Interval, track_pitch, rescue_final_syllable, measure_cues,
                                             RESCUE_FLOOR_HZ)

SR = 16000


def voice(f0_track, sr=SR):
    """Harmonic 'voice' following an F0 track given per sample (Hz); 0 = silence."""
    ph = 2 * np.pi * np.cumsum(f0_track) / sr
    x = sum(np.sin(k * ph) / k for k in range(1, 8))
    return 0.3 * x * (f0_track > 0)


def contour(knots, dur):
    t = np.arange(int(dur * SR)) / SR
    return np.interp(t, [k[0] for k in knots], [k[1] for k in knots])


def main():
    fdv.HAVE_PARSELMOUTH = False            # same tracker on every computer, so the numbers are reproducible
    floor, ceiling = 117.0, 300.0           # a speaker range that cuts off a low ending
    syl = Interval(1.20, 1.50, "nœʁ")
    # 1. a smooth fall from 160 Hz to 70 Hz on the final syllable: recovered
    x = voice(contour([(0, 0), (0.1, 0), (0.1001, 170), (1.2, 150), (1.5, 70), (1.5001, 0), (1.7, 0)], 1.7))
    t, f = track_pitch(x, SR, floor, ceiling, 0.01)
    in_syl = (t >= syl.start) & (t <= syl.end)
    before = int((~np.isnan(f[in_syl])).sum())
    new, why = rescue_final_syllable(x, SR, syl, t, f, ceiling, floor)
    assert new is not None, why
    after = int((~np.isnan(new[in_syl])).sum())
    assert after > before, (before, after)
    assert np.nanmin(new[in_syl]) < floor, "the rescued frames go below the speaker floor"
    c = measure_cues(t, new, t, np.full_like(t, 60.0), syl, 150.0)
    assert c["STATUS"] == "completed" and c["F0_CHANGE_ST"] < -3, c.get("F0_CHANGE_ST")
    # 2. an ending that drops by an octave at once (halving / creak): not accepted
    x2 = voice(contour([(0, 0), (0.1, 0), (0.1001, 170), (1.3, 160), (1.3001, 75), (1.5, 72), (1.5001, 0), (1.7, 0)], 1.7))
    t2, f2 = track_pitch(x2, SR, floor, ceiling, 0.01)
    new2, why2 = rescue_final_syllable(x2, SR, syl, t2, f2, ceiling, floor)
    assert new2 is None and "jump" in why2, why2
    # 3. nothing to do when the floor is already at the rescue floor
    assert rescue_final_syllable(x, SR, syl, t, f, ceiling, RESCUE_FLOOR_HZ)[0] is None
    print("low-floor rescue: all checks passed")


if __name__ == "__main__":
    main()
