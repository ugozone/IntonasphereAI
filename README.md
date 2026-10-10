# IntonaSphere AI Transcriber + Praat Analyzer

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

```bash
cd ~/IntonasphereAI
conda activate jamispeak-transcriber
python -m pip install -r requirements.txt
```

## Run

```bash
conda activate jamispeak-transcriber
python -m streamlit run app.py
```

## How to cite

If you use IntonaSphere AI in your research, please cite the software. GitHub's **"Cite this repository"** button (right-hand sidebar) gives APA and BibTeX generated from [`CITATION.cff`](CITATION.cff); BibTeX for the tool and its core dependencies is also in [`CITATION.bib`](CITATION.bib).

> Okoroji, J. U. (2026). *IntonaSphere AI: A transcription and Praat-based prosody analysis toolkit* (Version 0.1.0) [Computer software]. https://github.com/ugozone/IntonasphereAI

```bibtex
@software{Okoroji_IntonaSphere_AI_2026,
  author  = {Okoroji, Jamike Ugochukwu},
  title   = {{IntonaSphere AI: A Transcription and Praat-Based Prosody Analysis Toolkit}},
  year    = {2026},
  version = {0.1.0},
  url     = {https://github.com/ugozone/IntonasphereAI},
  note    = {Project website: https://intonasphereai.org/}
}
```

IntonaSphere AI's acoustic measures are computed with Praat through Parselmouth, so please also cite:

- Boersma, P., & Weenink, D. *Praat: doing phonetics by computer* [Computer program]. https://www.praat.org
- Jadoul, Y., Thompson, B., & de Boer, B. (2018). Introducing Parselmouth: A Python interface to Praat. *Journal of Phonetics, 71*, 1–15. https://doi.org/10.1016/j.wocn.2018.07.001

If you use the transcription module, cite Whisper (Radford et al., 2023); the entry is in `CITATION.bib`.
