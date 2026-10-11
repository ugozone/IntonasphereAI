# Checking the acoustic values and drawing the graphs in Praat

All scripts are in the `praat/` folder. Run each one from Praat with **Praat → Open Praat script… → Run → Run**.
When the form asks for a folder, give its full path: drag the folder from Finder into Terminal and copy the text that appears.
If Praat asks for permission to save a file, allow it.

| Script | What it does | Output |
|---|---|---|
| `verify_final_domain.praat` | Re-measures every final-syllable value in Praat, using the same syllable, pitch range and definitions as the tool, and compares each value with the tool's | `praat_verification.csv` + a summary in the Info window |
| `draw_final_domain.praat` | Draws the final-domain graph in Praat (waveform, spectrogram + F0, tiers, zoom on the final syllable, the values) | `x_final_domain_praat.png` |
| `draw_ftobi.praat` | Draws the F_ToBI graph in Praat (F0 + tones, words, breaks, AP, ip, IP, syllables) | `x_ftobi_praat.png` (or `x_checked_praat.png`) |
| `check_ftobi.praat` | Lets you correct the F_ToBI proposals one file at a time | `x_checked.TextGrid` |

Fill the forms like this:
- Audio folder: the folder with the WAVs, e.g. `test_data`.
- Results folder: `outputs_selftest/run/final_domain` for the first two scripts, and `outputs_selftest/run/ftobi` for the F_ToBI scripts.

The include file `intonasphere_measure.include` must stay in the same folder as the scripts.

## Checking one value by hand in the Praat editor (no script)
1. Open `x.wav` and `final_domain/x_cues.TextGrid` together, then click **View & Edit**.
2. Choose **Pitch → Pitch settings…** and enter the range from `PITCH_FLOOR_HZ` and `PITCH_CEILING_HZ` in the workbook.
3. Click the **FINAL-DOMAIN** interval. Its start, end and duration appear above the waveform: compare them with `FINAL_SYLLABLE_START`, `FINAL_SYLLABLE_END` and `FINAL_SYLLABLE_DURATION`.
4. With the interval selected:
   - **Pitch → Get maximum pitch** (F10) should give `F0_PEAK_HZ`.
   - **Intensity → Get intensity** (F11) should give `FINAL_INTENSITY_MEAN_DB`.
5. Click each point on the **CUES** tier (onset, peak, offset), then **Pitch → Get pitch** (F5). The value should match the number written on the point. Onset and offset are medians of three frames, so a single click can differ by 1–2 Hz.
6. Look at the F0 track over the syllable. Is the rise, fall or plateau the one the tool reports? Are there octave jumps?

**Small differences:** they are expected when you check by hand, because a click lands between frames. With the script, the differences should be close to 0. A large difference means the pitch track differs, for example because of an octave jump or a different pitch range. Look at that file.
