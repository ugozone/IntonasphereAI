import argparse
import math
import os
import re
from pathlib import Path
from typing import Dict, Optional, Tuple, List

import numpy as np
import pandas as pd
import parselmouth
from parselmouth.praat import call
from praatio import textgrid


# ============================================================
# General helpers
# ============================================================

AUDIO_EXTENSIONS = [".wav", ".mp3", ".m4a", ".flac", ".ogg", ".aac", ".mp4", ".mov", ".webm"]
TEXTGRID_EXTENSIONS = [".TextGrid", ".textgrid"]


def safe_float(value):
    try:
        if value is None:
            return None
        value = float(value)
        if math.isnan(value) or math.isinf(value):
            return None
        return value
    except Exception:
        return None


def normalize_string(value: str) -> str:
    if value is None:
        return ""
    return re.sub(r"[^a-zA-Z0-9]+", "", str(value).lower())


def is_pause_or_silence_label(label: str) -> bool:
    """
    Identify TextGrid labels that are pauses, silence, or empty intervals.
    This prevents MAS extraction from treating <p:> as the final syllable.
    """
    clean = str(label or "").strip().lower()

    pause_labels = {
        "",
        "<p:>",
        "<p>",
        "p",
        "sp",
        "sil",
        "silence",
        "pause",
        "#",
    }

    return clean in pause_labels or clean.startswith("<p")


def hz_to_st(f0_hz: float, reference_hz: float) -> Optional[float]:
    """
    Convert Hz to semitones relative to a reference F0.

    For cross-speaker comparison, the reference is usually the speaker/file median F0.
    """
    if f0_hz is None or reference_hz is None:
        return None
    if f0_hz <= 0 or reference_hz <= 0:
        return None
    return 12 * math.log2(f0_hz / reference_hz)


def find_matching_file(
    speaker_id: str,
    sentence_id: str,
    token_id: str,
    search_dir: str,
    extensions: List[str],
) -> Optional[str]:
    """
    Strict PFC-aware audio/TextGrid matching for all speakers.

    For question rows:
    Q1 must match tw1.
    Q2 must match tw2.
    Q3 must match tw3.

    If the correct Q-specific file is missing, return None.
    Do not reuse Q1 or a bare speaker file for Q2/Q3.
    """

    search_path = Path(search_dir)

    if not search_path.exists():
        return None

    files = []
    for ext in extensions:
        files.extend(list(search_path.rglob(f"*{ext}")))

    if not files:
        return None

    files = sorted(files, key=lambda f: len(f.stem))

    token_norm = normalize_string(token_id)
    speaker_norm = normalize_string(speaker_id)
    sentence_norm = normalize_string(sentence_id)

    def stem_norm(f):
        return normalize_string(f.stem)

    derived_markers = ["ph", "emoi", "pitch", "copy", "backup"]

    clean_files = [
        f for f in files
        if not any(marker in stem_norm(f) for marker in derived_markers)
    ]

    if not clean_files:
        clean_files = files

    question_number = ""

    if sentence_norm in {"q1", "q2", "q3"}:
        question_number = sentence_norm[-1]
    elif token_norm.endswith("q1"):
        question_number = "1"
    elif token_norm.endswith("q2"):
        question_number = "2"
    elif token_norm.endswith("q3"):
        question_number = "3"

    speaker_base = speaker_norm

    # If speaker is already a task file such as rcamp1tw1, reduce it to rcamp1.
    if speaker_base.endswith(("tw1", "tw2", "tw3")):
        speaker_base = speaker_base[:-3]

    candidate_bases = []

    if question_number:
        # General PFC pattern:
        # ciaak1 + Q2 -> ciaak1tw2
        if speaker_base:
            candidate_bases.append(speaker_base + "tw" + question_number)

        # Special case:
        # 11adp1tw + Q2 -> 11adp1tw2
        if speaker_base.endswith("tw"):
            candidate_bases.append(speaker_base + question_number)

        # Token base:
        # rcamp1tw1_Q1 -> rcamp1tw1
        if token_norm:
            token_base = token_norm
            for q in ["q1", "q2", "q3"]:
                if token_base.endswith(q):
                    token_base = token_base[:-len(q)].rstrip("_-")
            if token_base:
                candidate_bases.append(token_base)

        # Remove duplicate candidates
        seen = set()
        candidate_bases = [
            c for c in candidate_bases
            if c and not (c in seen or seen.add(c))
        ]

        # Exact Q-specific match only
        for candidate in candidate_bases:
            for f in clean_files:
                if stem_norm(f) == candidate:
                    return str(f)

        # Startswith Q-specific match, but only if it is not a derived marker file
        for candidate in candidate_bases:
            matches = [
                f for f in clean_files
                if stem_norm(f).startswith(candidate)
            ]
            if matches:
                matches = sorted(matches, key=lambda f: len(f.stem))
                return str(matches[0])

        # Critical rule:
        # For Q1/Q2/Q3 rows, do not fall back to another question's file.
        return None

    # Non-question rows only: allow exact speaker match
    if speaker_norm:
        for f in clean_files:
            if stem_norm(f) == speaker_norm:
                return str(f)

    # Non-question fallback only
    speaker_matches = [
        f for f in clean_files
        if speaker_norm and speaker_norm in stem_norm(f)
    ]
    if speaker_matches:
        speaker_matches = sorted(speaker_matches, key=lambda f: len(f.stem))
        return str(speaker_matches[0])

    return None


# ============================================================
# TextGrid helpers
# ============================================================

def load_textgrid(textgrid_path: str):
    return textgrid.openTextgrid(textgrid_path, includeEmptyIntervals=True)


def get_tier_names(textgrid_path: str) -> List[str]:
    tg = load_textgrid(textgrid_path)
    return list(tg.tierNames)


def find_tier_by_candidates(textgrid_path: str, candidates: List[str]) -> str:
    names = get_tier_names(textgrid_path)
    lower = {name.lower(): name for name in names}

    for cand in candidates:
        if cand.lower() in lower:
            return lower[cand.lower()]

    return ""


def find_word_tier(textgrid_path: str) -> str:
    return find_tier_by_candidates(
        textgrid_path,
        ["ORT-MAU", "ORT", "word", "words", "mots"],
    )


def find_syllable_tier(textgrid_path: str) -> str:
    return find_tier_by_candidates(
        textgrid_path,
        ["MAS", "syllable", "syllables", "syll", "syllabe", "syllabes"],
    )


def find_phone_tier(textgrid_path: str) -> str:
    return find_tier_by_candidates(
        textgrid_path,
        ["MAU", "phone", "phones", "phoneme", "phonemes", "segment", "segments"],
    )


def get_non_empty_intervals(textgrid_path: str, tier_name: str) -> List[Dict]:
    tg = load_textgrid(textgrid_path)
    tier = tg.getTier(tier_name)

    intervals = []
    textgrid_stem = normalize_string(Path(textgrid_path).stem)

    filename_intervals = []

    # Detect accidental filename labels from ORT-MAU.
    # Example:
    # ORT-MAU final label: maajs1tw3
    # MAS overlapping label: m a Z w
    # We must remove both.
    try:
        if tier_name != "ORT-MAU":
            ort_tier = tg.getTier("ORT-MAU")
            for ort_entry in ort_tier.entries:
                ort_label = str(ort_entry.label).strip()
                if normalize_string(ort_label) == textgrid_stem:
                    filename_intervals.append(
                        (
                            float(ort_entry.start),
                            float(ort_entry.end),
                        )
                    )
    except Exception:
        filename_intervals = []

    def overlaps_filename_interval(start: float, end: float) -> bool:
        for bad_start, bad_end in filename_intervals:
            if start < bad_end and end > bad_start:
                return True
        return False

    for entry in tier.entries:
        start = float(entry.start)
        end = float(entry.end)
        label = str(entry.label).strip()
        label_norm = normalize_string(label)

        if not label:
            continue

        if is_pause_or_silence_label(label):
            continue

        # Remove direct filename labels, for example maajs1tw3.
        if label_norm == textgrid_stem:
            continue

        # Remove phonetic/syllable intervals that overlap an ORT-MAU filename label.
        # Example: MAS label m a Z w overlapping ORT-MAU maajs1tw3.
        if overlaps_filename_interval(start, end):
            continue

        intervals.append(
            {
                "start": start,
                "end": end,
                "label": label,
            }
        )

    return intervals

def choose_final_interval(textgrid_path: str, preferred_tier: str = "") -> Dict:
    """
    Choose the final non-empty interval.

    For your dissertation token-level variables, the best default is:
    MAS = syllable tier, because FINAL_SYLLABLE_DURATION should come from the final syllable.
    """
    tier_name = preferred_tier

    if not tier_name:
        tier_name = find_syllable_tier(textgrid_path)

    if not tier_name:
        tier_name = find_word_tier(textgrid_path)

    if not tier_name:
        tier_name = find_phone_tier(textgrid_path)

    if not tier_name:
        tier_names = get_tier_names(textgrid_path)
        tier_name = tier_names[0] if tier_names else ""

    if not tier_name:
        return {
            "tier_name": "",
            "start": None,
            "end": None,
            "midpoint": None,
            "label": "",
            "error": "No usable TextGrid tier found.",
        }

    intervals = get_non_empty_intervals(textgrid_path, tier_name)

    if not intervals:
        return {
            "tier_name": tier_name,
            "start": None,
            "end": None,
            "midpoint": None,
            "label": "",
            "error": "No non-empty interval found.",
        }

    final_interval = intervals[-1]

    start = final_interval["start"]
    end = final_interval["end"]

    return {
        "tier_name": tier_name,
        "start": start,
        "end": end,
        "midpoint": (start + end) / 2,
        "label": final_interval["label"],
        "error": "",
    }


# ============================================================
# Praat extraction helpers
# ============================================================

def extract_pitch_dataframe(
    sound: parselmouth.Sound,
    pitch_floor: float = 75.0,
    pitch_ceiling: float = 500.0,
) -> pd.DataFrame:
    """
    Extract pitch track from Praat as dataframe.
    """
    pitch = sound.to_pitch(
        time_step=0.01,
        pitch_floor=pitch_floor,
        pitch_ceiling=pitch_ceiling,
    )

    times = pitch.xs()
    frequencies = pitch.selected_array["frequency"]

    df = pd.DataFrame(
        {
            "time": times,
            "f0_hz": frequencies,
        }
    )

    df["f0_hz"] = df["f0_hz"].replace(0, np.nan)

    return df


def get_f0_nearest_voiced(pitch_df: pd.DataFrame, time_point: float) -> Tuple[Optional[float], Optional[float]]:
    """
    Return nearest voiced F0 and the actual time used.
    """
    if time_point is None or pitch_df.empty:
        return None, None

    voiced = pitch_df.dropna(subset=["f0_hz"]).copy()

    if voiced.empty:
        return None, None

    voiced["distance"] = (voiced["time"] - time_point).abs()
    row = voiced.sort_values("distance").iloc[0]

    return safe_float(row["f0_hz"]), safe_float(row["time"])


def get_pitch_region(pitch_df: pd.DataFrame, start: float, end: float) -> pd.DataFrame:
    if start is None or end is None:
        return pd.DataFrame(columns=pitch_df.columns)

    region = pitch_df[
        (pitch_df["time"] >= float(start))
        & (pitch_df["time"] <= float(end))
    ].copy()

    region = region.dropna(subset=["f0_hz"])

    return region


def extract_intensity_mean(
    sound: parselmouth.Sound,
    pitch_floor: float = 75.0,
) -> Optional[float]:
    try:
        intensity = call(sound, "To Intensity", pitch_floor, 0.0, "yes")
        return safe_float(call(intensity, "Get mean", 0, 0, "energy"))
    except Exception:
        return None


def calculate_plateau_duration_st(
    region_df: pd.DataFrame,
    reference_hz: float,
    threshold_st: float = 1.0,
) -> Optional[float]:
    """
    Plateau duration = total time in final region where F0 stays within threshold_st
    of the region's maximum F0.

    This operationalizes plateau as a high stable region near the local F0 peak.
    """
    if region_df.empty or reference_hz is None:
        return None

    df = region_df.copy()
    df["f0_st"] = df["f0_hz"].apply(lambda x: hz_to_st(x, reference_hz))
    df = df.dropna(subset=["f0_st"])

    if df.empty:
        return None

    max_st = df["f0_st"].max()
    plateau_df = df[df["f0_st"] >= max_st - threshold_st]

    if plateau_df.empty:
        return 0.0

    # Approximate duration by frame count × median step
    if len(df) >= 2:
        time_step = float(np.median(np.diff(df["time"])))
    else:
        time_step = 0.01

    return float(len(plateau_df) * time_step)


def classify_contour(
    start_st: Optional[float],
    mid_st: Optional[float],
    end_st: Optional[float],
    peak_st: Optional[float],
    threshold_st: float = 1.0,
) -> str:
    """
    Classify final pitch contour.

    Categories:
    - Rising
    - Falling
    - Plateau
    - Rise-Fall
    - Fall-Rise
    - Undetermined
    """
    values = [start_st, mid_st, end_st, peak_st]

    if any(v is None for v in values):
        return "Undetermined"

    overall_change = end_st - start_st

    # Peak clearly occurs above both start and end
    if peak_st - start_st >= threshold_st and peak_st - end_st >= threshold_st:
        return "Rise-Fall"

    # Valley-like fall-rise
    if start_st - mid_st >= threshold_st and end_st - mid_st >= threshold_st:
        return "Fall-Rise"

    if overall_change >= threshold_st:
        return "Rising"

    if overall_change <= -threshold_st:
        return "Falling"

    return "Plateau"


def extract_token_acoustic_variables(
    audio_path: str,
    textgrid_path: str,
    preferred_tier: str = "",
    pitch_floor: float = 75.0,
    pitch_ceiling: float = 500.0,
    plateau_threshold_st: float = 1.0,
) -> Dict:
    """
    Extract exactly the token-level variables in your dissertation spreadsheet:

    CONTOUR_CLASS
    F0_MEAN_ST
    F0_RANGE_ST
    FINAL_SLOPE_ST
    FINAL_SYLLABLE_DURATION
    TOTAL_DURATION
    INTENSITY_MEAN
    PLATEAU_DURATION
    ALIGNMENT_TIME
    """

    results = {
        "CONTOUR_CLASS": None,
        "F0_MEAN_ST": None,
        "F0_RANGE_ST": None,
        "FINAL_SLOPE_ST": None,
        "FINAL_SYLLABLE_DURATION": None,
        "TOTAL_DURATION": None,
        "INTENSITY_MEAN": None,
        "PLATEAU_DURATION": None,
        "ALIGNMENT_TIME": None,
        "PRAAT_STATUS": "not_started",
        "PRAAT_ERROR": "",
        "TEXTGRID_TIER_USED": "",
        "FINAL_INTERVAL_LABEL": "",
        "FINAL_INTERVAL_START": None,
        "FINAL_INTERVAL_END": None,
    }

    try:
        sound = parselmouth.Sound(audio_path)
        total_duration = safe_float(sound.get_total_duration())

        results["TOTAL_DURATION"] = total_duration
        results["INTENSITY_MEAN"] = extract_intensity_mean(sound, pitch_floor=pitch_floor)

        final_interval = choose_final_interval(textgrid_path, preferred_tier=preferred_tier)

        if final_interval.get("error"):
            results["PRAAT_STATUS"] = "failed"
            results["PRAAT_ERROR"] = final_interval.get("error")
            return results

        final_start = final_interval["start"]
        final_end = final_interval["end"]
        final_mid = final_interval["midpoint"]

        results["TEXTGRID_TIER_USED"] = final_interval["tier_name"]
        results["FINAL_INTERVAL_LABEL"] = final_interval["label"]
        results["FINAL_INTERVAL_START"] = final_start
        results["FINAL_INTERVAL_END"] = final_end

        if final_start is None or final_end is None:
            results["PRAAT_STATUS"] = "failed"
            results["PRAAT_ERROR"] = "Final interval boundaries missing."
            return results

        final_duration = final_end - final_start
        results["FINAL_SYLLABLE_DURATION"] = safe_float(final_duration)

        pitch_df = extract_pitch_dataframe(
            sound,
            pitch_floor=pitch_floor,
            pitch_ceiling=pitch_ceiling,
        )

        voiced_all = pitch_df.dropna(subset=["f0_hz"])

        if voiced_all.empty:
            results["PRAAT_STATUS"] = "failed"
            results["PRAAT_ERROR"] = "No voiced F0 values found."
            return results

        reference_hz = safe_float(voiced_all["f0_hz"].median())

        region_df = get_pitch_region(pitch_df, final_start, final_end)

        if region_df.empty:
            results["PRAAT_STATUS"] = "failed"
            results["PRAAT_ERROR"] = "No voiced F0 values in final interval."
            return results

        # Convert final interval F0 to semitones relative to speaker/file median F0
        region_df["f0_st"] = region_df["f0_hz"].apply(lambda x: hz_to_st(x, reference_hz))
        region_df = region_df.dropna(subset=["f0_st"])

        if region_df.empty:
            results["PRAAT_STATUS"] = "failed"
            results["PRAAT_ERROR"] = "Could not convert final interval F0 to semitones."
            return results

        f0_mean_st = safe_float(region_df["f0_st"].mean())
        f0_min_st = safe_float(region_df["f0_st"].min())
        f0_max_st = safe_float(region_df["f0_st"].max())

        results["F0_MEAN_ST"] = f0_mean_st

        if f0_min_st is not None and f0_max_st is not None:
            results["F0_RANGE_ST"] = safe_float(f0_max_st - f0_min_st)

        # F0 at start, midpoint, end
        f0_start_hz, actual_start_time = get_f0_nearest_voiced(pitch_df, final_start)
        f0_mid_hz, actual_mid_time = get_f0_nearest_voiced(pitch_df, final_mid)
        f0_end_hz, actual_end_time = get_f0_nearest_voiced(pitch_df, final_end)

        f0_start_st = hz_to_st(f0_start_hz, reference_hz)
        f0_mid_st = hz_to_st(f0_mid_hz, reference_hz)
        f0_end_st = hz_to_st(f0_end_hz, reference_hz)

        if f0_start_st is not None and f0_end_st is not None and final_duration > 0:
            results["FINAL_SLOPE_ST"] = safe_float((f0_end_st - f0_start_st) / final_duration)

        # Peak alignment
        peak_row = region_df.sort_values("f0_st", ascending=False).iloc[0]
        peak_time = safe_float(peak_row["time"])
        peak_st = safe_float(peak_row["f0_st"])

        # ALIGNMENT_TIME = peak time relative to final syllable onset
        # Example: 0.05 means peak occurs 50 ms after final syllable onset.
        if peak_time is not None:
            results["ALIGNMENT_TIME"] = safe_float(peak_time - final_start)

        results["PLATEAU_DURATION"] = calculate_plateau_duration_st(
            region_df,
            reference_hz=reference_hz,
            threshold_st=plateau_threshold_st,
        )

        results["CONTOUR_CLASS"] = classify_contour(
            start_st=f0_start_st,
            mid_st=f0_mid_st,
            end_st=f0_end_st,
            peak_st=peak_st,
            threshold_st=1.0,
        )

        results["PRAAT_STATUS"] = "completed"
        return results

    except Exception as e:
        results["PRAAT_STATUS"] = "failed"
        results["PRAAT_ERROR"] = str(e)
        return results


# ============================================================
# Excel processing
# ============================================================

def process_token_sheet(
    df: pd.DataFrame,
    audio_dir: str,
    textgrid_dir: str,
    preferred_tier: str = "",
    pitch_floor: float = 75.0,
    pitch_ceiling: float = 500.0,
) -> pd.DataFrame:
    """
    Process one Token_Level_Data sheet.
    """
    output_df = df.copy()

    # Add diagnostic columns if not already present
    diagnostic_columns = [
        "AUDIO_FILE_USED",
        "TEXTGRID_FILE_USED",
        "PRAAT_STATUS",
        "PRAAT_ERROR",
        "TEXTGRID_TIER_USED",
        "FINAL_INTERVAL_LABEL",
        "FINAL_INTERVAL_START",
        "FINAL_INTERVAL_END",
    ]

    for col in diagnostic_columns:
        if col not in output_df.columns:
            output_df[col] = None

    for idx, row in output_df.iterrows():
        token_id = str(row.get("TOKEN_ID", "") or "")
        speaker_id = str(row.get("SPEAKER_ID", "") or "")
        sentence_id = str(row.get("SENTENCE_ID", "") or "")

        if not speaker_id:
            output_df.at[idx, "PRAAT_STATUS"] = "skipped"
            output_df.at[idx, "PRAAT_ERROR"] = "Missing SPEAKER_ID."
            continue

        audio_path = find_matching_file(
            speaker_id=speaker_id,
            sentence_id=sentence_id,
            token_id=token_id,
            search_dir=audio_dir,
            extensions=AUDIO_EXTENSIONS,
        )

        textgrid_path = find_matching_file(
            speaker_id=speaker_id,
            sentence_id=sentence_id,
            token_id=token_id,
            search_dir=textgrid_dir,
            extensions=TEXTGRID_EXTENSIONS,
        )

        output_df.at[idx, "AUDIO_FILE_USED"] = audio_path
        output_df.at[idx, "TEXTGRID_FILE_USED"] = textgrid_path

        if not audio_path:
            output_df.at[idx, "PRAAT_STATUS"] = "failed"
            output_df.at[idx, "PRAAT_ERROR"] = "No matching audio file found."
            continue

        if not textgrid_path:
            output_df.at[idx, "PRAAT_STATUS"] = "failed"
            output_df.at[idx, "PRAAT_ERROR"] = "No matching TextGrid file found."
            continue

        measures = extract_token_acoustic_variables(
            audio_path=audio_path,
            textgrid_path=textgrid_path,
            preferred_tier=preferred_tier,
            pitch_floor=pitch_floor,
            pitch_ceiling=pitch_ceiling,
        )

        for key, value in measures.items():
            if key in output_df.columns:
                output_df.at[idx, key] = value
            else:
                output_df[key] = None
                output_df.at[idx, key] = value

    return output_df


def process_token_level_workbook(
    template_path: str,
    audio_dir: str,
    textgrid_dir: str,
    output_xlsx: str,
    output_csv: str,
    preferred_tier: str = "MAS",
    pitch_floor: float = 75.0,
    pitch_ceiling: float = 500.0,
):
    """
    Process all sheets whose names begin with Token_Level_Data.
    Keep all other sheets unchanged.
    """
    workbook = pd.read_excel(template_path, sheet_name=None)

    processed_sheets = {}
    combined_token_rows = []

    for sheet_name, df in workbook.items():
        if sheet_name.startswith("Token_Level_Data"):
            print(f"Processing token sheet: {sheet_name}")

            processed_df = process_token_sheet(
                df=df,
                audio_dir=audio_dir,
                textgrid_dir=textgrid_dir,
                preferred_tier=preferred_tier,
                pitch_floor=pitch_floor,
                pitch_ceiling=pitch_ceiling,
            )

            processed_sheets[sheet_name] = processed_df
            combined_token_rows.append(processed_df.assign(SOURCE_SHEET=sheet_name))
        else:
            processed_sheets[sheet_name] = df

    # Concatenate all token-level rows into one master dataframe
    if combined_token_rows:
        combined_df = pd.concat(combined_token_rows, ignore_index=True, sort=False)

        # Put key identifying columns first when available
        priority_columns = [
            "SOURCE_SHEET",
            "TOKEN_ID",
            "SPEAKER_ID",
            "SENTENCE_ID",
            "REGION",
            "AGE",
            "GENDER",
            "EDUCATION",
            "SENTENCE_TEXT",
            "CONTOUR_CLASS",
            "F0_MEAN_ST",
            "F0_RANGE_ST",
            "FINAL_SLOPE_ST",
            "FINAL_SYLLABLE_DURATION",
            "TOTAL_DURATION",
            "INTENSITY_MEAN",
            "PLATEAU_DURATION",
            "ALIGNMENT_TIME",
            "AUDIO_FILE_USED",
            "TEXTGRID_FILE_USED",
            "PRAAT_STATUS",
            "PRAAT_ERROR",
            "TEXTGRID_TIER_USED",
            "FINAL_INTERVAL_LABEL",
            "FINAL_INTERVAL_START",
            "FINAL_INTERVAL_END",
        ]

        existing_priority = [col for col in priority_columns if col in combined_df.columns]
        remaining_columns = [col for col in combined_df.columns if col not in existing_priority]
        combined_df = combined_df[existing_priority + remaining_columns]

    else:
        combined_df = pd.DataFrame()

    # Save Excel with all original sheets plus one concatenated master sheet
    with pd.ExcelWriter(output_xlsx, engine="openpyxl") as writer:
        for sheet_name, df in processed_sheets.items():
            df.to_excel(writer, sheet_name=sheet_name[:31], index=False)

        combined_df.to_excel(
            writer,
            sheet_name="CONCATENATED_TOKEN_DATA",
            index=False,
        )

    # Save combined CSV for modeling
    combined_df.to_csv(output_csv, index=False)

    # Also save a separate concatenated Excel workbook only containing the master table
    concatenated_xlsx = str(Path(output_xlsx).with_name("PFC_all_token_data_concatenated.xlsx"))
    concatenated_csv = str(Path(output_csv).with_name("PFC_all_token_data_concatenated.csv"))

    with pd.ExcelWriter(concatenated_xlsx, engine="openpyxl") as writer:
        combined_df.to_excel(
            writer,
            sheet_name="ALL_TOKEN_DATA",
            index=False,
        )

    combined_df.to_csv(concatenated_csv, index=False)

    print("\nCompleted.")
    print(f"Excel output with all sheets: {output_xlsx}")
    print(f"CSV output combined: {output_csv}")
    print(f"Concatenated Excel only: {concatenated_xlsx}")
    print(f"Concatenated CSV only: {concatenated_csv}")
    print(f"Total concatenated rows: {len(combined_df)}")
    print(f"Total variables/columns: {len(combined_df.columns)}")

    return combined_df


# ============================================================
# Command line
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="Extract dissertation token-level Praat variables into PFC Excel template."
    )

    parser.add_argument(
        "--template",
        required=True,
        help="Path to token-level Excel template.",
    )

    parser.add_argument(
        "--audio_dir",
        required=True,
        help="Folder containing audio files.",
    )

    parser.add_argument(
        "--textgrid_dir",
        required=True,
        help="Folder containing TextGrid files.",
    )

    parser.add_argument(
        "--output_xlsx",
        default="outputs/PFC_token_level_praat_filled.xlsx",
        help="Output filled Excel workbook.",
    )

    parser.add_argument(
        "--output_csv",
        default="outputs/PFC_token_level_praat_filled.csv",
        help="Output combined token-level CSV.",
    )

    parser.add_argument(
        "--tier",
        default="MAS",
        help="TextGrid tier for final syllable extraction. Recommended: MAS.",
    )

    parser.add_argument(
        "--pitch_floor",
        type=float,
        default=75.0,
        help="Praat pitch floor in Hz.",
    )

    parser.add_argument(
        "--pitch_ceiling",
        type=float,
        default=500.0,
        help="Praat pitch ceiling in Hz.",
    )

    args = parser.parse_args()

    os.makedirs(Path(args.output_xlsx).parent, exist_ok=True)
    os.makedirs(Path(args.output_csv).parent, exist_ok=True)

    process_token_level_workbook(
        template_path=args.template,
        audio_dir=args.audio_dir,
        textgrid_dir=args.textgrid_dir,
        output_xlsx=args.output_xlsx,
        output_csv=args.output_csv,
        preferred_tier=args.tier,
        pitch_floor=args.pitch_floor,
        pitch_ceiling=args.pitch_ceiling,
    )


if __name__ == "__main__":
    main()
