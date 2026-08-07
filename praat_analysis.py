import math
import numpy as np
import pandas as pd
import parselmouth
from parselmouth.praat import call


def safe_value(value):
    """
    Convert NaN or infinite values into None for clean display.
    """
    try:
        if value is None:
            return None
        if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
            return None
        return value
    except Exception:
        return None


def analyze_audio_with_praat(audio_path: str) -> dict:
    """
    Extract global acoustic/phonetic features using Praat through Parselmouth.

    Features:
    - duration
    - mean F0
    - min F0
    - max F0
    - F0 range
    - mean intensity
    - midpoint formants F1, F2, F3
    """
    sound = parselmouth.Sound(audio_path)
    duration = sound.get_total_duration()

    pitch = sound.to_pitch()

    mean_f0 = call(pitch, "Get mean", 0, 0, "Hertz")
    min_f0 = call(pitch, "Get minimum", 0, 0, "Hertz", "Parabolic")
    max_f0 = call(pitch, "Get maximum", 0, 0, "Hertz", "Parabolic")

    intensity = sound.to_intensity()
    mean_intensity = call(intensity, "Get mean", 0, 0, "energy")

    formant = sound.to_formant_burg()
    midpoint = duration / 2

    f1_mid = call(formant, "Get value at time", 1, midpoint, "Hertz", "Linear")
    f2_mid = call(formant, "Get value at time", 2, midpoint, "Hertz", "Linear")
    f3_mid = call(formant, "Get value at time", 3, midpoint, "Hertz", "Linear")

    f0_range = None
    if safe_value(max_f0) is not None and safe_value(min_f0) is not None:
        f0_range = max_f0 - min_f0

    return {
        "duration_seconds": safe_value(duration),
        "mean_f0_hz": safe_value(mean_f0),
        "min_f0_hz": safe_value(min_f0),
        "max_f0_hz": safe_value(max_f0),
        "f0_range_hz": safe_value(f0_range),
        "mean_intensity_db": safe_value(mean_intensity),
        "f1_midpoint_hz": safe_value(f1_mid),
        "f2_midpoint_hz": safe_value(f2_mid),
        "f3_midpoint_hz": safe_value(f3_mid),
    }


def extract_pitch_track(audio_path: str, time_step: float = 0.01) -> pd.DataFrame:
    """
    Extract pitch track for plotting F0 contour.
    """
    sound = parselmouth.Sound(audio_path)
    pitch = sound.to_pitch(time_step=time_step)

    times = pitch.xs()
    f0_values = pitch.selected_array["frequency"]

    cleaned_f0 = []

    for value in f0_values:
        if value == 0 or np.isnan(value):
            cleaned_f0.append(np.nan)
        else:
            cleaned_f0.append(value)

    return pd.DataFrame(
        {
            "time_seconds": times,
            "f0_hz": cleaned_f0,
        }
    )


def analyze_final_pitch_movement(audio_path: str, final_window: float = 0.5) -> dict:
    """
    Analyze final pitch movement in the final part of the audio.

    This helps classify final contour as:
    - Rising
    - Falling
    - Plateau/Stable
    """
    sound = parselmouth.Sound(audio_path)
    duration = sound.get_total_duration()

    pitch = sound.to_pitch(time_step=0.01)

    start_time = max(0, duration - final_window)
    end_time = duration

    times = pitch.xs()
    f0_values = pitch.selected_array["frequency"]

    final_times = []
    final_f0 = []

    for t, f0 in zip(times, f0_values):
        if start_time <= t <= end_time and f0 > 0:
            final_times.append(t)
            final_f0.append(f0)

    if len(final_f0) < 2:
        return {
            "final_window_seconds": final_window,
            "final_start_f0_hz": None,
            "final_end_f0_hz": None,
            "final_f0_change_hz": None,
            "final_slope_hz_per_sec": None,
            "contour_label": "Insufficient voiced data",
        }

    final_start_f0 = final_f0[0]
    final_end_f0 = final_f0[-1]
    f0_change = final_end_f0 - final_start_f0
    time_change = final_times[-1] - final_times[0]

    if time_change > 0:
        slope = f0_change / time_change
    else:
        slope = None

    if f0_change > 15:
        contour_label = "Rising"
    elif f0_change < -15:
        contour_label = "Falling"
    else:
        contour_label = "Plateau/Stable"

    return {
        "final_window_seconds": final_window,
        "final_start_f0_hz": safe_value(final_start_f0),
        "final_end_f0_hz": safe_value(final_end_f0),
        "final_f0_change_hz": safe_value(f0_change),
        "final_slope_hz_per_sec": safe_value(slope),
        "contour_label": contour_label,
    }


def analyze_prominence_and_tune(audio_path: str, transcript: str = "") -> dict:
    """
    Estimate where interrogativity and prominence are marked.

    This gives a practical first-pass interpretation of:
    - final syllable-like region
    - final Accentual Phrase-like region
    - final Intonational Phrase-like region
    - interrogativity marking
    - prominence location
    - tune label candidate

    Important:
    This is heuristic. It is not a replacement for manual Praat/TextGrid/F_ToBI analysis.
    """
    sound = parselmouth.Sound(audio_path)
    duration = sound.get_total_duration()

    pitch = sound.to_pitch(time_step=0.01)
    intensity = sound.to_intensity()

    times = pitch.xs()
    f0_values = pitch.selected_array["frequency"]

    final_syllable_window = 0.30
    ap_window = 0.75
    ip_window = 1.20

    def voiced_f0_in_window(window_size: float):
        start_time = max(0, duration - window_size)

        window_times = []
        window_f0 = []

        for t, f0 in zip(times, f0_values):
            if start_time <= t <= duration and f0 > 0:
                window_times.append(t)
                window_f0.append(f0)

        return window_times, window_f0

    def f0_change_and_slope(window_size: float):
        window_times, window_f0 = voiced_f0_in_window(window_size)

        if len(window_f0) < 2:
            return None, None, None, None

        f0_start = window_f0[0]
        f0_end = window_f0[-1]
        f0_change = f0_end - f0_start
        time_change = window_times[-1] - window_times[0]

        if time_change > 0:
            slope = f0_change / time_change
        else:
            slope = None

        return f0_start, f0_end, f0_change, slope

    fs_start, fs_end, fs_change, fs_slope = f0_change_and_slope(final_syllable_window)
    ap_start, ap_end, ap_change, ap_slope = f0_change_and_slope(ap_window)
    ip_start, ip_end, ip_change, ip_slope = f0_change_and_slope(ip_window)

    final_start_time = max(0, duration - ap_window)

    try:
        mean_intensity_total = call(intensity, "Get mean", 0, duration, "energy")
    except Exception:
        mean_intensity_total = None

    try:
        mean_intensity_final = call(
            intensity,
            "Get mean",
            final_start_time,
            duration,
            "energy",
        )
    except Exception:
        mean_intensity_final = None

    if (
        safe_value(mean_intensity_total) is not None
        and safe_value(mean_intensity_final) is not None
    ):
        intensity_difference = mean_intensity_final - mean_intensity_total
    else:
        intensity_difference = None

    if ip_change is None:
        interrogativity_marking = (
            "Insufficient voiced F0 data to determine interrogative marking."
        )
        tune_label = "Undetermined"
        domain = "Undetermined"

    elif ip_change > 15:
        interrogativity_marking = (
            "Interrogativity is likely marked by a final rising F0 movement."
        )
        tune_label = (
            "Candidate: L* H% or H* H%, depending on pitch accent alignment."
        )
        domain = "IP-final boundary, with possible AP-final rise."

    elif ip_change < -15:
        interrogativity_marking = (
            "No final rise detected. Interrogativity may be marked syntactically, "
            "lexically, or by a falling/rhetorical contour."
        )
        tune_label = "Candidate: H* L% or falling boundary contour."
        domain = "IP-final falling boundary."

    else:
        interrogativity_marking = (
            "Final F0 is relatively stable. Interrogativity may be marked by syntax, "
            "plateau contour, or earlier prominence."
        )
        tune_label = "Candidate: plateau/stable boundary tone."
        domain = "AP/IP-final plateau or weak boundary movement."

    if fs_change is not None and fs_change > 15:
        prominence_location = (
            "Final syllable-like region shows a clear rising movement; "
            "prominence is likely on the final syllable."
        )

    elif ap_change is not None and ap_change > 15:
        prominence_location = (
            "The final Accentual Phrase-like region shows rising movement; "
            "prominence is likely AP-final."
        )

    elif intensity_difference is not None and intensity_difference > 2:
        prominence_location = (
            "The final region has stronger intensity; prominence may be carried "
            "by the final AP/IP region."
        )

    elif ap_change is not None and abs(ap_change) <= 15:
        prominence_location = (
            "No strong final F0 movement detected; prominence may be weak, "
            "distributed, or located earlier in the phrase."
        )

    else:
        prominence_location = "Prominence could not be determined automatically."

    return {
        "final_syllable_window_seconds": final_syllable_window,
        "ap_window_seconds": ap_window,
        "ip_window_seconds": ip_window,

        "final_syllable_start_f0_hz": safe_value(fs_start),
        "final_syllable_end_f0_hz": safe_value(fs_end),
        "final_syllable_f0_change_hz": safe_value(fs_change),
        "final_syllable_slope_hz_per_sec": safe_value(fs_slope),

        "ap_final_start_f0_hz": safe_value(ap_start),
        "ap_final_end_f0_hz": safe_value(ap_end),
        "ap_final_f0_change_hz": safe_value(ap_change),
        "ap_final_slope_hz_per_sec": safe_value(ap_slope),

        "ip_final_start_f0_hz": safe_value(ip_start),
        "ip_final_end_f0_hz": safe_value(ip_end),
        "ip_final_f0_change_hz": safe_value(ip_change),
        "ip_final_slope_hz_per_sec": safe_value(ip_slope),

        "mean_intensity_total_db": safe_value(mean_intensity_total),
        "mean_intensity_final_region_db": safe_value(mean_intensity_final),
        "final_intensity_difference_db": safe_value(intensity_difference),

        "interrogativity_marking": interrogativity_marking,
        "prominence_location": prominence_location,
        "prosodic_domain": domain,
        "tune_label_candidate": tune_label,
    }


def analyze_final_syllable_alignment(
    audio_path: str,
    final_syllable_window: float = 0.30,
) -> dict:
    """
    Estimate F0 alignment values for the final syllable-like region.

    This uses the final N seconds of the audio as an approximation.
    For dissertation-grade analysis, use TextGrid syllable boundaries.
    """
    sound = parselmouth.Sound(audio_path)
    duration = sound.get_total_duration()

    pitch = sound.to_pitch(time_step=0.01)

    final_syllable_onset = max(0, duration - final_syllable_window)
    final_syllable_offset = duration
    final_syllable_midpoint = (final_syllable_onset + final_syllable_offset) / 2
    phrase_boundary_time = duration

    def get_f0_at_time(time_point: float):
        try:
            value = call(pitch, "Get value at time", time_point, "Hertz", "Linear")
            return safe_value(value)
        except Exception:
            return None

    def get_nearest_voiced_f0_before(time_point: float, search_window: float = 0.15):
        """
        Find nearest voiced F0 before a given time point.
        Useful when F0 is undefined at the exact endpoint.
        """
        times = pitch.xs()
        f0_values = pitch.selected_array["frequency"]

        start_time = max(0, time_point - search_window)

        candidates = []

        for t, f0 in zip(times, f0_values):
            if start_time <= t <= time_point and f0 > 0:
                candidates.append((t, f0))

        if not candidates:
            return None, None

        nearest_time, nearest_f0 = candidates[-1]
        return safe_value(nearest_time), safe_value(nearest_f0)

    f0_start = get_f0_at_time(final_syllable_onset)
    f0_midpoint = get_f0_at_time(final_syllable_midpoint)
    f0_end = get_f0_at_time(final_syllable_offset)
    f0_phrase_boundary = get_f0_at_time(phrase_boundary_time)

    nearest_time_before_interval_end, nearest_f0_before_interval_end = (
        get_nearest_voiced_f0_before(final_syllable_offset)
    )

    nearest_time_before_phrase_boundary, nearest_f0_before_phrase_boundary = (
        get_nearest_voiced_f0_before(phrase_boundary_time)
    )

    times = pitch.xs()
    f0_values = pitch.selected_array["frequency"]

    peak_f0 = None
    peak_time = None

    for t, f0 in zip(times, f0_values):
        if final_syllable_onset <= t <= final_syllable_offset and f0 > 0:
            if peak_f0 is None or f0 > peak_f0:
                peak_f0 = f0
                peak_time = t

    if peak_time is None:
        alignment_interpretation = "F0 peak could not be determined."
        tune_decision = "Undetermined"

    else:
        syllable_duration = final_syllable_offset - final_syllable_onset

        early_boundary = final_syllable_onset + (syllable_duration * 0.33)
        late_boundary = final_syllable_onset + (syllable_duration * 0.66)

        if peak_time < early_boundary:
            alignment_interpretation = (
                "F0 peak occurs early in the final syllable-like region. "
                "This may suggest early prominence or pitch tracking instability."
            )
            tune_decision = "Possible H* H%, but verify manually."

        elif early_boundary <= peak_time <= late_boundary:
            alignment_interpretation = (
                "F0 peak occurs within the central part of the final syllable-like region. "
                "This suggests the high target may align with the prominent syllable."
            )
            tune_decision = "Likely H* H%, if the syllable is perceptually prominent."

        else:
            alignment_interpretation = (
                "F0 peak occurs late, near the phrase boundary. "
                "This suggests the high target may be boundary-aligned rather than syllable-aligned."
            )
            tune_decision = (
                "Likely L* H%, if the syllable begins low/mid and rises to the boundary."
            )

    return {
        "final_syllable_onset_time": safe_value(final_syllable_onset),
        "final_syllable_midpoint_time": safe_value(final_syllable_midpoint),
        "final_syllable_offset_time": safe_value(final_syllable_offset),
        "phrase_boundary_time": safe_value(phrase_boundary_time),

        "f0_at_final_syllable_start_hz": safe_value(f0_start),
        "f0_at_final_syllable_midpoint_hz": safe_value(f0_midpoint),
        "f0_at_final_syllable_end_hz": safe_value(f0_end),
        "f0_at_phrase_boundary_hz": safe_value(f0_phrase_boundary),

        "nearest_voiced_time_before_final_syllable_end": safe_value(
            nearest_time_before_interval_end
        ),
        "nearest_voiced_f0_before_final_syllable_end_hz": safe_value(
            nearest_f0_before_interval_end
        ),
        "nearest_voiced_time_before_phrase_boundary": safe_value(
            nearest_time_before_phrase_boundary
        ),
        "nearest_voiced_f0_before_phrase_boundary_hz": safe_value(
            nearest_f0_before_phrase_boundary
        ),

        "f0_peak_time_in_final_syllable": safe_value(peak_time),
        "f0_peak_value_in_final_syllable_hz": safe_value(peak_f0),

        "pitch_accent_alignment_interpretation": alignment_interpretation,
        "lh_or_hh_tune_decision": tune_decision,
    }


def analyze_textgrid_final_interval_alignment(
    audio_path: str,
    final_interval: dict,
) -> dict:
    """
    Use exact TextGrid interval boundaries to measure F0 alignment.

    This calculates:
    - F0 at final interval onset
    - F0 at final interval midpoint
    - F0 at final interval offset
    - F0 at phrase boundary
    - nearest voiced F0 before interval offset
    - nearest voiced F0 before phrase boundary
    - Time of F0 peak inside the interval
    - Value of F0 peak inside the interval

    This is the preferred method for dissertation-quality analysis.
    """

    if not final_interval or final_interval.get("start") is None:
        return {
            "textgrid_tier_used": final_interval.get("tier_name", "") if final_interval else "",
            "textgrid_final_interval_label": "",
            "textgrid_final_interval_start": None,
            "textgrid_final_interval_midpoint": None,
            "textgrid_final_interval_end": None,
            "textgrid_phrase_boundary_time": None,

            "textgrid_f0_at_interval_start_hz": None,
            "textgrid_f0_at_interval_midpoint_hz": None,
            "textgrid_f0_at_interval_end_hz": None,
            "textgrid_f0_at_phrase_boundary_hz": None,

            "textgrid_nearest_voiced_time_before_interval_end": None,
            "textgrid_nearest_voiced_f0_before_interval_end_hz": None,
            "textgrid_nearest_voiced_time_before_phrase_boundary": None,
            "textgrid_nearest_voiced_f0_before_phrase_boundary_hz": None,

            "textgrid_f0_peak_time_in_interval": None,
            "textgrid_f0_peak_value_in_interval_hz": None,
            "textgrid_alignment_interpretation": "No usable TextGrid interval was provided.",
            "textgrid_lh_or_hh_tune_decision": "Undetermined",
        }

    sound = parselmouth.Sound(audio_path)
    duration = sound.get_total_duration()
    pitch = sound.to_pitch(time_step=0.01)

    interval_start = final_interval["start"]
    interval_midpoint = final_interval["midpoint"]
    interval_end = final_interval["end"]
    phrase_boundary_time = duration

    # Guard against tiny TextGrid/audio mismatch
    interval_start = max(0, min(interval_start, duration))
    interval_midpoint = max(0, min(interval_midpoint, duration))
    interval_end = max(0, min(interval_end, duration))

    def get_f0_at_time(time_point: float):
        """
        Try to get F0 exactly at a time point.
        If Praat has no voiced value there, return None.
        """
        try:
            value = call(pitch, "Get value at time", time_point, "Hertz", "Linear")
            return safe_value(value)
        except Exception:
            return None

    def get_nearest_voiced_f0_before(time_point: float, search_window: float = 0.15):
        """
        Find nearest voiced F0 before a given time point.

        This is important because F0 is often undefined at the exact final boundary
        due to silence, devoicing, creaky voice, or end-of-file pitch-frame limits.
        """
        times = pitch.xs()
        f0_values = pitch.selected_array["frequency"]

        start_time = max(0, time_point - search_window)

        candidates = []

        for t, f0 in zip(times, f0_values):
            if start_time <= t <= time_point and f0 > 0:
                candidates.append((t, f0))

        if not candidates:
            return None, None

        nearest_time, nearest_f0 = candidates[-1]
        return safe_value(nearest_time), safe_value(nearest_f0)

    f0_start = get_f0_at_time(interval_start)
    f0_midpoint = get_f0_at_time(interval_midpoint)
    f0_end = get_f0_at_time(interval_end)
    f0_phrase_boundary = get_f0_at_time(phrase_boundary_time)

    nearest_time_before_interval_end, nearest_f0_before_interval_end = (
        get_nearest_voiced_f0_before(interval_end)
    )

    nearest_time_before_phrase_boundary, nearest_f0_before_phrase_boundary = (
        get_nearest_voiced_f0_before(phrase_boundary_time)
    )

    times = pitch.xs()
    f0_values = pitch.selected_array["frequency"]

    peak_f0 = None
    peak_time = None

    for t, f0 in zip(times, f0_values):
        if interval_start <= t <= interval_end and f0 > 0:
            if peak_f0 is None or f0 > peak_f0:
                peak_f0 = f0
                peak_time = t

    if peak_time is None:
        alignment_interpretation = (
            "F0 peak could not be determined inside the TextGrid final interval."
        )
        tune_decision = "Undetermined"

    else:
        interval_duration = interval_end - interval_start

        if interval_duration <= 0:
            alignment_interpretation = "Final TextGrid interval has invalid duration."
            tune_decision = "Undetermined"

        else:
            early_boundary = interval_start + (interval_duration * 0.33)
            late_boundary = interval_start + (interval_duration * 0.66)

            if peak_time < early_boundary:
                alignment_interpretation = (
                    "F0 peak occurs early in the TextGrid-defined final interval. "
                    "This may indicate early prominence or pitch tracking instability."
                )
                tune_decision = "Possible H* H%, but verify manually."

            elif early_boundary <= peak_time <= late_boundary:
                alignment_interpretation = (
                    "F0 peak occurs near the center of the TextGrid-defined final interval. "
                    "This suggests the high target may align with the prominent syllable."
                )
                tune_decision = "Likely H* H%, if the interval is the prominent syllable."

            else:
                alignment_interpretation = (
                    "F0 peak occurs late in the TextGrid-defined final interval, "
                    "near the phrase boundary. This suggests boundary alignment."
                )
                tune_decision = (
                    "Likely L* H%, if the interval begins low/mid and rises to H%."
                )

    return {
        "textgrid_tier_used": final_interval.get("tier_name", ""),
        "textgrid_final_interval_label": final_interval.get("label", ""),
        "textgrid_final_interval_start": safe_value(interval_start),
        "textgrid_final_interval_midpoint": safe_value(interval_midpoint),
        "textgrid_final_interval_end": safe_value(interval_end),
        "textgrid_phrase_boundary_time": safe_value(phrase_boundary_time),

        "textgrid_f0_at_interval_start_hz": safe_value(f0_start),
        "textgrid_f0_at_interval_midpoint_hz": safe_value(f0_midpoint),
        "textgrid_f0_at_interval_end_hz": safe_value(f0_end),
        "textgrid_f0_at_phrase_boundary_hz": safe_value(f0_phrase_boundary),

        "textgrid_nearest_voiced_time_before_interval_end": safe_value(
            nearest_time_before_interval_end
        ),
        "textgrid_nearest_voiced_f0_before_interval_end_hz": safe_value(
            nearest_f0_before_interval_end
        ),
        "textgrid_nearest_voiced_time_before_phrase_boundary": safe_value(
            nearest_time_before_phrase_boundary
        ),
        "textgrid_nearest_voiced_f0_before_phrase_boundary_hz": safe_value(
            nearest_f0_before_phrase_boundary
        ),

        "textgrid_f0_peak_time_in_interval": safe_value(peak_time),
        "textgrid_f0_peak_value_in_interval_hz": safe_value(peak_f0),

        "textgrid_alignment_interpretation": alignment_interpretation,
        "textgrid_lh_or_hh_tune_decision": tune_decision,
    }


def build_acoustic_dataframe(
    global_results: dict,
    final_results: dict,
    tune_results: dict = None,
    alignment_results: dict = None,
    textgrid_alignment_results: dict = None,
) -> pd.DataFrame:
    """
    Combine global acoustic results, final contour results, tune results,
    final-syllable alignment results, and TextGrid-based alignment results.
    """
    combined = {}
    combined.update(global_results)
    combined.update(final_results)

    if tune_results:
        combined.update(tune_results)

    if alignment_results:
        combined.update(alignment_results)

    if textgrid_alignment_results:
        combined.update(textgrid_alignment_results)

    return pd.DataFrame([combined])