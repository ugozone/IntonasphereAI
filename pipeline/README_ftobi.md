# IntonaSphere AI: F_ToBI assistant

`modules/ftobi_annotator.py` takes each question's WAV file and its WebMAUS TextGrid. It **proposes** a full F_ToBI annotation as Praat tiers: tones, break indices, AP / ip / IP, syllables and phones in IPA. A trained annotator then checks the proposal in Praat.

`modules/validate_ftobi.py` measures how much the annotator had to correct, and that is the validation figure for the paper. The tool never replaces the annotator. It produces a first pass that can be checked, so that annotating 129 tokens becomes feasible and reproducible.

## Run it

```bash
pip install numpy scipy pandas matplotlib openpyxl praat-parselmouth requests
pip install faster-whisper     # only for recordings that are not PFC and have no .txt
python -m modules.ftobi_annotator --folder data/wav_and_textgrids --out outputs/ftobi
```

The folder holds WAV files and, if you have them, their WebMAUS TextGrids or text files (see below). Every threshold can be changed from the command line, for example `--dur-ratio 1.5`. The values used are saved in the PARAMETERS sheet of `ftobi_annotations.xlsx`.

### What the folder can contain: three ways in

| You provide | What the tool does | Recorded in `ftobi_tokens.csv` |
|---|---|---|
| `x.wav` + `x.TextGrid` | Uses your WebMAUS TextGrid exactly as it is. This is the original workflow, and it is never overwritten. | `ALIGNMENT_SOURCE = user_textgrid` |
| `x.wav` + `x.txt` | Sends your sentence and the audio to WebMAUS (French), then saves the TextGrid | `TEXT_SOURCE = user_txt` |
| `x.wav` only, PFC file name (`…tw1/2/3`) | Takes the question text from the file name (Q1/Q2/Q3) and sends it to WebMAUS | `TEXT_SOURCE = pfc_texte_lu` |
| `x.wav` only, any other recording | Transcribes it with faster-whisper (French) and writes `x.asr.txt`, then sends it to WebMAUS | `TEXT_SOURCE = asr`. **Check this transcript.** |

The `--align` option chooses how far the tool goes:

- `--align none` restores the original behaviour: a WAV without a TextGrid is skipped.
- `--align pfc` aligns automatically only for PFC file names and for files that have a `.txt`.
- `--align any` is the default.

New TextGrids go to `<out>/aligned/`, together with `alignment_log.csv`, and are reused on later runs.

**About the transcript.** To correct a transcript, edit `x.asr.txt`, save it as `x.txt`, delete `<out>/aligned/x.TextGrid` and run again. Your text then takes priority.

**About WebMAUS.** The tool always asks for French (`fra-FR`). It calls the BAS pipeline `G2P_MAUS_PHO2SYL`, which gives the same tiers as your files, including the MAS syllable tier.

- If that call fails, the tool uses `runMAUSBasic` and builds the MAS tier itself: phones are grouped into syllables inside each word, following French onset rules. On your 9 original WebMAUS files this rebuilt tier matched WebMAUS's own on 110 out of 110 syllables.
- The service needs an internet connection and is free for academic, non-profit research.
- The audio is uploaded to the BAS server in Munich, which keeps it for 24 hours. Check that this is compatible with the PFC data-use conditions.

To produce only the TextGrids, without F_ToBI, for example to use them with the final-domain visualizer:

```bash
python -m modules.auto_align --folder data/wavs --out data/wavs      # TextGrids saved next to the WAVs
```

| Output | Contents |
|---|---|
| `<stem>_ftobi.TextGrid` | The proposal (tiers below) |
| `<stem>_ftobi.png` | F0 contour with tones, breaks and phrases drawn on it |
| `ftobi_tokens.csv` | One row per utterance: nuclear configuration, phrasing, tones, number of uncertain labels, QC warnings |
| `ftobi_syllables.csv` | One row per syllable: every cue and every decision |
| `ftobi_annotations.xlsx` | Both tables plus the parameters |
| `ftobi_praat_ranges.csv` | The pitch range used for each file (read by the Praat script) |

## Tiers in the TextGrid

| Tier | Type | Contents |
|---|---|---|
| tones | point | F_ToBI tones: aL, Hi, L, H\*, L\*, H+!H\*, H-, L-, H%, L%, !H% |
| words | interval | Orthographic words (ORT-MAU) |
| breaks | point | Break index after every word: 0–4, with `p` for a hesitation pause |
| AP / ip / IP | interval | Accentual, intermediate and intonational phrases |
| syllables | interval | Syllables in IPA (MAS, converted from SAMPA) |
| phones | interval | Phones in IPA (MAU) |
| evidence | point | Measured cues on each syllable that could end an AP, e.g. `D1.92 H+3.3 R1.4 P0ms [DH]` |
| nuc-edge | point | Test of Beyssade et al. (2007), described below |
| misc | interval | QC warnings: vowel-less syllables, non-French SAMPA, transcription ≠ expected form |

**A label ending in `?` is a low-confidence proposal**, because its cue lies within 15 % of the threshold. This follows the ToBI convention for uncertain labels, and these are the labels to check first.

## The rules and where they come from

| Step | Rule | Source |
|---|---|---|
| Accentable words | The final accent falls on the last full (non-schwa) syllable of a content word. Clitics and other function words never carry it. A prenominal adjective directly followed by its noun (*Premier ministre*, *grand honneur*) does not close an AP. | Delais-Roussarie et al. 2015, §3.1.2.1 |
| AP boundary (2) | A candidate becomes an AP when its final syllable is prominent. Prominence means one of: rhyme duration ≥ 1.61 × the mean of the 3 preceding and 3 following syllables, F0 ≥ 1.43 ST above them, a rise ≥ 2.07 ST on the rhyme, or a following pause ≥ 100 ms. | Avanzi et al. 2011, read-speech thresholds |
| ip boundary (3) | An AP boundary with stronger lengthening (≥ 2.0) or with a pause. A pause on its own gets `3?`, because it may be a reading hesitation. | Delais-Roussarie et al. 2015, §3.1.2.1; Michelas & D'Imperio 2012 |
| IP boundary (4) | The end of the utterance, or a pause ≥ 300 ms after a lengthened syllable (marked `4?`) | Delais-Roussarie et al. 2015, §3.1.2.1 |
| Breaks 0 / 1 | 0 after a clitic, 1 between words inside an AP | Delais-Roussarie et al. 2015, §3.1.3 |
| AP tones | The AP follows the pattern (aL)(Hi)(L)H\*. The final accent is H\* when the syllable rises or is a local peak, and L\* otherwise, which is not contrastive before the nucleus. Hi is an early peak on one of the first syllables, or on a wh-word or *est-ce que*, that is ≥ 1.5 ST above the AP-initial low and ≥ 1 ST above what follows. aL is the AP-initial low before the first H. An ip edge is H- when high or rising and L- when low or falling. | Delais-Roussarie et al. 2015, ex. (3), §3.1.2.2, §3.3.4.1 |
| Nuclear configuration | Accent and boundary tone fall on the same final syllable, an effect of tonal crowding. T\* is read at the start of the final vowel, relative to the penultimate syllable and the speaker's range. T% is read from the movement across the rhyme: ≥ +1.5 ST gives H%, ≤ −1.5 ST gives L%, and a level movement takes the level of T\*. A low penultimate before H\* gives the leading L of (L)H\*. A lengthened high penultimate followed by a lower final gives H+!H\* !H%. | Delais-Roussarie et al. 2015, Table 3.6 |
| Left-edge phrasal tone | Interrogatives anchor H- (with a falling L\* nucleus) or L- (with a rising H\* nucleus) at the left edge of the nuclear domain. That edge is the wh-expression or the inverted verb, as in H- on [til] of *ira-t-il*. | Beyssade, Delais-Roussarie & Marandin 2007, ex. (12)–(21) |

Before any label is computed, frames where F0 jumps by more than 4 ST in 10 ms are removed. Real F0 cannot move that fast, so these are octave errors or fricative noise, and the number removed is reported per token. All F0 values are in semitones relative to the speaker's median in that utterance.

## Phonetic transcription

WebMAUS writes SAMPA, which is converted to IPA. Each word is then checked against its expected canonical form in the PFC questions (`PFC_LEXICON`). Regular variation is tolerated: o/ɔ, e/ɛ, ø/œ, schwa present or absent, and the i~ij glide. On the samples the check found three problems:

- **`Qu'est-ce` → /kts/** in every file. The WebMAUS grapheme-to-phoneme step mis-transcribes this word, so its syllable has no vowel and its F0 is read from the whole syllable. Fix the KAN form, or the word spelling sent to WebMAUS, before the full run.
- **64aab1tw1 contains German SAMPA** (`I`, `aU`, `?`, `e:`). That file was almost certainly aligned with the German model, so re-run it with **fra-FR**.
- Hand-edited labels such as `n\oeR` (an unspaced Praat symbol) and `mɑ̃nifɛstasjɔ̃`.

## Check in Praat, then measure agreement

1. In Praat, choose Open Praat script, open `praat/check_ftobi.praat` and run it. Give it the outputs folder, the audio folder and your initials.
2. Each file opens in the editor. Set **Pitch > Pitch settings** to the range shown in the window. Then correct `tones`, `breaks` and `AP / ip / IP`, and delete the `?` from every label you accept. Click **Save & next**. The corrected file is saved as `<stem>_checked.TextGrid`; the proposal is never overwritten, and the script resumes where you stopped.
3. Measure agreement:

```bash
python -m modules.validate_ftobi --auto outputs/ftobi --checked outputs/ftobi --out outputs/ftobi_validation
```

The script reports the following, written to `ftobi_validation.xlsx`:

- break-index agreement, Cohen's κ and linear-weighted κ, with a confusion matrix;
- precision, recall and F1 for AP, ip and IP boundaries;
- tone detection and label κ, by category;
- agreement on the nuclear configuration;
- agreement for confident versus `?` labels.

If the `?` flag works, most corrections fall on `?` labels.

To compare boundary times with an older hand annotation that has AP and IP point tiers:

```bash
python -m modules.validate_ftobi --boundaries-only outputs/ftobi/64aab1tw2_ftobi.TextGrid 64aab1tw2m.TextGrid --tol 0.10
```

### Protocol for the paper

Use the same 36-token stratified sample (seed 2027) as the acoustic validation. Two annotators trained on F_ToBI each correct the proposals independently, without seeing each other's work.

Report:

- tool vs annotator A, and tool vs annotator B: how much was corrected;
- annotator A vs annotator B on their corrected files: the human ceiling.

For comparison, human ToBI inter-annotator agreement is typically about κ 0.6–0.8 for break indices and accents. Avanzi et al. (2011) report κ = 0.67 between experts for French prominence, and κ = 0.70 (linear-weighted) for their automatic tool against the experts.

The tool is acceptable when its agreement with the annotators approaches the agreement between them. Agreement that is not obtained from human corrections must not be reported.

## Limits

- The rules work on read speech aligned by WebMAUS. Errors in the alignment, such as vowel-less syllables, carry through. Those cases are flagged in `misc`.
- Without Parselmouth, a built-in tracker modelled on Praat is used. Install `praat-parselmouth` so that the F0 is Praat's own.
- Bitonal accents (H+!H\*, H+H\*) and !H% are rare and proposed only with `?`.
- The thresholds come from the literature and have not been tuned on these data. Tune them only on annotator-corrected files, and only on files outside the validation sample.

## References

- Avanzi, M., Lacheret-Dujour, A., Obin, N. & Victorri, B. (2011). Toward a continuous modeling of French prosodic structure: Using acoustic features to predict prominence location and prominence degree. *Proceedings of Interspeech 2011*, Florence.
- Beyssade, C., Delais-Roussarie, E. & Marandin, J.-M. (2007). The prosody of interrogatives in French. *Nouveaux Cahiers de Linguistique Française* 28, 163–175.
- Delais-Roussarie, E., Post, B., Avanzi, M., Buthke, C., Di Cristo, A., Feldhausen, I., Jun, S.-A., Martin, P., Meisenburg, T., Rialland, A., Sichel-Bazin, R. & Yoo, H.-Y. (2015). Intonational phonology of French: Developing a ToBI system for French. In S. Frota & P. Prieto (eds.), *Intonation in Romance*, 63–100. Oxford University Press.
- Jun, S.-A. & Fougeron, C. (2002). Realizations of accentual phrase in French intonation. *Probus* 14, 147–172.
- Michelas, A. & D'Imperio, M. (2012). When syntax meets prosody: Tonal and duration variability in French accentual phrases. *Journal of Phonetics* 40, 816–829.
- Rosenberg, A. (2010). AuToBI: A tool for automatic ToBI annotation. *Proceedings of Interspeech 2010*, Makuhari.
- Kisler, T., Reichel, U. & Schiel, F. (2017). Multilingual processing of speech via web services. *Computer Speech & Language* 45, 326–347.
- Schiel, F. (1999). Automatic phonetic transcription of non-prompted speech. *Proceedings of ICPhS 1999*, 607–610. (WebMAUS)
