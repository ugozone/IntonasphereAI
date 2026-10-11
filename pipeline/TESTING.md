# Testing IntonaSphere AI on your computer

## 1. Install (once)
```bash
cd IntonasphereAI/pipeline
pip install -r requirements.txt
pip install faster-whisper        # only to test recordings that have no TextGrid and no .txt
```

## 2. Automatic self-test (about 5 minutes)
The repository ships no recordings (corpus audio stays private). When `test_data/` has no WAV files, the self-test first creates two short **synthetic** recordings with `test_data/make_test_data.py` (a buzz shaped like the vowel /a/, saying "la banane"; no real speaker):

| File | Route tested | Expected result |
|---|---|---|
| `synth_question.wav` + `synth_question.TextGrid` | WAV + TextGrid (original workflow), F_ToBI | rise, H* H% |
| `synth_statement.wav` + `synth_statement.txt` | Any name + text file: WebMAUS with your text | fall |

To test with real speech, make a small folder of your own recordings and pass it with `--folder`, for example:

| File | Route tested |
|---|---|
| `xxx1tw2.wav` + `xxx1tw2.TextGrid` | WAV + your TextGrid |
| `xxx1tw1.wav` | PFC name, no TextGrid: WebMAUS with the PFC question text |
| `my_sentence.wav` + `my_sentence.txt` | Any name + text file: WebMAUS with your text |
| `other.wav` | Nothing else: speech recognition (needs faster-whisper), then WebMAUS |

```bash
python -m modules.selftest --folder test_data
```
**Send me `outputs_selftest/selftest_report.txt`.** Every line is marked PASS, WARN, FAIL, SKIP or INFO.

## 3. Check the results by eye (about 15 minutes)

1. **Graphs.** Open `outputs_selftest/run/final_domain/*.png` and `outputs_selftest/run/ftobi/*.png`.
   - Does the F0 follow what you hear?
   - Is the final syllable the right one?
2. **WebMAUS TextGrids.** In Praat, open `synth_statement.wav` (or one of your own recordings without a TextGrid) together with its file in `outputs_selftest/run/aligned/`.
   - Are the word and syllable boundaries in the right places? (For the synthetic file they are approximate, since it is not real speech.)
   - Are the phones French?
3. **F_ToBI checking.** Run `praat/check_ftobi.praat`.
   - Proposals folder: `outputs_selftest/run/ftobi`
   - Audio folder: `test_data`

   Correct one file and click "Save & next". Then confirm that `*_checked.TextGrid` appears and that you can stop the script and resume it.
4. **Validation.** Run:
   ```bash
   python -m modules.validate_ftobi --auto outputs_selftest/run/ftobi --checked outputs_selftest/run/ftobi --out outputs_selftest/validation
   ```
   Then open `outputs_selftest/validation/ftobi_validation.xlsx`.
5. **Workbook.** Open `outputs_selftest/run/intonasphere_results.xlsx`.
   - Is there one row per WAV?
   - Is the `ALIGNMENT_SOURCE` correct for each file?

## 4. Then a real batch
Run your full folder once normally and once with `--realign`, then compare the two runs with `python -m modules.compare_runs` (see README.md).

## What a failure usually means
| Report line | Likely cause and what to do |
|---|---|
| `FAIL package …` | Run `pip install -r requirements.txt` |
| `WARN pitch engine built-in` | Run `pip install praat-parselmouth`. The results are valid, but Praat's own pitch tracking is preferred for the paper. |
| `FAIL WebMAUS …` | No internet connection, a firewall, or the BAS server is down. Files that have a TextGrid still work. Send me the error text. |
| `WARN WebMAUS used the French model` | German symbols appeared in the output. Send me the report. |
| `FAIL output TextGrids` / `workbook` | A bug. Send me the report. |
