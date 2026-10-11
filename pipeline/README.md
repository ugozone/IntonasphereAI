# IntonaSphere AI: prosodic cues and F_ToBI from French recordings

**Testing first:** see TESTING.md (`python -m modules.selftest --folder test_data`).
Checking values and drawing the graphs in Praat: see PRAAT_VERIFICATION.md.

## Check a folder before processing it

```bash
python -m modules.check_folder --folder ~/Desktop/pfc_all --speakers metadata/pfc_speaker_table_corrected.xlsx
```

This changes nothing. It reports unreadable or silent WAVs, missing or wrongly paired TextGrids, extra TextGrid versions, non-French WebMAUS alignments, speakers missing from the table, and what the pipeline will do with each file. The results are written to `folder_check_report.txt` and `folder_check.xlsx`, next to the folder.

**Fixing the folder.** Add `--fix` to see proposed fixes; nothing changes yet. Add `--fix --apply` to carry them out, and `--undo` to reverse them.
- **Renamed:** TextGrids with name typos get the name of their WAV (e.g. `maant1w4` → `maant1tw4`).
- **Moved to `pfc_all/_set_aside/`:** extra versions, TextGrids with no WAV, non-PFC files, unusable audio, and broken TextGrids (wrong length, missing tiers, non-French alignment). The pipeline then re-aligns those recordings with WebMAUS.
- **Nothing is deleted.** Every change is logged in `folder_fix_log.csv`.
- **Speaker codes that aren't in the table are left for you to decide.**

**Statement files (`xxxtw4.wav`).** These hold the opening sentence of the PFC text, *Le village de Beaulieu est en grand émoi.* They are processed as a declarative control: SENTENCE_ID = S4 (statement), TOKEN_ID = `xxxtw_S4`, QUESTION_TYPE = declarative. To leave them out, move them out of the folder.

## One command for everything

```bash
pip install -r requirements.txt
python -m modules.run_all --folder data/wavs --out outputs
```

For every WAV in the folder, the command runs these steps in one pass:

1. **Alignment.**
   - Your WebMAUS TextGrid is used as it is.
   - If there is no TextGrid, WebMAUS (French) is called with one of three texts:
     - your `.txt` file;
     - the PFC question text, worked out from the file name (`…tw1/2/3`);
     - a speech-recognition transcript.
2. **Pitch.** F0 is tracked once per file, using Praat through Parselmouth with a speaker-adaptive range. Both graphs use this same F0.
3. **Final-domain graph and cues:** `outputs/final_domain/x_final_domain.png` and `x_cues.TextGrid`.
4. **F_ToBI graph and annotation:** `outputs/ftobi/x_ftobi.png` and `x_ftobi.TextGrid`. The labels are proposals, to be checked in Praat.
5. **One workbook,** `outputs/intonasphere_results.xlsx`, with these sheets:

| Sheet | Contents |
|---|---|
| README | What each sheet holds |
| ALL_TOKENS | One row per recording: alignment source, final-domain cues, F_ToBI summary, figure paths, and `CONTOUR_VS_BOUNDARY_TONE` |
| FINAL_DOMAIN | Every final-syllable cue |
| FTOBI_TOKENS / FTOBI_SYLLABLES | The F_ToBI proposal and the evidence for each syllable |
| ALIGNMENT | Where each TextGrid came from |
| PARAMETERS | Every threshold used, so the run can be repeated exactly |

### Options

| Option | Effect |
|---|---|
| `--align none` | Use only existing TextGrids, with no WebMAUS or speech recognition. A file without a TextGrid still gets its final-domain graph, using automatic segmentation. |
| `--align pfc` | Call WebMAUS only for PFC file names and files that have a `.txt` |
| `--no-ftobi` / `--no-final-domain` | Produce only one of the two graphs |
| `--pitch-range 75 500` | Use a fixed pitch range instead of the speaker-adaptive one |
| `--realign` | Ignore every existing TextGrid and align **all** files with WebMAUS from the sound and its text (PFC text, or your `.txt`). Your TextGrids are not changed; their names are kept in the `USER_TEXTGRID` column for comparison. Needs `--align pfc` or `--align any`. If WebMAUS fails for a file, that file falls back to automatic segmentation (it does not use your TextGrid), and the ALIGNMENT sheet says why. |

## Aligning everything from the sound alone (`--realign`) and comparing

So that the whole dataset is aligned by one documented procedure, run the extraction twice, into two output folders, then compare them:

```
python3 -m modules.run_all --folder ~/Desktop/pfc_all --out ~/Desktop/pfc_results --align pfc --speakers metadata/pfc_speaker_table_corrected.xlsx
python3 -m modules.run_all --folder ~/Desktop/pfc_all --out ~/Desktop/pfc_results_realigned --align pfc --realign --speakers metadata/pfc_speaker_table_corrected.xlsx
python3 -m modules.compare_runs --a ~/Desktop/pfc_results --b ~/Desktop/pfc_results_realigned
```

`compare_runs` uses only recordings that were aligned in both runs (add `--include-unaligned` to override, `--only-user-textgrids` to keep only files that had your own TextGrid in run A). It reports the final-syllable start/end difference in ms (and the share within 20 and 50 ms), the duration difference, the median difference and correlation of slope and F0 onset/peak/offset, and the agreement and Cohen's kappa for the contour class, the three-way slope class and the F_ToBI nuclear configuration. It writes `compare_runs_report.txt` and `compare_runs.xlsx` (SUMMARY, PER_FILE, CONTOUR_CROSSTAB) into the second folder. The files whose contour class differs are listed: open both graphs for those.

### `CONTOUR_VS_BOUNDARY_TONE`

The two analyses describe the end of the question in different ways.

- The final-domain **contour class** is based on the **slope**, the rate of change in ST/s.
- The F_ToBI **boundary tone** is based on the **size** of the movement: H% for a rise of at least +1.5 ST, L% for a fall of at least −1.5 ST.

A small, slow rise can therefore count as "rise" in one and as level, marked "?", in the other. This column reports `agree`, `agree (F_ToBI label uncertain)`, or `… : check`. Look at the `check` rows in Praat.

## Pitch range (how F0 is tracked)

The range is set by two passes, after De Looze & Hirst (2008):

1. **First pass,** with a broad range chosen by sex from the speaker table: men 60–300 Hz, women 100–500 Hz, and 60–600 Hz when sex is unknown.
2. **Second pass,** with floor = 0.75 × the 25th percentile and ceiling = 1.5 × the 75th percentile of the first-pass F0.
   - First-pass frames more than 8 semitones from the speaker's median are left out of this calculation. These are octave errors: F0 wrongly halved or doubled.
   - The floor is never below 50 Hz.

**Pooling.** By default the first-pass values are pooled per **speaker**, so all of a speaker's recordings (tw1–tw4) get the same range. `--pitch-method file` sets the range for each recording on its own, which was the previous behaviour. `--no-sex-first-pass` uses 60–600 Hz for everyone. The method is recorded in PARAMETERS, and each file's range in ALL_TOKENS.

**Sex check.** A speaker whose median F0 is unusual for the sex given in the table (men above 165 Hz, women below 150 Hz) gets the broad 60–600 Hz first pass instead, and is listed in DATASET_WARNINGS so you can verify SEX. If the table is right, no action is needed. Example: 64aji1 is a man with a high voice (median about 170–180 Hz).

**Separate commands.** The final-domain and F_ToBI commands run on their own still use the per-file range.

## The dataset sheet (28 released headings)

```bash
python -m modules.run_all --folder data/wavs --out outputs --speakers metadata/pfc_speaker_table_corrected.xlsx
```

- **DATASET sheet** (also saved as `outputs/intonasphere_dataset.csv`): one row per recording. It has exactly the 28 headings of the released dataset, in the same order (TOKEN_ID … EXTRACTION_END), and every value is computed by code.
- **CODEBOOK sheet:** the definition, unit and source of each column. Cite it in the paper.
- **SPEAKERS sheet:** the speaker table as it was used.
- **DATASET_WARNINGS sheet:** recordings whose speaker is not in the table. Each warning suggests the closest code.
- **AGE_GROUP** is recomputed from AGE by the median split (median of all speakers in the table). An age equal to the median goes to the Older group; change this with `--age-tie Younger`. The median and the rule are recorded in PARAMETERS.
- **Codes:** `--speaker-fix TABLE_CODE=CORRECT_CODE` corrects a code in the table (e.g. `--speaker-fix 81acc1=81aac1`). `metadata/pfc_speaker_table_corrected.xlsx` already includes this correction.
- **No speaker table:** the demographic columns stay empty and everything else is still computed.

## The separate commands still work

| Command | Does |
|---|---|
| `python -m modules.final_domain_visualizer --folder X --out Y` | Final-domain graphs only (see `README_final_domain_visualizer.md`) |
| `python -m modules.ftobi_annotator --folder X --out Y [--align none]` | F_ToBI only (see `README_ftobi.md`) |
| `python -m modules.auto_align --folder X --out X` | WebMAUS TextGrids only, saved next to the WAVs |
| `python -m modules.validate_ftobi --auto Y --checked Y` | Agreement between the F_ToBI proposals and the corrections made in Praat |

## Windows

The pipeline runs on Windows 10/11 as well as macOS and Linux. It is tested on all three automatically (see the *Actions* tab on GitHub). The only differences are in how you type the commands:

| | macOS / Linux | Windows (PowerShell or Command Prompt) |
|---|---|---|
| Python command | `python3` | `python` (or `py`) |
| Install | `python3 -m pip install -r requirements.txt` | `python -m pip install -r requirements.txt` |
| Paths | `~/Desktop/pfc_all` | `~/Desktop/pfc_all` also works, or `C:\Users\yourname\Desktop\pfc_all` |
| Paths with spaces | `"~/My data/pfc_all"` | `"C:\Users\yourname\My data\pfc_all"` (always use quotes) |
| Several lines | end a line with `\` | PowerShell: end with `` ` `` (backtick); Command Prompt: put everything on one line |

Example (PowerShell, one line):

```
cd C:\Users\yourname\IntonasphereAI\pipeline
python -m modules.run_all --folder "~/Desktop/pfc_all" --out "~/Desktop/pfc_results" --align pfc --speakers metadata/pfc_speaker_table_corrected.xlsx
```

Notes:
- **Installing Python:** install it from python.org or Anaconda. With the python.org installer, tick **"Add python.exe to PATH"**.
- **Files open in Excel:** close `intonasphere_results.xlsx` (and the CSVs) before running again. Windows locks open files, and the pipeline stops at the start and names them, so a long run is never lost at the end.
- **CSV files:** they are saved as UTF-8 with a byte-order mark, so Excel on Windows shows accents and IPA symbols correctly.
- **Praat scripts:** they work the same in Praat for Windows. In the script forms you can paste folder paths with either `\` or `/`.

## Checking the results in Praat

- **F_ToBI:** run `praat/check_ftobi.praat` on `outputs/ftobi`, correct each file and save it as `*_checked.TextGrid`. Then run `validate_ftobi`.
- **Final-domain cues:** open `x.wav` together with `outputs/final_domain/x_cues.TextGrid`. The CUES tier marks every measured point with its time and value.
