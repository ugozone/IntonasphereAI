"""
IntonaSphere AI Research Batch Extractor

This module connects the IntonaSphere AI Streamlit interface to the
existing token-level Praat/TextGrid extraction workflow.
"""

from pathlib import Path
import pandas as pd

from token_level_praat_extractor import process_token_level_workbook


def validate_existing_path(path_value: str, label: str) -> Path:
    """
    Validate that a file or folder exists.
    """
    path = Path(path_value).expanduser()

    if not path.exists():
        raise FileNotFoundError(f"{label} not found: {path}")

    return path


def run_pfc_token_level_extraction(
    template_path: str,
    audio_dir: str,
    textgrid_dir: str,
    output_xlsx: str,
    output_csv: str,
    preferred_tier: str = "MAS",
    pitch_floor: float = 75.0,
    pitch_ceiling: float = 500.0,
) -> pd.DataFrame:
    """
    Run token-level acoustic and prosodic extraction for PFC-style data.

    This function processes all Excel sheets whose names begin with
    Token_Level_Data and extracts research-ready acoustic variables,
    including F0, final slope, intensity, duration, plateau duration,
    contour class, final interval information, and diagnostic columns.

    Parameters
    ----------
    template_path:
        Excel workbook containing Token_Level_Data sheets.
    audio_dir:
        Folder containing matching audio files.
    textgrid_dir:
        Folder containing matching Praat TextGrid files.
    output_xlsx:
        Full Excel output path.
    output_csv:
        Full CSV output path.
    preferred_tier:
        Preferred TextGrid tier for final interval extraction. Default is MAS.
    pitch_floor:
        Praat pitch floor. Default is 75 Hz.
    pitch_ceiling:
        Praat pitch ceiling. Default is 500 Hz.

    Returns
    -------
    pandas.DataFrame
        Concatenated token-level acoustic dataset.
    """

    template_path = validate_existing_path(template_path, "Template workbook")
    audio_dir = validate_existing_path(audio_dir, "Audio folder")
    textgrid_dir = validate_existing_path(textgrid_dir, "TextGrid folder")

    output_xlsx = Path(output_xlsx).expanduser()
    output_csv = Path(output_csv).expanduser()

    output_xlsx.parent.mkdir(parents=True, exist_ok=True)
    output_csv.parent.mkdir(parents=True, exist_ok=True)

    df = process_token_level_workbook(
        template_path=str(template_path),
        audio_dir=str(audio_dir),
        textgrid_dir=str(textgrid_dir),
        output_xlsx=str(output_xlsx),
        output_csv=str(output_csv),
        preferred_tier=preferred_tier,
        pitch_floor=float(pitch_floor),
        pitch_ceiling=float(pitch_ceiling),
    )

    if not isinstance(df, pd.DataFrame):
        if output_csv.exists():
            df = pd.read_csv(output_csv)
        else:
            raise RuntimeError("Extraction finished, but no dataframe or CSV output was found.")

    return df


def run_pfc_word_and_syllable_extraction(
    template_path: str,
    audio_dir: str,
    textgrid_dir: str,
    output_xlsx: str,
    output_csv: str,
    pitch_floor: float = 75.0,
    pitch_ceiling: float = 500.0,
) -> pd.DataFrame:
    """
    Run final-word extraction from ORT-MAU and final-syllable extraction from MAS,
    then merge both into one row per token.
    """

    output_xlsx = Path(output_xlsx).expanduser()
    output_csv = Path(output_csv).expanduser()

    word_csv = output_csv.with_name(output_csv.stem + "_word_temp.csv")
    word_xlsx = output_xlsx.with_name(output_xlsx.stem + "_word_temp.xlsx")

    syll_csv = output_csv.with_name(output_csv.stem + "_syllable_temp.csv")
    syll_xlsx = output_xlsx.with_name(output_xlsx.stem + "_syllable_temp.xlsx")

    word_df = run_pfc_token_level_extraction(
        template_path=template_path,
        audio_dir=audio_dir,
        textgrid_dir=textgrid_dir,
        output_xlsx=str(word_xlsx),
        output_csv=str(word_csv),
        preferred_tier="ORT-MAU",
        pitch_floor=pitch_floor,
        pitch_ceiling=pitch_ceiling,
    )

    syllable_df = run_pfc_token_level_extraction(
        template_path=template_path,
        audio_dir=audio_dir,
        textgrid_dir=textgrid_dir,
        output_xlsx=str(syll_xlsx),
        output_csv=str(syll_csv),
        preferred_tier="MAS",
        pitch_floor=pitch_floor,
        pitch_ceiling=pitch_ceiling,
    )

    merge_keys = [
        "SOURCE_SHEET",
        "TOKEN_ID",
        "SPEAKER_ID",
        "SENTENCE_ID",
    ]

    merge_keys = [
        col for col in merge_keys
        if col in word_df.columns and col in syllable_df.columns
    ]

    word_cols = {
        "PRAAT_STATUS": "WORD_PRAAT_STATUS",
        "PRAAT_ERROR": "WORD_PRAAT_ERROR",
        "TEXTGRID_TIER_USED": "FINAL_WORD_TIER",
        "FINAL_INTERVAL_LABEL": "FINAL_WORD_LABEL",
        "FINAL_INTERVAL_START": "FINAL_WORD_START",
        "FINAL_INTERVAL_END": "FINAL_WORD_END",
        "CONTOUR_CLASS": "FINAL_WORD_CONTOUR_CLASS",
        "F0_MIN_HZ": "FINAL_WORD_F0_MIN_HZ",
        "F0_MAX_HZ": "FINAL_WORD_F0_MAX_HZ",
        "F0_MEAN_HZ": "FINAL_WORD_F0_MEAN_HZ",
        "F0_RANGE_HZ": "FINAL_WORD_F0_RANGE_HZ",
        "F0_MEAN_ST": "FINAL_WORD_F0_MEAN_ST",
        "F0_RANGE_ST": "FINAL_WORD_F0_RANGE_ST",
        "FINAL_SLOPE_ST": "FINAL_WORD_SLOPE_ST",
        "FINAL_SYLLABLE_DURATION": "FINAL_WORD_DURATION",
        "INTENSITY_MEAN": "FINAL_WORD_INTENSITY_MEAN",
        "PLATEAU_DURATION": "FINAL_WORD_PLATEAU_DURATION",
    }

    syllable_cols = {
        "PRAAT_STATUS": "SYLLABLE_PRAAT_STATUS",
        "PRAAT_ERROR": "SYLLABLE_PRAAT_ERROR",
        "TEXTGRID_TIER_USED": "FINAL_SYLLABLE_TIER",
        "FINAL_INTERVAL_LABEL": "FINAL_SYLLABLE_LABEL",
        "FINAL_INTERVAL_START": "FINAL_SYLLABLE_START",
        "FINAL_INTERVAL_END": "FINAL_SYLLABLE_END",
        "CONTOUR_CLASS": "FINAL_SYLLABLE_CONTOUR_CLASS",
        "F0_MIN_HZ": "FINAL_SYLLABLE_F0_MIN_HZ",
        "F0_MAX_HZ": "FINAL_SYLLABLE_F0_MAX_HZ",
        "F0_MEAN_HZ": "FINAL_SYLLABLE_F0_MEAN_HZ",
        "F0_RANGE_HZ": "FINAL_SYLLABLE_F0_RANGE_HZ",
        "F0_MEAN_ST": "FINAL_SYLLABLE_F0_MEAN_ST",
        "F0_RANGE_ST": "FINAL_SYLLABLE_F0_RANGE_ST",
        "FINAL_SLOPE_ST": "FINAL_SYLLABLE_SLOPE_ST",
        "FINAL_SYLLABLE_DURATION": "FINAL_SYLLABLE_DURATION",
        "INTENSITY_MEAN": "FINAL_SYLLABLE_INTENSITY_MEAN",
        "PLATEAU_DURATION": "FINAL_SYLLABLE_PLATEAU_DURATION",
    }

    word_keep = merge_keys + [col for col in word_cols if col in word_df.columns]
    syllable_keep = merge_keys + [col for col in syllable_cols if col in syllable_df.columns]

    word_part = word_df[word_keep].rename(columns=word_cols)
    syllable_part = syllable_df[syllable_keep].rename(columns=syllable_cols)

    base_drop = list(word_cols.keys())
    base_df = word_df.drop(columns=[col for col in base_drop if col in word_df.columns])

    combined = base_df.merge(
        word_part,
        on=merge_keys,
        how="left",
    ).merge(
        syllable_part,
        on=merge_keys,
        how="left",
    )

    priority_cols = [
        "SOURCE_SHEET",
        "TOKEN_ID",
        "SPEAKER_ID",
        "SENTENCE_ID",
        "QUESTION_TYPE",
        "SENTENCE_TEXT",

        "REGION",
        "REGION_GROUP",
        "CONTINENT",
        "SITE_ID",
        "COUNTRY",
        "AGE",
        "AGE_GROUP",
        "SEX",
        "GENDER_LABEL",

        "FINAL_WORD_LABEL",
        "FINAL_WORD_START",
        "FINAL_WORD_END",
        "FINAL_WORD_TIER",
        "FINAL_WORD_CONTOUR_CLASS",
        "FINAL_WORD_F0_MIN_HZ",
        "FINAL_WORD_F0_MAX_HZ",
        "FINAL_WORD_F0_MEAN_HZ",
        "FINAL_WORD_F0_RANGE_HZ",
        "FINAL_WORD_F0_MEAN_ST",
        "FINAL_WORD_F0_RANGE_ST",
        "FINAL_WORD_SLOPE_ST",
        "FINAL_WORD_DURATION",
        "FINAL_WORD_INTENSITY_MEAN",
        "WORD_PRAAT_STATUS",
        "WORD_PRAAT_ERROR",

        "FINAL_SYLLABLE_LABEL",
        "FINAL_SYLLABLE_START",
        "FINAL_SYLLABLE_END",
        "FINAL_SYLLABLE_TIER",
        "FINAL_SYLLABLE_CONTOUR_CLASS",
        "FINAL_SYLLABLE_F0_MIN_HZ",
        "FINAL_SYLLABLE_F0_MAX_HZ",
        "FINAL_SYLLABLE_F0_MEAN_HZ",
        "FINAL_SYLLABLE_F0_RANGE_HZ",
        "FINAL_SYLLABLE_F0_MEAN_ST",
        "FINAL_SYLLABLE_F0_RANGE_ST",
        "FINAL_SYLLABLE_SLOPE_ST",
        "FINAL_SYLLABLE_DURATION",
        "FINAL_SYLLABLE_INTENSITY_MEAN",
        "SYLLABLE_PRAAT_STATUS",
        "SYLLABLE_PRAAT_ERROR",

        "AUDIO_FILE_USED",
        "TEXTGRID_FILE_USED",
    ]

    existing_priority = [col for col in priority_cols if col in combined.columns]
    remaining_cols = [col for col in combined.columns if col not in existing_priority]
    combined = combined[existing_priority + remaining_cols]

    output_csv.parent.mkdir(parents=True, exist_ok=True)
    output_xlsx.parent.mkdir(parents=True, exist_ok=True)

    combined.to_csv(output_csv, index=False)

    with pd.ExcelWriter(output_xlsx, engine="openpyxl") as writer:
        combined.to_excel(writer, sheet_name="WORD_AND_SYLLABLE", index=False)

    return combined
