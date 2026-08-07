import math
import warnings
from typing import Dict, Any

import numpy as np
import pandas as pd
import librosa
import parselmouth
from parselmouth.praat import call


warnings.filterwarnings("ignore")


def safe_float(value):
    """
    Convert numerical output safely to float.
    """
    try:
        if value is None:
            return None
        if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
            return None
        return float(value)
    except Exception:
        return None


def safe_mean(values):
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]
    if len(values) == 0:
        return None
    return float(np.mean(values))


def safe_std(values):
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]
    if len(values) == 0:
        return None
    return float(np.std(values))


def safe_min(values):
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]
    if len(values) == 0:
        return None
    return float(np.min(values))


def safe_max(values):
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]
    if len(values) == 0:
        return None
    return float(np.max(values))


def load_audio_for_voiceprint(audio_path: str, sample_rate: int = 16000):
    """
    Load audio as mono waveform for spectral and MFCC features.
    """
    y, sr = librosa.load(audio_path, sr=sample_rate, mono=True)
    return y, sr


# ============================================================
# Praat-based voice source features
# ============================================================

def extract_praat_voice_source_features(
    audio_path: str,
    pitch_floor: float = 75.0,
    pitch_ceiling: float = 500.0,
) -> Dict[str, Any]:
    """
    Extract F0, intensity, jitter, shimmer, HNR, and voicing features using Praat.

    These are useful for vocal identity / voice quality profiling.
    """
    results = {}

    try:
        sound = parselmouth.Sound(audio_path)
        duration = sound.get_total_duration()

        results["voiceprint_duration_seconds"] = safe_float(duration)

        # Pitch / F0
        pitch = call(sound, "To Pitch", 0.0, pitch_floor, pitch_ceiling)

        mean_f0 = call(pitch, "Get mean", 0, 0, "Hertz")
        min_f0 = call(pitch, "Get minimum", 0, 0, "Hertz", "Parabolic")
        max_f0 = call(pitch, "Get maximum", 0, 0, "Hertz", "Parabolic")
        f0_std = call(pitch, "Get standard deviation", 0, 0, "Hertz")

        results["voiceprint_mean_f0_hz"] = safe_float(mean_f0)
        results["voiceprint_min_f0_hz"] = safe_float(min_f0)
        results["voiceprint_max_f0_hz"] = safe_float(max_f0)
        results["voiceprint_f0_std_hz"] = safe_float(f0_std)

        if results["voiceprint_min_f0_hz"] is not None and results["voiceprint_max_f0_hz"] is not None:
            results["voiceprint_f0_range_hz"] = (
                results["voiceprint_max_f0_hz"] - results["voiceprint_min_f0_hz"]
            )
        else:
            results["voiceprint_f0_range_hz"] = None

        # Voicing ratio from pitch frames
        try:
            pitch_values = pitch.selected_array["frequency"]
            voiced = pitch_values[pitch_values > 0]
            results["voiceprint_voiced_frame_count"] = int(len(voiced))
            results["voiceprint_total_pitch_frame_count"] = int(len(pitch_values))
            results["voiceprint_voiced_ratio"] = (
                float(len(voiced) / len(pitch_values)) if len(pitch_values) > 0 else None
            )
        except Exception:
            results["voiceprint_voiced_frame_count"] = None
            results["voiceprint_total_pitch_frame_count"] = None
            results["voiceprint_voiced_ratio"] = None

        # Intensity
        try:
            intensity = call(sound, "To Intensity", pitch_floor, 0.0, "yes")
            results["voiceprint_mean_intensity_db"] = safe_float(
                call(intensity, "Get mean", 0, 0, "energy")
            )
            results["voiceprint_min_intensity_db"] = safe_float(
                call(intensity, "Get minimum", 0, 0, "Parabolic")
            )
            results["voiceprint_max_intensity_db"] = safe_float(
                call(intensity, "Get maximum", 0, 0, "Parabolic")
            )

            if (
                results["voiceprint_min_intensity_db"] is not None
                and results["voiceprint_max_intensity_db"] is not None
            ):
                results["voiceprint_intensity_range_db"] = (
                    results["voiceprint_max_intensity_db"]
                    - results["voiceprint_min_intensity_db"]
                )
            else:
                results["voiceprint_intensity_range_db"] = None

        except Exception as e:
            results["voiceprint_intensity_error"] = str(e)

        # Jitter / shimmer / HNR
        try:
            point_process = call(
                sound,
                "To PointProcess (periodic, cc)",
                pitch_floor,
                pitch_ceiling,
            )

            results["voiceprint_jitter_local"] = safe_float(
                call(point_process, "Get jitter (local)", 0, 0, 0.0001, 0.02, 1.3)
            )

            results["voiceprint_jitter_local_absolute"] = safe_float(
                call(point_process, "Get jitter (local, absolute)", 0, 0, 0.0001, 0.02, 1.3)
            )

            results["voiceprint_jitter_rap"] = safe_float(
                call(point_process, "Get jitter (rap)", 0, 0, 0.0001, 0.02, 1.3)
            )

            results["voiceprint_jitter_ppq5"] = safe_float(
                call(point_process, "Get jitter (ppq5)", 0, 0, 0.0001, 0.02, 1.3)
            )

            results["voiceprint_shimmer_local"] = safe_float(
                call([sound, point_process], "Get shimmer (local)", 0, 0, 0.0001, 0.02, 1.3, 1.6)
            )

            results["voiceprint_shimmer_local_db"] = safe_float(
                call([sound, point_process], "Get shimmer (local_dB)", 0, 0, 0.0001, 0.02, 1.3, 1.6)
            )

            results["voiceprint_shimmer_apq3"] = safe_float(
                call([sound, point_process], "Get shimmer (apq3)", 0, 0, 0.0001, 0.02, 1.3, 1.6)
            )

            results["voiceprint_shimmer_apq5"] = safe_float(
                call([sound, point_process], "Get shimmer (apq5)", 0, 0, 0.0001, 0.02, 1.3, 1.6)
            )

        except Exception as e:
            results["voiceprint_jitter_shimmer_error"] = str(e)

        try:
            harmonicity = call(sound, "To Harmonicity (cc)", 0.01, pitch_floor, 0.1, 1.0)
            results["voiceprint_hnr_mean_db"] = safe_float(
                call(harmonicity, "Get mean", 0, 0)
            )
        except Exception as e:
            results["voiceprint_hnr_error"] = str(e)

    except Exception as e:
        results["voiceprint_praat_error"] = str(e)

    return results


# ============================================================
# Praat-based formant features
# ============================================================

def extract_formant_features(
    audio_path: str,
    max_formant: float = 5500.0,
    number_of_formants: int = 5,
) -> Dict[str, Any]:
    """
    Extract mean and standard deviation of F1-F4 using Praat Burg formant analysis.
    """
    results = {}

    try:
        sound = parselmouth.Sound(audio_path)
        duration = sound.get_total_duration()

        formant = call(
            sound,
            "To Formant (burg)",
            0.0,
            number_of_formants,
            max_formant,
            0.025,
            50.0,
        )

        times = np.linspace(0.05, max(0.05, duration - 0.05), 100)

        for formant_number in [1, 2, 3, 4]:
            values = []

            for t in times:
                try:
                    value = call(formant, "Get value at time", formant_number, float(t), "Hertz", "Linear")
                    if value and np.isfinite(value):
                        values.append(float(value))
                except Exception:
                    pass

            results[f"voiceprint_f{formant_number}_mean_hz"] = safe_mean(values)
            results[f"voiceprint_f{formant_number}_std_hz"] = safe_std(values)
            results[f"voiceprint_f{formant_number}_min_hz"] = safe_min(values)
            results[f"voiceprint_f{formant_number}_max_hz"] = safe_max(values)

        # Formant dispersion approximation
        f_means = [
            results.get("voiceprint_f1_mean_hz"),
            results.get("voiceprint_f2_mean_hz"),
            results.get("voiceprint_f3_mean_hz"),
            results.get("voiceprint_f4_mean_hz"),
        ]

        f_means = [x for x in f_means if x is not None]

        if len(f_means) >= 2:
            results["voiceprint_formant_mean_dispersion_hz"] = safe_mean(np.diff(f_means))
        else:
            results["voiceprint_formant_mean_dispersion_hz"] = None

    except Exception as e:
        results["voiceprint_formant_error"] = str(e)

    return results


# ============================================================
# Librosa-based spectral and cepstral features
# ============================================================

def extract_spectral_mfcc_features(
    audio_path: str,
    sample_rate: int = 16000,
    n_mfcc: int = 13,
) -> Dict[str, Any]:
    """
    Extract spectral features and MFCC statistics using librosa.

    MFCCs are widely used in speaker recognition and voiceprint-style systems.
    """
    results = {}

    try:
        y, sr = load_audio_for_voiceprint(audio_path, sample_rate=sample_rate)

        if len(y) == 0:
            results["voiceprint_librosa_error"] = "Empty audio signal."
            return results

        # Basic amplitude
        rms = librosa.feature.rms(y=y)[0]
        results["voiceprint_rms_mean"] = safe_mean(rms)
        results["voiceprint_rms_std"] = safe_std(rms)
        results["voiceprint_rms_min"] = safe_min(rms)
        results["voiceprint_rms_max"] = safe_max(rms)

        # Spectral features
        spectral_centroid = librosa.feature.spectral_centroid(y=y, sr=sr)[0]
        spectral_bandwidth = librosa.feature.spectral_bandwidth(y=y, sr=sr)[0]
        spectral_rolloff = librosa.feature.spectral_rolloff(y=y, sr=sr, roll_percent=0.85)[0]
        spectral_flatness = librosa.feature.spectral_flatness(y=y)[0]
        zero_crossing_rate = librosa.feature.zero_crossing_rate(y)[0]

        results["voiceprint_spectral_centroid_mean_hz"] = safe_mean(spectral_centroid)
        results["voiceprint_spectral_centroid_std_hz"] = safe_std(spectral_centroid)

        results["voiceprint_spectral_bandwidth_mean_hz"] = safe_mean(spectral_bandwidth)
        results["voiceprint_spectral_bandwidth_std_hz"] = safe_std(spectral_bandwidth)

        results["voiceprint_spectral_rolloff_mean_hz"] = safe_mean(spectral_rolloff)
        results["voiceprint_spectral_rolloff_std_hz"] = safe_std(spectral_rolloff)

        results["voiceprint_spectral_flatness_mean"] = safe_mean(spectral_flatness)
        results["voiceprint_spectral_flatness_std"] = safe_std(spectral_flatness)

        results["voiceprint_zero_crossing_rate_mean"] = safe_mean(zero_crossing_rate)
        results["voiceprint_zero_crossing_rate_std"] = safe_std(zero_crossing_rate)

        # MFCC features
        mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=n_mfcc)

        for i in range(n_mfcc):
            coeff = mfcc[i, :]
            index = i + 1

            results[f"voiceprint_mfcc_{index}_mean"] = safe_mean(coeff)
            results[f"voiceprint_mfcc_{index}_std"] = safe_std(coeff)
            results[f"voiceprint_mfcc_{index}_min"] = safe_min(coeff)
            results[f"voiceprint_mfcc_{index}_max"] = safe_max(coeff)

        # Delta MFCCs
        try:
            delta_mfcc = librosa.feature.delta(mfcc)

            for i in range(n_mfcc):
                coeff = delta_mfcc[i, :]
                index = i + 1

                results[f"voiceprint_delta_mfcc_{index}_mean"] = safe_mean(coeff)
                results[f"voiceprint_delta_mfcc_{index}_std"] = safe_std(coeff)

        except Exception as e:
            results["voiceprint_delta_mfcc_error"] = str(e)

    except Exception as e:
        results["voiceprint_librosa_error"] = str(e)

    return results


# ============================================================
# Temporal and pause features
# ============================================================

def extract_temporal_pause_features(
    audio_path: str,
    sample_rate: int = 16000,
) -> Dict[str, Any]:
    """
    Extract duration, silence/pause, and rough speech activity features.
    """
    results = {}

    try:
        y, sr = load_audio_for_voiceprint(audio_path, sample_rate=sample_rate)

        duration = librosa.get_duration(y=y, sr=sr)
        results["voiceprint_total_duration_seconds"] = safe_float(duration)

        # Non-silent intervals
        intervals = librosa.effects.split(y, top_db=30)

        speech_duration = 0.0
        for start, end in intervals:
            speech_duration += (end - start) / sr

        silence_duration = max(0.0, duration - speech_duration)

        results["voiceprint_estimated_speech_duration_seconds"] = safe_float(speech_duration)
        results["voiceprint_estimated_silence_duration_seconds"] = safe_float(silence_duration)
        results["voiceprint_estimated_pause_ratio"] = (
            safe_float(silence_duration / duration) if duration > 0 else None
        )
        results["voiceprint_estimated_speech_ratio"] = (
            safe_float(speech_duration / duration) if duration > 0 else None
        )
        results["voiceprint_detected_speech_segments"] = int(len(intervals))

        if len(intervals) > 1:
            pauses = []

            for i in range(len(intervals) - 1):
                pause_samples = intervals[i + 1][0] - intervals[i][1]
                pause_seconds = pause_samples / sr
                if pause_seconds > 0:
                    pauses.append(pause_seconds)

            results["voiceprint_pause_count"] = int(len(pauses))
            results["voiceprint_mean_pause_duration_seconds"] = safe_mean(pauses)
            results["voiceprint_max_pause_duration_seconds"] = safe_max(pauses)
        else:
            results["voiceprint_pause_count"] = 0
            results["voiceprint_mean_pause_duration_seconds"] = None
            results["voiceprint_max_pause_duration_seconds"] = None

    except Exception as e:
        results["voiceprint_temporal_error"] = str(e)

    return results


# ============================================================
# Summary and interpretation
# ============================================================

def build_voiceprint_summary(results: Dict[str, Any]) -> str:
    """
    Build a readable summary of the speaker acoustic profile.
    """
    mean_f0 = results.get("voiceprint_mean_f0_hz")
    f0_range = results.get("voiceprint_f0_range_hz")
    hnr = results.get("voiceprint_hnr_mean_db")
    jitter = results.get("voiceprint_jitter_local")
    shimmer = results.get("voiceprint_shimmer_local")
    centroid = results.get("voiceprint_spectral_centroid_mean_hz")
    voiced_ratio = results.get("voiceprint_voiced_ratio")

    return (
        f"Voiceprint-style acoustic profile: mean F0={mean_f0}, "
        f"F0 range={f0_range}, HNR={hnr}, jitter={jitter}, shimmer={shimmer}, "
        f"spectral centroid={centroid}, voiced ratio={voiced_ratio}. "
        f"Interpret this as a speaker acoustic profile, not as an absolute DNA-like identity test."
    )


def voiceprint_disclaimer() -> str:
    return (
        "This module extracts speaker-specific acoustic variables useful for speaker "
        "characterization and comparison. Voice is not biologically fixed like DNA; "
        "it varies with age, health, emotion, fatigue, microphone quality, recording "
        "environment, language, and speaking style. Results should be interpreted as "
        "an acoustic profile, not as infallible forensic identification."
    )


# ============================================================
# Main public functions
# ============================================================

def analyze_voiceprint_features(
    audio_path: str,
    speaker_id: str = "",
    file_name: str = "",
    sample_rate: int = 16000,
    pitch_floor: float = 75.0,
    pitch_ceiling: float = 500.0,
) -> Dict[str, Any]:
    """
    Extract a broad professional acoustic profile for voiceprint-style analysis.
    """
    results = {
        "voiceprint_module": "Voiceprint / Vocal Empreinte analysis",
        "voiceprint_speaker_id": speaker_id,
        "voiceprint_file_name": file_name,
        "voiceprint_sample_rate": sample_rate,
        "voiceprint_pitch_floor_hz": pitch_floor,
        "voiceprint_pitch_ceiling_hz": pitch_ceiling,
    }

    results.update(
        extract_praat_voice_source_features(
            audio_path,
            pitch_floor=pitch_floor,
            pitch_ceiling=pitch_ceiling,
        )
    )

    results.update(
        extract_formant_features(
            audio_path,
            max_formant=5500.0,
            number_of_formants=5,
        )
    )

    results.update(
        extract_spectral_mfcc_features(
            audio_path,
            sample_rate=sample_rate,
            n_mfcc=13,
        )
    )

    results.update(
        extract_temporal_pause_features(
            audio_path,
            sample_rate=sample_rate,
        )
    )

    results["voiceprint_summary"] = build_voiceprint_summary(results)
    results["voiceprint_scientific_disclaimer"] = voiceprint_disclaimer()
    results["voiceprint_analysis_status"] = "completed"

    return results


def voiceprint_results_to_dataframe(
    results: Dict[str, Any],
    speaker_id: str = "",
    file_name: str = "",
) -> pd.DataFrame:
    """
    Convert voiceprint result dictionary to one-row dataframe.
    """
    row = {
        "speaker_id": speaker_id or results.get("voiceprint_speaker_id", ""),
        "file_name": file_name or results.get("voiceprint_file_name", ""),
    }

    row.update(results)

    return pd.DataFrame([row])
