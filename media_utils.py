import os
import re
import uuid
import shutil
import subprocess
from pathlib import Path

import yt_dlp


UPLOAD_DIR = "uploads"
OUTPUT_DIR = "outputs"

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)


def check_ffmpeg_installed() -> bool:
    """
    Check whether FFmpeg is available.
    """
    return shutil.which("ffmpeg") is not None


def safe_filename(filename: str) -> str:
    """
    Make uploaded filenames safe and unique.
    """
    name = Path(filename).stem
    suffix = Path(filename).suffix

    clean_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", name).strip("_")
    unique_id = uuid.uuid4().hex[:8]

    return f"{clean_name}_{unique_id}{suffix}"


def save_uploaded_file(uploaded_file) -> str:
    """
    Save a Streamlit uploaded file to disk.
    """
    filename = safe_filename(uploaded_file.name)
    path = os.path.join(UPLOAD_DIR, filename)

    with open(path, "wb") as f:
        f.write(uploaded_file.getbuffer())

    return path


def extract_speaker_id_from_filename(file_name_or_path: str) -> str:
    """
    Extract speaker ID from filename.

    Examples:
    maabh1tw1.wav -> maabh1tw1
    11aal1tw_PM_ira_t_il.wav -> 11aal1tw
    """
    base = os.path.basename(file_name_or_path)
    stem = os.path.splitext(base)[0]

    # Remove random suffix from safe_filename
    stem = re.sub(r"_[a-f0-9]{8}$", "", stem)

    # Prefer first underscore-separated token
    if "_" in stem:
        return stem.split("_")[0]

    return stem


def convert_to_wav(
    input_path: str,
    sample_rate: int = 16000,
    clean_audio: bool = True,
) -> str:
    """
    Convert audio/video to WAV using FFmpeg.

    Cleaning pipeline:
    - mono
    - target sample rate
    - highpass filter to remove rumble
    - lowpass filter to reduce high-frequency noise
    - loudnorm to normalize volume

    This improves transcription reliability for Whisper.
    """
    if not check_ffmpeg_installed():
        raise RuntimeError("FFmpeg is not installed or not available in PATH.")

    input_path = str(input_path)
    stem = Path(input_path).stem
    output_path = os.path.join(OUTPUT_DIR, f"{stem}_clean_{sample_rate}.wav")

    if clean_audio:
        audio_filter = "highpass=f=80,lowpass=f=8000,loudnorm"
    else:
        audio_filter = "loudnorm"

    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        input_path,
        "-vn",
        "-ac",
        "1",
        "-ar",
        str(sample_rate),
        "-af",
        audio_filter,
        output_path,
    ]

    result = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg conversion failed:\n{result.stderr}")

    return output_path


def download_media_from_url(url: str) -> str:
    """
    Download public media using yt-dlp.

    Use only for media the user owns, has permission to process,
    or is legally allowed to transcribe.
    """
    if not url.strip():
        raise ValueError("No URL provided.")

    output_template = os.path.join(UPLOAD_DIR, "%(title).80s_%(id)s.%(ext)s")

    ydl_opts = {
        "outtmpl": output_template,
        "format": "bestaudio/best",
        "noplaylist": True,
        "quiet": False,
        "no_warnings": False,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        downloaded_path = ydl.prepare_filename(info)

    return downloaded_path
