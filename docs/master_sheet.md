# PFC Q1–Q3 master sheet and token-selection rule

After every token-level extraction (`token_level_praat_extractor.py` or the
Research batch tab in the app), IntonaSphere AI writes `<output>_MASTER.xlsx`
and `<output>_MASTER_token_flow.csv` next to the extraction output, provided the
template workbook contains a `combined speaker table` sheet. The logic lives in
`modules/master_sheet.py`; disable it with `--no_master`.

## What the master sheet contains

One row per planned token (speaker × question), including speakers and questions
that have not been measured yet, with:

- speaker metadata from the speaker table: site, country, region, age, age group
  (Older = above the sample median), sex/gender;
- question type and the official target sentence next to the transcribed text;
- all acoustic measures from the extraction;
- `QC_FLAGS` / `QC_OK`: failed extraction, missing alignment, mis-cut extraction
  window, missing final-region measures, filename in transcript, disfluencies;
- `AUTO_DECISION` / `AUTO_REASON`: the automatic decision under the selection rule;
- `PITCH_TRACK_CHECKED`, `MANUAL_DECISION`, `MANUAL_NOTE`: manual entries merged
  from the overrides file;
- `SELECTION_DECISION`: the final decision (manual if given, otherwise automatic);
- `COMPLETE_CASE_SET`: whether the speaker has all three tokens included
  (for the sensitivity analysis).

## Selection rule

The rule is anchored on the final word group of each question, where the nuclear
configuration is realized (`à Beaulieu`, `grand honneur`, `visites officielles`).

1. Technical problems are repaired before any exclusion → **Repair, then reassess**.
2. A token is **excluded** if the final word group is missing, repeated, or contains
   a hesitation or self-repair.
3. Hesitations, repairs and small lexical substitutions earlier in the sentence do
   not lead to exclusion → **Include**.
4. Planned tokens without measurements → **Pending – no data**; speaker codes not in
   the speaker table → **Pending – metadata**.
5. Every speaker with at least one included token is retained.

Pitch-track usability over the nuclear region is judged by hand and recorded in the
overrides file.

## Manual overrides

`manual_overrides.csv` (created next to the output if missing; pass another file
with `--overrides`) has the columns
`TOKEN_ID, PITCH_TRACK_CHECKED, MANUAL_DECISION, MANUAL_NOTE`.
It is read on every run and never overwritten, so manual decisions survive re-extraction.

## Settings

At the top of `modules/master_sheet.py`: target sentences and final word groups,
`SPEAKER_ALIASES` (e.g. `{'81aac1': '81acc1'}`), `AGE_RULE`, `WINDOW_FACTOR`,
`MIN_SPEECH_RATE`, and the list of hesitation words.

## Running it on an existing output

```bash
python -m modules.master_sheet --acoustics outputs/PFC_token_level_praat_filled.csv \
    --speakers PFC_template.xlsx --out outputs/PFC_Q1_Q2_Q3_MASTER.xlsx
```
