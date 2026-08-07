import os
import re
from praatio import textgrid


def get_file_stem(file_name_or_path: str) -> str:
    """
    Return filename without extension.
    """
    base = os.path.basename(file_name_or_path)
    return os.path.splitext(base)[0]


def normalize_stem(stem: str) -> str:
    """
    Normalize filename stem for matching audio and TextGrid files.

    Also removes the random 8-character suffix added by safe_filename().

    Example:
    maabh1tw1_a1b2c3d4.wav
    maabh1tw1_e5f6a7b8.TextGrid

    both become:
    maabh1tw1
    """
    clean_stem = stem.strip().lower()
    clean_stem = re.sub(r"_[a-f0-9]{8}$", "", clean_stem)
    return clean_stem


def match_audio_textgrid_pairs(audio_paths: list, textgrid_paths: list) -> list:
    """
    Match audio files and TextGrid files by normalized filename stem.
    """
    audio_map = {
        normalize_stem(get_file_stem(path)): path
        for path in audio_paths
    }

    textgrid_map = {
        normalize_stem(get_file_stem(path)): path
        for path in textgrid_paths
    }

    matched_pairs = []

    for stem, audio_path in audio_map.items():
        if stem in textgrid_map:
            matched_pairs.append(
                {
                    "stem": stem,
                    "audio_path": audio_path,
                    "textgrid_path": textgrid_map[stem],
                }
            )

    return matched_pairs


def load_textgrid(textgrid_path: str):
    """
    Load a TextGrid using praatio.
    """
    return textgrid.openTextgrid(textgrid_path, includeEmptyIntervals=True)


def get_tier_names(textgrid_path: str) -> list:
    """
    Return all tier names in a TextGrid.
    """
    tg = load_textgrid(textgrid_path)
    return tg.tierNames


def summarize_textgrid(textgrid_path: str) -> dict:
    """
    Return a quick summary of the TextGrid.
    """
    tg = load_textgrid(textgrid_path)

    return {
        "textgrid_file": os.path.basename(textgrid_path),
        "tier_names": ", ".join(tg.tierNames),
        "number_of_tiers": len(tg.tierNames),
    }


def find_tier_by_candidates(textgrid_path: str, candidates: list) -> str:
    """
    Find a tier name by matching likely candidate names.
    """
    tier_names = get_tier_names(textgrid_path)
    tier_names_lower = {name.lower(): name for name in tier_names}

    for candidate in candidates:
        if candidate.lower() in tier_names_lower:
            return tier_names_lower[candidate.lower()]

    return ""


def find_word_tier(textgrid_path: str) -> str:
    """
    Find likely word/orthographic tier.
    """
    return find_tier_by_candidates(
        textgrid_path,
        [
            "ORT-MAU",
            "ort-mau",
            "ORT",
            "ort",
            "word",
            "words",
            "mots",
        ],
    )


def find_syllable_tier(textgrid_path: str) -> str:
    """
    Find likely syllable tier.
    """
    return find_tier_by_candidates(
        textgrid_path,
        [
            "MAS",
            "mas",
            "syllable",
            "syllables",
            "syll",
            "syllabe",
            "syllabes",
        ],
    )


def find_phone_tier(textgrid_path: str) -> str:
    """
    Find likely phone/sound tier.
    """
    return find_tier_by_candidates(
        textgrid_path,
        [
            "MAU",
            "mau",
            "phone",
            "phones",
            "phoneme",
            "phonemes",
            "segment",
            "segments",
        ],
    )


def find_transcription_tier(textgrid_path: str) -> str:
    """
    Find likely full-transcription tier.
    """
    return find_tier_by_candidates(
        textgrid_path,
        [
            "TRN",
            "trn",
            "transcription",
            "sentence",
            "phrase",
        ],
    )


def find_best_tier_name(textgrid_path: str, preferred_tiers=None) -> str:
    """
    Find best available tier for final interval extraction.

    Priority:
    - syllable tier
    - word tier
    - phone tier
    - first available interval tier
    """
    if preferred_tiers is None:
        preferred_tiers = [
            "MAS",
            "syllable",
            "syllables",
            "ORT-MAU",
            "word",
            "words",
            "MAU",
            "phones",
            "phone",
        ]

    tier_names = get_tier_names(textgrid_path)
    tier_names_lower = {name.lower(): name for name in tier_names}

    for preferred in preferred_tiers:
        if preferred.lower() in tier_names_lower:
            return tier_names_lower[preferred.lower()]

    tg = load_textgrid(textgrid_path)

    for tier_name in tg.tierNames:
        tier = tg.getTier(tier_name)
        if hasattr(tier, "entries"):
            return tier_name

    return ""


def get_non_empty_intervals(textgrid_path: str, tier_name: str) -> list:
    """
    Extract non-empty intervals from a TextGrid tier.

    Returns:
    [
        {"start": float, "end": float, "label": str}
    ]
    """
    tg = load_textgrid(textgrid_path)
    tier = tg.getTier(tier_name)

    intervals = []

    for entry in tier.entries:
        start = float(entry.start)
        end = float(entry.end)
        label = str(entry.label).strip()

        if label:
            intervals.append(
                {
                    "start": start,
                    "end": end,
                    "label": label,
                }
            )

    return intervals


def get_final_interval_from_textgrid(textgrid_path: str, tier_name: str = "") -> dict:
    """
    Get the final non-empty interval from a selected tier.
    """
    if not tier_name:
        tier_name = find_best_tier_name(textgrid_path)

    if not tier_name:
        return {
            "tier_name": "",
            "start": None,
            "midpoint": None,
            "end": None,
            "label": "",
            "error": "No usable tier found.",
        }

    intervals = get_non_empty_intervals(textgrid_path, tier_name)

    if not intervals:
        return {
            "tier_name": tier_name,
            "start": None,
            "midpoint": None,
            "end": None,
            "label": "",
            "error": "No non-empty intervals found.",
        }

    final_interval = intervals[-1]
    start = final_interval["start"]
    end = final_interval["end"]
    midpoint = (start + end) / 2

    return {
        "tier_name": tier_name,
        "start": start,
        "midpoint": midpoint,
        "end": end,
        "label": final_interval["label"],
        "error": "",
    }


def get_intervals_in_time_window(
    textgrid_path: str,
    start_time: float,
    end_time: float,
    tier_name: str = "",
) -> list:
    """
    Get all non-empty intervals from a TextGrid tier that overlap a time window.
    """
    if start_time is None or end_time is None:
        return []

    if not tier_name:
        tier_name = find_best_tier_name(textgrid_path)

    if not tier_name:
        return []

    intervals = get_non_empty_intervals(textgrid_path, tier_name)

    selected = []

    for interval in intervals:
        interval_start = interval["start"]
        interval_end = interval["end"]

        if interval_end >= start_time and interval_start <= end_time:
            selected.append(interval)

    return selected


def get_interval_at_time(
    textgrid_path: str,
    time_point: float,
    tier_name: str = "",
) -> dict:
    """
    Find the interval in a TextGrid tier that contains a given time point.

    Useful for identifying which word/syllable/phone carries the highest F0.
    """
    if time_point is None:
        return {
            "tier_name": tier_name,
            "start": None,
            "end": None,
            "midpoint": None,
            "label": "",
            "error": "No time point provided.",
        }

    if not tier_name:
        tier_name = find_best_tier_name(textgrid_path)

    if not tier_name:
        return {
            "tier_name": "",
            "start": None,
            "end": None,
            "midpoint": None,
            "label": "",
            "error": "No usable tier found.",
        }

    intervals = get_non_empty_intervals(textgrid_path, tier_name)

    for interval in intervals:
        start = interval["start"]
        end = interval["end"]

        if start <= time_point <= end:
            return {
                "tier_name": tier_name,
                "start": start,
                "end": end,
                "midpoint": (start + end) / 2,
                "label": interval["label"],
                "error": "",
            }

    return {
        "tier_name": tier_name,
        "start": None,
        "end": None,
        "midpoint": None,
        "label": "",
        "error": "No interval found at this time point.",
    }


def join_interval_labels(intervals: list) -> str:
    """
    Join interval labels into a readable string.
    """
    labels = []

    for interval in intervals:
        label = str(interval.get("label", "")).strip()
        if label:
            labels.append(label)

    return " ".join(labels)


def intervals_to_compact_string(intervals: list) -> str:
    """
    Return interval labels with timing for clarity.
    """
    parts = []

    for interval in intervals:
        label = str(interval.get("label", "")).strip()
        start = interval.get("start")
        end = interval.get("end")

        if label and start is not None and end is not None:
            parts.append(f"{label} [{start:.3f}-{end:.3f}]")

    return " | ".join(parts)


def build_region_material(
    textgrid_path: str,
    region_name: str,
    start_time: float,
    end_time: float,
    word_tier: str,
    syllable_tier: str,
    phone_tier: str,
) -> dict:
    """
    Build word/syllable/phone material for a prosodic region.
    """
    word_intervals = get_intervals_in_time_window(
        textgrid_path,
        start_time,
        end_time,
        word_tier,
    )

    syllable_intervals = get_intervals_in_time_window(
        textgrid_path,
        start_time,
        end_time,
        syllable_tier,
    )

    phone_intervals = get_intervals_in_time_window(
        textgrid_path,
        start_time,
        end_time,
        phone_tier,
    )

    return {
        f"{region_name}_start": start_time,
        f"{region_name}_end": end_time,

        f"{region_name}_word_labels": join_interval_labels(word_intervals),
        f"{region_name}_syllable_labels": join_interval_labels(syllable_intervals),
        f"{region_name}_phone_labels": join_interval_labels(phone_intervals),

        f"{region_name}_word_intervals": intervals_to_compact_string(word_intervals),
        f"{region_name}_syllable_intervals": intervals_to_compact_string(syllable_intervals),
        f"{region_name}_phone_intervals": intervals_to_compact_string(phone_intervals),
    }


def get_phonetic_portions_for_ap_ip_final(
    textgrid_path: str,
    duration: float,
    final_syllable_window: float = 0.30,
    ap_window: float = 0.75,
    ip_window: float = 1.20,
    phonetic_tier_name: str = "",
    syllable_tier_name: str = "",
    word_tier_name: str = "",
) -> dict:
    """
    Extract word, syllable, and phone portions corresponding to:
    - final syllable-like region
    - AP-final region
    - IP-final region

    Preferred tiers:
    - ORT-MAU for words
    - MAS for syllables
    - MAU for phones/sounds
    """
    if duration is None:
        return {
            "ap_ip_phonetic_error": "Duration is missing.",
        }

    word_tier = word_tier_name or find_word_tier(textgrid_path)
    syllable_tier = syllable_tier_name or find_syllable_tier(textgrid_path)
    phone_tier = phonetic_tier_name or find_phone_tier(textgrid_path)

    if not word_tier:
        word_tier = find_best_tier_name(textgrid_path)

    if not syllable_tier:
        syllable_tier = find_best_tier_name(textgrid_path)

    if not phone_tier:
        phone_tier = find_best_tier_name(textgrid_path)

    final_syllable_start = max(0, duration - final_syllable_window)
    final_syllable_end = duration

    ap_start = max(0, duration - ap_window)
    ap_end = duration

    ip_start = max(0, duration - ip_window)
    ip_end = duration

    results = {
        "word_tier_used_for_ap_ip": word_tier,
        "syllable_tier_used_for_ap_ip": syllable_tier,
        "phonetic_tier_used_for_ap_ip": phone_tier,
    }

    results.update(
        build_region_material(
            textgrid_path,
            "final_syllable_region",
            final_syllable_start,
            final_syllable_end,
            word_tier,
            syllable_tier,
            phone_tier,
        )
    )

    results.update(
        build_region_material(
            textgrid_path,
            "ap_region",
            ap_start,
            ap_end,
            word_tier,
            syllable_tier,
            phone_tier,
        )
    )

    results.update(
        build_region_material(
            textgrid_path,
            "ip_region",
            ip_start,
            ip_end,
            word_tier,
            syllable_tier,
            phone_tier,
        )
    )

    return results


def get_prominence_material_at_time(
    textgrid_path: str,
    peak_time: float,
) -> dict:
    """
    Identify the word, syllable, and phone/sound corresponding to the F0 peak.

    This connects:
    F0 peak → word → syllable → phone/sound
    """
    word_tier = find_word_tier(textgrid_path)
    syllable_tier = find_syllable_tier(textgrid_path)
    phone_tier = find_phone_tier(textgrid_path)

    if not word_tier:
        word_tier = find_best_tier_name(textgrid_path)

    if not syllable_tier:
        syllable_tier = find_best_tier_name(textgrid_path)

    if not phone_tier:
        phone_tier = find_best_tier_name(textgrid_path)

    word_interval = get_interval_at_time(textgrid_path, peak_time, word_tier)
    syllable_interval = get_interval_at_time(textgrid_path, peak_time, syllable_tier)
    phone_interval = get_interval_at_time(textgrid_path, peak_time, phone_tier)

    word_label = word_interval.get("label", "")
    syllable_label = syllable_interval.get("label", "")
    phone_label = phone_interval.get("label", "")

    combined_prominence_transcription = " | ".join(
        [x for x in [word_label, syllable_label, phone_label] if x]
    )

    return {
        "prominence_word_tier": word_tier,
        "prominence_syllable_tier": syllable_tier,
        "prominence_phone_tier": phone_tier,

        "prominence_word_label": word_label,
        "prominence_word_start": word_interval.get("start"),
        "prominence_word_end": word_interval.get("end"),

        "prominence_syllable_label": syllable_label,
        "prominence_syllable_start": syllable_interval.get("start"),
        "prominence_syllable_end": syllable_interval.get("end"),

        "prominence_phone_label": phone_label,
        "prominence_phone_start": phone_interval.get("start"),
        "prominence_phone_end": phone_interval.get("end"),

        "prominence_combined_transcription": combined_prominence_transcription,

        "prominence_lookup_status": (
            word_interval.get("error", "")
            or syllable_interval.get("error", "")
            or phone_interval.get("error", "")
            or "OK"
        ),
    }


def build_interrogativity_marker_statement(
    prominence_material: dict,
    tune_decision: str = "",
    domain: str = "",
) -> str:
    """
    Build a readable interpretation connecting:
    prosodic domain → word/syllable/phone → F0 peak → interrogativity.
    """
    word = prominence_material.get("prominence_word_label", "N/A")
    syllable = prominence_material.get("prominence_syllable_label", "N/A")
    phone = prominence_material.get("prominence_phone_label", "N/A")
    peak_time = prominence_material.get("prominence_f0_peak_time", "N/A")
    peak_f0 = prominence_material.get("prominence_f0_peak_value_hz", "N/A")

    return (
        f"The F0 peak associated with prominence/interrogativity is aligned with "
        f"the word '{word}', the syllable-like unit '{syllable}', and the phone/sound "
        f"'{phone}'. The peak occurs at {peak_time} seconds with an F0 value of "
        f"{peak_f0} Hz. Prosodic domain: {domain or 'N/A'}. "
        f"Tune decision: {tune_decision or 'N/A'}."
    )



def extract_reference_transcript_from_textgrid(textgrid_path: str) -> dict:
    """
    Extract a reference transcript from TextGrid.

    Priority:
    1. TRN tier, if available
    2. ORT-MAU / word tier
    3. best available tier

    Returns:
    {
        "reference_transcript": "...",
        "reference_tier_used": "...",
        "reference_source": "TextGrid",
        "error": ""
    }
    """
    try:
        trn_tier = find_transcription_tier(textgrid_path)
        word_tier = find_word_tier(textgrid_path)

        if trn_tier:
            intervals = get_non_empty_intervals(textgrid_path, trn_tier)
            labels = [i["label"] for i in intervals if i.get("label")]
            transcript = " ".join(labels).strip()

            if transcript:
                return {
                    "reference_transcript": transcript,
                    "reference_tier_used": trn_tier,
                    "reference_source": "TextGrid TRN",
                    "error": "",
                }

        if word_tier:
            intervals = get_non_empty_intervals(textgrid_path, word_tier)
            labels = [i["label"] for i in intervals if i.get("label")]
            transcript = " ".join(labels).strip()

            if transcript:
                return {
                    "reference_transcript": transcript,
                    "reference_tier_used": word_tier,
                    "reference_source": "TextGrid word tier",
                    "error": "",
                }

        best_tier = find_best_tier_name(textgrid_path)
        if best_tier:
            intervals = get_non_empty_intervals(textgrid_path, best_tier)
            labels = [i["label"] for i in intervals if i.get("label")]
            transcript = " ".join(labels).strip()

            return {
                "reference_transcript": transcript,
                "reference_tier_used": best_tier,
                "reference_source": "TextGrid fallback tier",
                "error": "",
            }

        return {
            "reference_transcript": "",
            "reference_tier_used": "",
            "reference_source": "TextGrid",
            "error": "No usable transcript tier found.",
        }

    except Exception as e:
        return {
            "reference_transcript": "",
            "reference_tier_used": "",
            "reference_source": "TextGrid",
            "error": str(e),
        }

