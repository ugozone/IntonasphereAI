# Final-domain visualizer (IntonaSphere AI)

Creates, for every question token:

- **`<file>_final_domain.png`**: a Praat-style figure with the waveform, spectrogram and F0 track, plus the tiers. The final syllable is shaded, and a zoom panel marks F0 onset, peak and offset with their times and values, the fitted slope and the duration.
- **`<file>_cues.TextGrid`**: opens in Praat next to the WAV. It keeps your WebMAUS tiers (or adds automatic `UTT-AUTO` / `SYL-AUTO` tiers when there is no TextGrid) and adds:
  - `FINAL-DOMAIN` (interval tier): the final syllable
  - `CUES` (point tier): each cue at its exact time, e.g. `F0 onset 231 Hz`, `F0 offset 248 Hz`, `RISE +5.3 ST/s fitted; dur 370 ms`
- **`final_domain_cues.csv` / `.xlsx`**: one row per token with every cue and its time, linked to the figure and the TextGrid.

## Install

Copy `modules/final_domain_visualizer.py` into the repository's `modules/` folder, then:

```bash
pip install praat-parselmouth numpy scipy matplotlib pandas openpyxl
```

With Parselmouth installed, pitch and intensity come from Praat itself. Without it, a built-in tracker (Praat-style autocorrelation) is used and named in each figure.

## Run

```bash
# WAVs with same-name WebMAUS TextGrids: final syllable taken from the MAS tier
python -m modules.final_domain_visualizer --folder path/to/folder --out outputs/final_domain

# WAVs only (or to ignore TextGrids): automatic segmentation
python -m modules.final_domain_visualizer --folder path/to/folder --out outputs/final_domain --force-auto

# options
--tier MAS                 # syllable tier name in your TextGrids
--slope-threshold 1.5      # ST/s boundary between rise/fall and plateau
--pitch-range 75 500       # fixed range instead of the speaker-adaptive two-pass range
--svg                      # also save SVG figures (for papers)
```

## Measures

| Column | Meaning |
| --- | --- |
| FINAL_SYLLABLE_START / END / DURATION | Final syllable (MAS tier, or automatic) |
| F0_ONSET / PEAK / VALLEY / OFFSET (_TIME, _HZ) | Onset and offset are medians of the first and last 3 voiced frames |
| F0_CHANGE_ST | Offset relative to onset, in semitones |
| FINAL_SLOPE_ST | Least-squares slope through the voiced frames (ST/s); used for CONTOUR_CLASS |
| FINAL_SLOPE_ENDPOINT_ST | (last − first frame) / syllable duration: the release-dataset definition |
| PEAK_ALIGNMENT_S / _PROP | Peak time from syllable onset, in seconds and as a share of the syllable |
| MAX_F0_JUMP_ST / QC_OCTAVE_JUMP | Largest frame-to-frame F0 jump in the final syllable; flag if ≥ 7 ST |
| PITCH_FLOOR_HZ / CEILING_HZ | Speaker-adaptive range: 0.75 × Q25 and 1.5 × Q75 of a first pass |

## How TextGrids are matched

`64aab1tw2.wav` takes `64aab1tw2.TextGrid`. If there is no exact match, a suffixed version of the same token is accepted (`64aab1tw1R.TextGrid`, `64aab1tw2m.TextGrid`, `… copy.TextGrid`), but never another question's file. Among several candidates, the one with a syllable interval tier (MAS) wins. Accepted syllable tiers, in order: MAS, syllabe, syllable, sylable, syllables, syll.

## Quality flag

`QC_OCTAVE_JUMP` = True when F0 jumps by 7 ST or more between two 10-ms frames inside the final syllable, which is usually a tracking error. Such figures are marked "⚠ check".

## Automatic segmentation (when no TextGrid is given)

Silences are found as in Praat's *To TextGrid (silences)* (−25 dB). Syllable nuclei are intensity peaks with dips of at least 2 dB that are voiced at the peak (de Jong & Wempe, 2009). Syllable boundaries fall at the intensity minima between nuclei. The final syllable is extended through continuous voicing. This is an approximation for files without alignment; WebMAUS MAS boundaries are preferred whenever they exist.

## The final syllable in the TextGrid (x_cues.TextGrid)

| Tier | Contents |
|---|---|
| FINAL-DOMAIN | The final syllable in IPA, its word, start and end times and duration, e.g. `[ljø]  final syllable of 'Beaulieu'  1.400-1.683 s  (283 ms)` |
| FINAL-PHONES | Its phones in IPA, with the vowel marked: `l` · `j` · `ø (vowel)` |
| CONTOUR | Rise / fall / plateau, the fitted slope, the change from onset to offset, the peak alignment and the share of the vowel that has F0 |
| CUES | Points for onset, peak, low and offset, each with its value, plus "F0 ends" where the pitch track stops before the end of the syllable |

**F0 on the final vowel.** At the end of a sentence the last vowel is often creaky, or its pitch drops below the floor, and then F0 cannot be measured there. The contour is then measured mostly on the consonants before the vowel.
- `FINAL_VOWEL_F0_COVERAGE` gives the share of the vowel that has F0.
- `QC_FINAL_VOWEL_LOW_F0` is True when that share is below 50%.
- Check these tokens in Praat, and say in the paper how they were treated: kept, or analysed separately.

## Contour classes

| Class | Rule |
|---|---|
| **rise-fall** | F0 peaks inside the final syllable: the peak lies in the middle 60% of the voiced part, is at least 1.5 ST above both the onset and the offset, and has at least 4 voiced frames (40 ms) on each side. It corresponds to F_ToBI (L)H* L%. |
| **fall-rise** | The same rule with a low point instead of a peak. It corresponds to F_ToBI L* H%. |
| **rise / fall / plateau** | Otherwise, from the fitted slope: at least +1.5 ST/s is a rise, at most −1.5 ST/s is a fall, anything in between is a plateau. |

A single straight line cannot describe a contour that turns, so these graphs show two fitted lines, one before and one after the turning point. `CONTOUR_SLOPE_CLASS` keeps the class that the slope rule alone would give, for comparison with the earlier three-way results. Praat's `verify_final_domain.praat` applies the same rule.
