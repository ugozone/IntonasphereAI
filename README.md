# JamiSpeak Transcriber + Praat Analyzer

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
cd ~/jamispeak-transcriber
conda activate jamispeak-transcriber
python -m pip install -r requirements.txt