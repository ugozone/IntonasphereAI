import argparse
import os
import re
from pathlib import Path

import pandas as pd

from token_level_praat_extractor import extract_token_acoustic_variables


AUDIO_EXTENSIONS = [".wav", ".mp3", ".m4a", ".flac", ".ogg", ".aac", ".mp4", ".mov", ".webm"]
TEXTGRID_EXTENSIONS = [".TextGrid", ".textgrid"]


def clean_file_id(path: Path) -> str:
    """
    Return filename stem as ID, removing common duplicate/copy markers.
    """
    stem = path.stem.strip()

    # Remove " copy" from names like ciaak1tw1 copy.TextGrid
    stem = re.sub(r"\s+copy$", "", stem, flags=re.IGNORECASE)

    return stem


def extract_speaker_base(file_id: str) -> str:
    """
    Extract speaker base from token/file ID.

    Example:
    64aab1tw1 -> 64aab1tw
    64aab1tw2 -> 64aab1tw
    maabh1tw3 -> maabh1tw

    This keeps the speaker identity separate from the sentence/token number.
    """
    match = re.match(r"^(.+?)([1-4])$", file_id)

    if match:
        return match.group(1)

    return file_id


def extract_sentence_number(file_id: str):
    """
    Extract final sentence/token number if filename ends in 1, 2, 3, or 4.
    """
    match = re.match(r"^(.+?)([1-4])$", file_id)

    if match:
        return match.group(2)

    return ""


def collect_audio_textgrid_pairs(folder_path: str) -> pd.DataFrame:
    """
    Scan folder and build one row per unique file ID.
    Matches audio and TextGrid by filename stem.
    """
    folder = Path(folder_path)

    if not folder.exists():
        raise FileNotFoundError(f"Folder does not exist: {folder_path}")

    audio_map = {}
    textgrid_map = {}

    for file in folder.iterdir():
        if not file.is_file():
            continue

        if file.name.startswith("."):
            continue

        suffix = file.suffix

        file_id = clean_file_id(file)

        if suffix.lower() in [ext.lower() for ext in AUDIO_EXTENSIONS]:
            audio_map[file_id] = str(file)

        if suffix in TEXTGRID_EXTENSIONS or suffix.lower() == ".textgrid":
            textgrid_map[file_id] = str(file)

    all_ids = sorted(set(audio_map.keys()) | set(textgrid_map.keys()))

    rows = []

    for file_id in all_ids:
        audio_file = audio_map.get(file_id, "")
        textgrid_file = textgrid_map.get(file_id, "")

        rows.append(
            {
                "file_id": file_id,
                "speaker_id": extract_speaker_base(file_id),
                "sentence_number": extract_sentence_number(file_id),
                "audio_file": audio_file,
                "textgrid_file": textgrid_file,
                "audio_exists": bool(audio_file),
                "textgrid_exists": bool(textgrid_file),
            }
        )

    return pd.DataFrame(rows)


def analyze_folder_pairs(
    folder_path: str,
    output_csv: str,
    output_excel: str,
    tier: str = "MAS",
    pitch_floor: float = 75.0,
    pitch_ceiling: float = 500.0,
) -> pd.DataFrame:
    """
    Build one master dataframe for all IDs in the folder.
    """
    pair_df = collect_audio_textgrid_pairs(folder_path)

    result_rows = []

    total = len(pair_df)

    print(f"Found {total} unique IDs in folder.")
    print("Starting extraction...\n")

    for index, row in pair_df.iterrows():
        file_id = row["file_id"]
        speaker_id = row["speaker_id"]
        audio_file = row["audio_file"]
        textgrid_file = row["textgrid_file"]

        print(f"[{index + 1}/{total}] Processing {file_id}")

        base_row = row.to_dict()

        if not audio_file:
            base_row.update(
                {
                    "PRAAT_STATUS": "failed",
                    "PRAAT_ERROR": "No matching audio file found.",
                    "CONTOUR_CLASS": None,
                    "F0_MEAN_ST": None,
                    "F0_RANGE_ST": None,
                    "FINAL_SLOPE_ST": None,
                    "FINAL_SYLLABLE_DURATION": None,
                    "TOTAL_DURATION": None,
                    "INTENSITY_MEAN": None,
                    "PLATEAU_DURATION": None,
                    "ALIGNMENT_TIME": None,
                }
            )
            result_rows.append(base_row)
            continue

        if not textgrid_file:
            base_row.update(
                {
                    "PRAAT_STATUS": "audio_only_no_textgrid",
                    "PRAAT_ERROR": "Audio exists, but no matching TextGrid found. TextGrid-based variables not extracted.",
                    "CONTOUR_CLASS": None,
                    "F0_MEAN_ST": None,
                    "F0_RANGE_ST": None,
                    "FINAL_SLOPE_ST": None,
                    "FINAL_SYLLABLE_DURATION": None,
                    "TOTAL_DURATION": None,
                    "INTENSITY_MEAN": None,
                    "PLATEAU_DURATION": None,
                    "ALIGNMENT_TIME": None,
                }
            )
            result_rows.append(base_row)
            continue

        try:
            measures = extract_token_acoustic_variables(
                audio_path=audio_file,
                textgrid_path=textgrid_file,
                preferred_tier=tier,
                pitch_floor=pitch_floor,
                pitch_ceiling=pitch_ceiling,
            )

            base_row.update(measures)
            result_rows.append(base_row)

        except Exception as e:
            base_row.update(
                {
                    "PRAAT_STATUS": "failed",
                    "PRAAT_ERROR": str(e),
                    "CONTOUR_CLASS": None,
                    "F0_MEAN_ST": None,
                    "F0_RANGE_ST": None,
                    "FINAL_SLOPE_ST": None,
                    "FINAL_SYLLABLE_DURATION": None,
                    "TOTAL_DURATION": None,
                    "INTENSITY_MEAN": None,
                    "PLATEAU_DURATION": None,
                    "ALIGNMENT_TIME": None,
                }
            )
            result_rows.append(base_row)

    master_df = pd.DataFrame(result_rows)

    priority_cols = [
        "file_id",
        "speaker_id",
        "sentence_number",
        "audio_exists",
        "textgrid_exists",
        "audio_file",
        "textgrid_file",
        "CONTOUR_CLASS",
        "F0_MEAN_ST",
        "F0_RANGE_ST",
        "FINAL_SLOPE_ST",
        "FINAL_SYLLABLE_DURATION",
        "TOTAL_DURATION",
        "INTENSITY_MEAN",
        "PLATEAU_DURATION",
        "ALIGNMENT_TIME",
        "PRAAT_STATUS",
        "PRAAT_ERROR",
        "TEXTGRID_TIER_USED",
        "FINAL_INTERVAL_LABEL",
        "FINAL_INTERVAL_START",
        "FINAL_INTERVAL_END",
    ]

    existing_priority = [col for col in priority_cols if col in master_df.columns]
    remaining_cols = [col for col in master_df.columns if col not in existing_priority]
    master_df = master_df[existing_priority + remaining_cols]

    output_csv_path = Path(output_csv)
    output_excel_path = Path(output_excel)

    output_csv_path.parent.mkdir(parents=True, exist_ok=True)
    output_excel_path.parent.mkdir(parents=True, exist_ok=True)

    master_df.to_csv(output_csv_path, index=False)

    with pd.ExcelWriter(output_excel_path, engine="openpyxl") as writer:
        master_df.to_excel(writer, sheet_name="PFC_MASTER_DATAFRAME", index=False)

        summary_df = pd.DataFrame(
            [
                {
                    "total_ids": len(master_df),
                    "audio_exists_count": int(master_df["audio_exists"].sum()),
                    "textgrid_exists_count": int(master_df["textgrid_exists"].sum()),
                    "completed_count": int((master_df["PRAAT_STATUS"] == "completed").sum()),
                    "audio_only_no_textgrid_count": int((master_df["PRAAT_STATUS"] == "audio_only_no_textgrid").sum()),
                    "failed_count": int((master_df["PRAAT_STATUS"] == "failed").sum()),
                }
            ]
        )

        summary_df.to_excel(writer, sheet_name="SUMMARY", index=False)

    print("\nCompleted.")
    print(f"Master CSV: {output_csv_path}")
    print(f"Master Excel: {output_excel_path}")
    print(f"Total rows/IDs: {len(master_df)}")

    print("\nStatus counts:")
    print(master_df["PRAAT_STATUS"].value_counts(dropna=False))

    return master_df


def main():
    parser = argparse.ArgumentParser(
        description="Build one master dataframe from all PFC audio/TextGrid IDs in a folder."
    )

    parser.add_argument(
        "--folder",
        required=True,
        help="Folder containing .wav and .TextGrid files.",
    )

    parser.add_argument(
        "--output_csv",
        default="outputs/PFC_folder_master_dataframe.csv",
        help="Output CSV file.",
    )

    parser.add_argument(
        "--output_excel",
        default="outputs/PFC_folder_master_dataframe.xlsx",
        help="Output Excel file.",
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

    analyze_folder_pairs(
        folder_path=args.folder,
        output_csv=args.output_csv,
        output_excel=args.output_excel,
        tier=args.tier,
        pitch_floor=args.pitch_floor,
        pitch_ceiling=args.pitch_ceiling,
    )


if __name__ == "__main__":
    main()
