"""Checks modules/review_list.py on a small made-up results workbook.

    cd pipeline && python tests/test_review_list.py
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from modules.review_list import build, REVIEW_COLUMNS
from modules.selection import EXCLUDE, CHECK, INCLUDE


def main():
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        sel = pd.DataFrame([
            dict(TOKEN_ID="a01tw_Q1", SITE_ID="Bangui", AUDIO_FILE="a01tw1.wav", AUTO_DECISION=EXCLUDE,
                 AUTO_REASON="(a) no F0 in the final syllable", TRANSCRIPT_SOURCE="your TextGrid"),
            dict(TOKEN_ID="a02tw_Q2", SITE_ID="Bamako", AUDIO_FILE="a02tw2.wav", AUTO_DECISION=CHECK,
                 AUTO_REASON="(b) articulation rate 1.8", TRANSCRIPT_SOURCE="your TextGrid"),
            dict(TOKEN_ID="a03tw_Q3", SITE_ID="Lacaune", AUDIO_FILE="a03tw3.wav", AUTO_DECISION=INCLUDE,
                 AUTO_REASON="meets all criteria", TRANSCRIPT_SOURCE="WebMAUS from pfc_texte_lu (hesitations not transcribed)"),
            dict(TOKEN_ID="a04tw_Q1", SITE_ID="Lacaune", AUDIO_FILE="a04tw1.wav", AUTO_DECISION=INCLUDE,
                 AUTO_REASON="meets all criteria", TRANSCRIPT_SOURCE="your TextGrid"),
            dict(TOKEN_ID="a05tw_Q1", SITE_ID="Bangui", AUDIO_FILE="a05tw1.wav", AUTO_DECISION=EXCLUDE,
                 AUTO_REASON="(c) final word group repeated", TRANSCRIPT_SOURCE="your TextGrid"),
            dict(TOKEN_ID="a06tw_Q2", SITE_ID="Lacaune", AUDIO_FILE="a06tw2.wav", AUTO_DECISION=INCLUDE,
                 AUTO_REASON="meets all criteria", TRANSCRIPT_SOURCE="WebMAUS (cached alignment; hesitations may not be transcribed)"),
            dict(TOKEN_ID="a07tw_S4", SITE_ID="x", AUTO_DECISION="Pending – no data", AUTO_REASON="no recording"),
        ])
        files = [f"a0{i}tw{q}.wav" for i, q in [(1, 1), (2, 2), (3, 3), (4, 1), (5, 1), (6, 2)]]
        at = pd.DataFrame({"AUDIO_FILE": files, "TEXTGRID_USED": [f"/data/{f[:-4]}.TextGrid" for f in files]})
        fd = pd.DataFrame({"AUDIO_FILE": files, "FINAL_SYLLABLE_START": [2.0, 5.0, 6.0, 1.0, 1.0, 0.5],
                           "FINAL_SYLLABLE_END": [2.3, 5.4, 6.5, 1.2, 1.3, 0.8]})
        ds = pd.DataFrame({"AUDIO_FILE": files, "EXTRACTION_END": [2.3, 5.4, 6.5, 1.2, 1.3, 0.8]})
        res = d / "intonasphere_results.xlsx"
        with pd.ExcelWriter(res, engine="openpyxl") as xw:
            for name, df in (("SELECTION", sel), ("ALL_TOKENS", at), ("FINAL_DOMAIN", fd), ("DATASET", ds)):
                df.to_excel(xw, sheet_name=name, index=False)
        ov = d / "manual_overrides.csv"
        ov.write_text("TOKEN_ID,CHECKED,MANUAL_DECISION,MANUAL_NOTE\na06tw_Q2,yes,Include,listened\n", encoding="utf-8-sig")
        lst = build(res, Path("/data"), [1, 2, 3], ov, include_checked=False)
        assert list(lst.columns) == REVIEW_COLUMNS
        got = dict(zip(lst["TOKEN_ID"], lst["TASK"]))
        assert got == {"a01tw_Q1": 1, "a02tw_Q2": 2, "a03tw_Q3": 3}, got      # a06 already checked, a04/a05/a07 not listed
        r1 = lst.set_index("TOKEN_ID").loc["a01tw_Q1"]
        assert abs(r1["ZOOM_START"] - 0.5) < 1e-9 and abs(r1["ZOOM_END"] - 2.6) < 1e-9
        assert r1["AUDIO_PATH"] == str(Path("/data") / "a01tw1.wav") and r1["TEXTGRID_PATH"] == "/data/a01tw1.TextGrid"
        r2 = lst.set_index("TOKEN_ID").loc["a02tw_Q2"]
        assert r2["ZOOM_START"] == 0 and r2["ZOOM_END"] == 0, "check 2 shows the whole file"
        assert "a06tw_Q2" in set(build(res, Path("/data"), [3], ov, include_checked=True)["TOKEN_ID"])
        assert list(lst["ORDER"]) == [1, 2, 3]
    print("review list: all checks passed")


if __name__ == "__main__":
    main()
