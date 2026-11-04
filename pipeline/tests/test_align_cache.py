"""Checks how modules/auto_align.py reuses cached WebMAUS alignments: the text source is recorded,
and a recording whose .txt has changed since it was aligned is aligned again.

    cd pipeline && python tests/test_align_cache.py
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
from scipy.io import wavfile

import modules.auto_align as aa


def main():
    with tempfile.TemporaryDirectory() as d:
        d = Path(d); data, al = d / "data", d / "aligned"
        data.mkdir(); al.mkdir()
        for stem in ("x01tw4", "x02tw4", "x03tw4"):
            wavfile.write(data / f"{stem}.wav", 16000, np.zeros(1600, dtype=np.int16))
            (al / f"{stem}.TextGrid").write_text("cached", encoding="utf-8")
            (al / f"{stem}.txt").write_text("Le village de Beaulieu est en grand émoi.\n", encoding="utf-8")
        (data / "x01tw4.txt").write_text("Le village de Beaulieu est en grand émoi.\n", encoding="utf-8")   # same text
        (data / "x02tw4.txt").write_text("Le village de Beaulieu est en émoi.\n", encoding="utf-8")         # changed
        calls = []
        aa.webmaus = lambda w, text, out, lang: (calls.append(w.name), out.write_text("new", encoding="utf-8"), "webmaus")[-1]
        res = {r.wav.name: r for r in aa.ensure_alignments(data, al, mode="pfc", log=lambda *a: None)}
        assert res["x01tw4.wav"].text_source == "user_txt (cached)", res["x01tw4.wav"].text_source
        assert res["x03tw4.wav"].text_source == "pfc_texte_lu (cached)", res["x03tw4.wav"].text_source
        assert calls == ["x02tw4.wav"] and res["x02tw4.wav"].text_source == "user_txt", (calls, res["x02tw4.wav"])
        res = {r.wav.name: r for r in aa.ensure_alignments(data, al, mode="none", log=lambda *a: None)}
        assert res["x02tw4.wav"].alignment_source == "webmaus (cached)"
    print("alignment cache: all checks passed")


if __name__ == "__main__":
    main()
