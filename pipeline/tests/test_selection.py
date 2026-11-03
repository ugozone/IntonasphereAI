"""Checks every branch of the token-selection rule (modules/selection.py) on made-up rows.

    cd pipeline && python tests/test_selection.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from modules.selection import (select, token_flow, token_flow_by_site, check_final_group, INCLUDE, EXCLUDE,
                               CHECK, REPAIR, PENDING_DATA, PENDING_META, SELECTION_COLUMNS)

Q = {"Q1": "Le Premier ministre ira-t-il à Beaulieu",
     "Q2": "Qu'est-ce qui a donc valu à Beaulieu ce grand honneur",
     "Q3": "Comment en plus éviter les manifestations qui ont eu tendance à se multiplier lors des visites officielles",
     "S4": "Le village de Beaulieu est en grand émoi"}


def tok(code, s, text=None, **kw):
    base = dict(TOKEN_ID=f"{code}tw_{s}", SPEAKER_ID=f"{code}tw", SENTENCE_ID=s, SENTENCE_TEXT=text or Q[s],
                SITE_ID="Bamako", CONTINENT="Africa", AGE=50, AGE_GROUP="Older", SEX="F",
                SPEECH_RATE_SYLL_PER_SEC=5.0, FINAL_SYLLABLE_DURATION=0.25, TEXTGRID_FILE=f"{code}tw{s[-1]}.TextGrid",
                AUDIO_FILE=f"{code}tw{s[-1]}.wav")
    base.update(kw)
    return base


def tokens_extra(code, s, **kw):
    return dict(AUDIO_FILE=f"{code}tw{s[-1]}.wav", ALIGNMENT_SOURCE="user_textgrid",
                FINAL_DOMAIN_STATUS=kw.pop("status", "completed"),
                FINAL_VOWEL_F0_COVERAGE=kw.pop("cov", 0.9), QC_FINAL_VOWEL_LOW_F0=kw.pop("low", False),
                QC_OCTAVE_JUMP=kw.pop("jump", False), CONTOUR_VS_BOUNDARY_TONE=kw.pop("cvb", "agree"))


def main():
    # final-word-group check
    assert check_final_group(Q["Q2"], "Q2")[0] is True
    assert check_final_group("Qu'est-ce qui a donc valu à Beaulieu ce grand euh grand honneur", "Q2")[0] is False
    assert check_final_group("Le premier ministre ira-t-il", "Q1")[0] is False
    ok, _, notes = check_final_group("Le euh le village de Beaulieu est en grand émoi", "S4")
    assert ok is True and notes, "an early hesitation is noted but not excluded"

    ds, at = [], []
    cases = {  # code: (sentence, dataset changes, ALL_TOKENS changes, expected decision, flagged)
        "a01": ("Q1", {}, {}, INCLUDE, "no"),
        "a02": ("Q2", {}, {"status": "no_voiced_f0_in_final_syllable"}, EXCLUDE, "no"),        # (a)
        "a03": ("Q3", {"SPEECH_RATE_SYLL_PER_SEC": 1.4}, {}, CHECK, "no"),                     # (b)
        "a04": ("Q2", {"SENTENCE_TEXT": "Qu'est-ce qui a donc valu à Beaulieu ce grand euh grand honneur"}, {}, EXCLUDE, "no"),  # (c)
        "a05": ("Q1", {}, {"low": True, "cov": 0.3}, INCLUDE, "yes"),                          # flag
        "a06": ("Q1", {}, {"jump": True}, INCLUDE, "yes"),
        "a07": ("Q3", {"FINAL_SYLLABLE_DURATION": 0.71}, {}, INCLUDE, "yes"),
        "a08": ("Q2", {}, {"cvb": "rise vs L%: check"}, INCLUDE, "yes"),
        "a09": ("Q1", {"TEXTGRID_FILE": ""}, {}, REPAIR, "no"),
        "a10": ("S4", {}, {}, INCLUDE, "no"),
        "a11": ("Q1", {"SITE_ID": None}, {}, PENDING_META, "no"),
    }
    for code, (s, d, t, *_ ) in cases.items():
        ds.append(tok(code, s, **d))
        at.append(tokens_extra(code, s, **t))
    # a10 also has all three questions -> complete case and RQ4 set
    for s in ("Q2", "Q3"):
        ds.append(tok("a10", s)); at.append(tokens_extra("a10", s))
    ds.append(tok("a10", "Q1")); at.append(tokens_extra("a10", "Q1"))
    speakers = pd.DataFrame({"SITE_ID": ["Bamako"] * 11, "CONTINENT": ["Africa"] * 11, "AGE": [50] * 11,
                             "AGE_GROUP": ["Older"] * 11, "SEX": ["F"] * 11},
                            index=pd.Index([f"a{i:02d}" for i in range(1, 11)] + ["zz9"], name="CODE"))
    overrides = pd.DataFrame({"TOKEN_ID": ["a03tw_Q3"], "CHECKED": ["yes"], "MANUAL_DECISION": ["Exclude"],
                              "MANUAL_NOTE": ["listened: file contains the next sentence"]}).set_index("TOKEN_ID")
    sel = select(pd.DataFrame(ds), pd.DataFrame(at), speakers, overrides)
    assert list(sel.columns) == SELECTION_COLUMNS
    by = sel.set_index("TOKEN_ID")
    for code, (s, _, _, want, flagged) in cases.items():
        r = by.loc[f"{code}tw_{s}"]
        assert r["AUTO_DECISION"] == want, (code, r["AUTO_DECISION"], r["AUTO_REASON"])
        assert r["FLAGGED"] == flagged, (code, r["FLAGS"])
    assert by.loc["a03tw_Q3", "SELECTION_DECISION"] == EXCLUDE, "a manual decision overrides the automatic one"
    assert by.loc["zz9tw_S4", "AUTO_DECISION"] == PENDING_DATA, "planned S4 row for a speaker without recordings"
    assert by.loc["a10tw_S4", "COMPLETE_CASE_SET"] == "yes" and by.loc["a10tw_S4", "RQ4_SET"] == "yes"
    assert by.loc["a01tw_Q1", "COMPLETE_CASE_SET"] == "no" and by.loc["a01tw_Q1", "RQ4_SET"] == "no"
    flow = token_flow(sel).set_index("STEP")
    assert flow.loc[INCLUDE, "ALL"] == int((sel["SELECTION_DECISION"] == INCLUDE).sum())
    assert flow.loc["Speakers in the RQ4 set (S4 and at least one question included)", "ALL"] == 1
    site = token_flow_by_site(sel)
    assert site["TOTAL"].sum() == len(sel)
    print(f"token selection: all {len(cases) + 6} checks passed")


if __name__ == "__main__":
    main()
