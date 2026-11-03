# PFC master sheet (Q1–Q3 and S4) and token-selection rule

After every token-level extraction (`token_level_praat_extractor.py` or the
Research batch tab in the app), IntonaSphere AI writes `<output>_MASTER.xlsx`
and `<output>_MASTER_token_flow.csv` next to the extraction output, provided the
template workbook contains a `combined speaker table` sheet. The logic lives in
`modules/master_sheet.py`; disable it with `--no_master`.

## What the master sheet contains

One row per planned token (speaker × sentence), including speakers and sentences
that have not been measured yet. The sentences are the three questions Q1–Q3 and
the statement S4 (*Le village de Beaulieu est en grand émoi*), which serves as the
within-speaker baseline for RQ4. Each row has:

- speaker metadata from the speaker table: site, country, region, age, age group
  (Older = above the sample median), sex/gender;
- `SENTENCE_TYPE` (interrogative/declarative), the sentence type and the official
  target sentence next to the transcribed text;
- all acoustic measures from the extraction;
- `QC_FLAGS` / `QC_OK`: failed extraction, missing alignment, mis-cut extraction
  window, missing final-region measures, filename in transcript, disfluencies;
- `AUTO_DECISION` / `AUTO_REASON`: the automatic decision under the selection rule;
- `PITCH_TRACK_CHECKED`, `MANUAL_DECISION`, `MANUAL_NOTE`: manual entries merged
  from the overrides file;
- `SELECTION_DECISION`: the final decision (manual if given, otherwise automatic);
- `COMPLETE_CASE_SET`: whether the speaker has all three questions included
  (for the sensitivity analysis);
- `RQ4_SET`: whether the speaker has S4 and at least one question included
  (the speakers used for the question–statement comparison).

## Selection rule

The rule is anchored on the final word group of each sentence, where the nuclear
configuration is realized (`à Beaulieu`, `grand honneur`, `visites officielles`,
`grand émoi`).

1. Technical problems are repaired before any exclusion → **Repair, then reassess**.
2. A token is **excluded** if the final word group is missing, repeated, or contains
   a hesitation or self-repair.
3. Hesitations, repairs and small lexical substitutions earlier in the sentence do
   not lead to exclusion → **Include**.
4. Planned tokens without measurements → **Pending – no data**; speaker codes not in
   the speaker table → **Pending – metadata**.
5. Every speaker with at least one included token is retained.
6. S4 is planned for every speaker in the speaker table (`PLAN_S4 = True`). For a
   speaker whose reading has no usable S4, record `Not available` in
   `MANUAL_DECISION` so the row is no longer counted as pending.

Pitch-track usability over the nuclear region is judged by hand and recorded in the
overrides file.

## Manual overrides

`manual_overrides.csv` (created next to the output if missing; pass another file
with `--overrides`) has the columns
`TOKEN_ID, PITCH_TRACK_CHECKED, MANUAL_DECISION, MANUAL_NOTE`.
It is read on every run and never overwritten, so manual decisions survive re-extraction.

## Settings

At the top of `modules/master_sheet.py`: target sentences and final word groups,
`PLAN_S4`, `SPEAKER_ALIASES` (e.g. `{'81aac1': '81acc1'}`), `AGE_RULE`, `WINDOW_FACTOR`,
`MIN_SPEECH_RATE`, and the list of hesitation words.

## Running it on an existing output

```bash
python -m modules.master_sheet --acoustics outputs/PFC_token_level_praat_filled.csv \
    --speakers PFC_template.xlsx --out outputs/PFC_MASTER.xlsx
```

## Adding S4 to an extraction

1. Cut the statement from each reading and name the files with `tw4`, like the
   questions (`ciaak1tw4.wav`, `ciaak1tw4.TextGrid`). File matching is strict:
   an S4 row only ever uses a `tw4` file, never another sentence's file.
2. Add one row per speaker to the token sheet of the template with
   `SENTENCE_ID = S4` and `SENTENCE_TEXT` set to the transcribed statement.
3. Run the extraction on all four sentences together, so that the speaker-level
   pitch range is computed from the same set of recordings for every sentence.
