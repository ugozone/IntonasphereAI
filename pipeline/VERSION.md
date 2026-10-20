# IntonaSphere AI pipeline - version of 10 October 2026

One package with everything; it replaces all earlier zips.

| Command | What it does |
|---|---|
| `python3 -m modules.check_folder --folder F --speakers metadata/pfc_speaker_table_corrected.xlsx [--fix [--apply]] [--undo]` | Checks a data folder before processing. `--fix` proposes safe repairs, `--fix --apply` carries them out (renames, moves files to `_set_aside`, nothing deleted), `--undo` reverses them. |
| `python3 -m modules.run_all --folder F --out O --align pfc --speakers metadata/pfc_speaker_table_corrected.xlsx` | The full extraction: alignment, pitch, final-domain graph, F_ToBI graph and the 28-column DATASET with its CODEBOOK. |
| `python3 -m modules.run_all ... --realign` | Aligns every file again with WebMAUS from the sound and its text, ignoring existing TextGrids, so the whole set is aligned by one procedure. |
| `python3 -m modules.compare_runs --a O1 --b O2` | Compares two runs (e.g. your TextGrids vs. `--realign`): boundary differences in ms, cue differences, contour and nuclear agreement with kappa. |
| `python3 -m modules.selftest --folder test_data` | Tests the installation on your computer. |
| `python3 -m modules.validate_ftobi --auto O/ftobi --checked O/ftobi` | Measures agreement between the F_ToBI proposals and an annotator's corrections. |
| `python3 -m modules.segment_media --media film.mp4 --srt film.srt --out F` | Cuts a long recording (audio or video) into one WAV + .txt per phrase, ready for `run_all`. Times from a CSV, subtitles, a TextGrid, an IntonaSphere transcript, or speech recognition. |
| `python3 -m modules.run_all ... --measure both` | Also measures the whole phrase (PHRASE_* columns: onset, offset, max, min, mean, range, change, slope), not only the final syllable. |
| `python3 -m modules.coding_table --results R1 R2 --design d.csv --corrections c.csv --out t.xlsx` | Builds one coding table from one or more runs: study design + measures + semitone formulas, values to check in Praat in orange, hand corrections in blue and logged. `--design-by question` for PFC. |
| Praat: `praat/verify_final_domain.praat`, `draw_final_domain.praat`, `draw_ftobi.praat`, `check_ftobi.praat` | Re-measure the values in Praat, draw both graphs in Praat, and correct the F_ToBI proposals. |

## Added on 20 October 2026

- **segment_media:** cuts films, interviews and long readings into phrase clips; padding never reaches into a neighbouring phrase, and speech-recognition loops over music are flagged.
- **Whole-phrase measures:** `run_all --measure both` (default `--measure final` keeps the old output unchanged).
- **coding_table:** corpus coding table with automatic QC flags (octave doubling at onset, halving or creak, values at the pitch floor or ceiling, low final-vowel F0, short final syllable, contour vs F_ToBI boundary disagreement, speech-recognition text) and a corrections file that doubles as the QC log.

## Included in this version

- **Alignment:** WebMAUS alignment in French for WAVs without a TextGrid (PFC text, your `.txt`, or speech recognition). Existing TextGrids are always used unchanged.
- **Pitch range:** two passes, with the first pass chosen by sex (men 60–300 Hz, women 100–500 Hz). The range is pooled per speaker, and octave errors are left out of the calculation. A voice that is unusual for its listed sex gets the broad 60–600 Hz first pass and is flagged.
- **Dataset:** the DATASET sheet has exactly the 28 released headings, every value computed by code, and the CODEBOOK defines each column.
- **Speaker table:** read from `metadata/pfc_speaker_table_corrected.xlsx`.
  - AGE_GROUP is recomputed by the median rule (median 44; age 44 counts as Older).
  - 81acc1 is corrected to 81aac1.
  - 64aji1 is confirmed male (PFC record).
- **Statement files (tw4):** the declarative control *Le village de Beaulieu est en grand émoi.*, labelled S4 (`xxxtw_S4`).
- **Speaker table:** 53 speakers; rcarn1, scajd1 and maabd1 added from their PFC records.
- **Folder checker:** quiet recordings are reported as low-level and usable, not as silent.
- **F_ToBI assistant:** proposes tones, breaks, AP/ip/IP and IPA tiers. A "?" marks low confidence. It also tests the left-edge phrasal tone of Beyssade et al. (2007).
- **Final syllable in the TextGrid:** FINAL-DOMAIN (IPA, word, times), FINAL-PHONES, CONTOUR and CUES tiers; the share of the final vowel with F0 is measured and flagged when below 50%.
- **Contour classes:** rise-fall and fall-rise added; the earlier three-way class is kept in CONTOUR_SLOPE_CLASS. The graphs draw two fitted lines for a turning contour, and the Praat check applies the same rule.
- **Praat scripts:** tested in Praat 7.0.
- **Test data:** synthetic recordings generated on demand, so no PFC audio is redistributed.
- **Re-alignment:** `--realign` aligns all files from the sound alone (plus its text) and records your original TextGrid in `USER_TEXTGRID`; `compare_runs` measures how much the results change.

`sample_outputs/` shows a run of this version on the synthetic recordings made by `test_data/make_test_data.py` (no corpus audio is included in the repository). It was made in the build environment with the built-in pitch tracker, so on your computer the values will differ slightly because Parselmouth uses Praat's own tracking.
