# IntonaSphere AI Transcriber + Praat Analyzer

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.23290623.svg)](https://doi.org/10.5281/zenodo.23290623) [![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Website: https://intonasphereai.org/

This app transcribes audio/video files and performs phonetic/acoustic analysis using Praat through Parselmouth.

## Features

- Upload audio files
- Upload video files
- Record voice directly
- Paste public media URLs
- Convert media to WAV with FFmpeg
- Transcribe with Faster-Whisper
- Generate timestamped transcripts
- Run Praat acoustic analysis
- Extract F0/pitch, duration, intensity, formants
- Estimate final pitch movement
- Export TXT, DOCX, PDF, SRT
- Export acoustic results as CSV and Excel
- Calculate Word Error Rate and transcription accuracy

## Setup

Open Terminal in the `IntonasphereAI` folder (on a Mac, e.g. `/Users/yourname/IntonasphereAI`, which is the same as `~/IntonasphereAI`), or `cd` to wherever you cloned the repository:

```bash
cd ~/IntonasphereAI          # or: cd /path/to/IntonasphereAI
conda activate jamispeak-transcriber
python -m pip install -r requirements.txt
```

**Windows:** the same commands work in the Anaconda Prompt, from your `C:\Users\yourname\IntonasphereAI` folder. The Streamlit app also needs FFmpeg (`conda install -c conda-forge ffmpeg`). The analysis pipeline (below) uses `python` instead of `python3`; see [Windows in pipeline/README.md](pipeline/README.md#windows).

## Run

```bash
conda activate jamispeak-transcriber
python -m streamlit run app.py
```

## Analysis pipeline (batch extraction, F_ToBI, dataset)

The [`pipeline/`](pipeline/) folder holds the command-line research pipeline used for the LSA 2027 study: WAV → alignment (your TextGrids, or WebMAUS from the sound and its text) → final-syllable acoustic cues and contour class → F_ToBI proposal TextGrids → the 28-column dataset with its codebook, plus Praat scripts that re-measure the values and draw both graphs.

```bash
cd ~/IntonasphereAI/pipeline   # or: cd /path/to/IntonasphereAI/pipeline
python3 -m pip install -r requirements.txt
python3 -m modules.selftest --folder test_data
python3 -m modules.run_all --folder ~/Desktop/pfc_all --out ~/Desktop/pfc_results --align pfc --speakers metadata/pfc_speaker_table_corrected.xlsx
```

No recordings or corpus metadata are included: the self-test makes its own synthetic recordings, and the speaker table stays on your computer (see [`pipeline/metadata/README.md`](pipeline/metadata/README.md)).

See [`pipeline/README.md`](pipeline/README.md) for every option (`--realign`, `compare_runs`, `check_folder`), [`pipeline/PRAAT_VERIFICATION.md`](pipeline/PRAAT_VERIFICATION.md) for checking the values in Praat, and [`pipeline/VERSION.md`](pipeline/VERSION.md) for what this version includes.

## How to cite

**Author:** Jamike Ugochukwu Okoroji, Department of Modern Languages and Classics, Barefield College of Arts and Sciences, The University of Alabama, Tuscaloosa, Alabama, USA.

If you use IntonaSphere AI in your research, please cite the software. GitHub's **"Cite this repository"** button (right-hand sidebar) gives APA and BibTeX generated from [`CITATION.cff`](CITATION.cff); BibTeX for the tool and its core dependencies is also in [`CITATION.bib`](CITATION.bib).

> Okoroji, J. U. (2026). *IntonaSphere AI: A transcription and Praat-based prosody analysis toolkit* (Version 0.2.0) [Computer software]. Zenodo. https://doi.org/10.5281/zenodo.23290623

```bibtex
@software{Okoroji_IntonaSphere_AI_2026,
  author  = {Okoroji, Jamike Ugochukwu},
  title   = {{IntonaSphere AI: A Transcription and Praat-Based Prosody Analysis Toolkit}},
  year    = {2026},
  version = {0.2.0},
  doi     = {10.5281/zenodo.23290623},
  url     = {https://github.com/ugozone/IntonasphereAI},
  note    = {Department of Modern Languages and Classics, The University of Alabama, Tuscaloosa, Alabama, USA. Project website: https://intonasphereai.org/}
}
```

IntonaSphere AI's acoustic measures are computed with Praat through Parselmouth, so please also cite:

- Boersma, P., & Weenink, D. *Praat: doing phonetics by computer* [Computer program]. https://www.praat.org
- Jadoul, Y., Thompson, B., & de Boer, B. (2018). Introducing Parselmouth: A Python interface to Praat. *Journal of Phonetics, 71*, 1–15. https://doi.org/10.1016/j.wocn.2018.07.001

If you use the transcription module, cite Whisper (Radford et al., 2023); the entry is in `CITATION.bib`.

If you use the pipeline's automatic alignment, please also cite WebMAUS: Kisler, T., Reichel, U., & Schiel, F. (2017). Multilingual processing of speech via web services. *Computer Speech & Language, 45*, 326–347. https://doi.org/10.1016/j.csl.2017.01.005

## License

IntonaSphere AI is released under the [MIT License](LICENSE). © 2026 Jamike Ugochukwu Okoroji. You may use, modify and share the code, provided the copyright notice and licence text are kept. Corpus recordings and metadata (e.g. PFC) are not part of this repository and remain under their own terms.

