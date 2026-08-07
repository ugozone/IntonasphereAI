import os
import re
from typing import Dict, List, Tuple


os.environ.setdefault(
    "PHONEMIZER_ESPEAK_LIBRARY",
    "/opt/homebrew/lib/libespeak-ng.dylib",
)


# ============================================================
# Language codes
# ============================================================

PHONEMIZER_LANGUAGE_CODES = {
    "Auto-detect": "fr-fr",

    # European languages
    "French": "fr-fr",
    "English": "en-us",
    "Nigerian English": "en-us",
    "Spanish": "es",
    "Portuguese": "pt-br",
    "German": "de",
    "Italian": "it",

    # African languages / approximations
    "Yoruba": "yo",
    "Hausa": "ha",
    "Igbo": "ig",
    "Swahili": "sw",
    "Amharic": "am",

    # Asian / Middle Eastern languages
    "Arabic": "ar",
    "Hindi": "hi",
    "Mandarin": "cmn",
    "Chinese": "cmn",
    "Japanese": "ja",
    "Korean": "ko",

    # Other global languages
    "Russian": "ru",
    "Turkish": "tr",

    # Pidgin approximations
    "Pidgin": "en-us",
    "Nigerian Pidgin": "en-us",
}


EPITRAN_LANGUAGE_CODES = {
    # European
    "French": "fra-Latn",
    "English": "eng-Latn",
    "Nigerian English": "eng-Latn",
    "Spanish": "spa-Latn",
    "Portuguese": "por-Latn",
    "German": "deu-Latn",
    "Italian": "ita-Latn",

    # African
    "Yoruba": "yor-Latn",
    "Hausa": "hau-Latn",
    "Igbo": "ibo-Latn",
    "Swahili": "swa-Latn",
    "Amharic": "amh-Ethi",

    # Asian / Middle Eastern
    "Arabic": "ara-Arab",
    "Hindi": "hin-Deva",
    "Mandarin": "cmn-Hans",
    "Chinese": "cmn-Hans",
    "Japanese": "jpn-Hira",
    "Korean": "kor-Hang",

    # Other
    "Russian": "rus-Cyrl",
    "Turkish": "tur-Latn",

    # Approximation
    "Pidgin": "eng-Latn",
    "Nigerian Pidgin": "eng-Latn",
}


LANGUAGE_ENGINE_PRIORITY = {
    # European languages: eSpeak is usually fast and stable
    "French": ["phonemizer_espeak", "epitran"],
    "English": ["phonemizer_espeak", "epitran"],
    "Nigerian English": ["phonemizer_espeak", "epitran"],
    "Spanish": ["phonemizer_espeak", "epitran"],
    "Portuguese": ["phonemizer_espeak", "epitran"],
    "German": ["phonemizer_espeak", "epitran"],
    "Italian": ["phonemizer_espeak", "epitran"],

    # African languages: Epitran/custom may be preferable where eSpeak is weak
    "Yoruba": ["epitran", "phonemizer_espeak", "custom_mapping"],
    "Hausa": ["epitran", "phonemizer_espeak", "custom_mapping"],
    "Igbo": ["custom_mapping", "epitran", "phonemizer_espeak"],
    "Swahili": ["epitran", "phonemizer_espeak"],
    "Amharic": ["epitran", "phonemizer_espeak"],

    # Asian and Middle Eastern languages
    "Arabic": ["epitran", "phonemizer_espeak"],
    "Hindi": ["epitran", "phonemizer_espeak"],
    "Mandarin": ["epitran", "phonemizer_espeak"],
    "Chinese": ["epitran", "phonemizer_espeak"],
    "Japanese": ["epitran", "phonemizer_espeak"],
    "Korean": ["epitran", "phonemizer_espeak"],

    # Others
    "Russian": ["epitran", "phonemizer_espeak"],
    "Turkish": ["epitran", "phonemizer_espeak"],

    # Pidgin
    "Pidgin": ["phonemizer_espeak", "epitran"],
    "Nigerian Pidgin": ["phonemizer_espeak", "epitran"],
}


# ============================================================
# Reliability notes
# ============================================================

def get_reliability_note(language: str, engine: str) -> str:
    """
    Return a transparent reliability note for global phonetic transcription.
    """
    if engine == "textgrid_only":
        return (
            "TextGrid mode selected. The phonetic material should be interpreted from "
            "the aligned TextGrid tiers rather than automatic text-to-IPA conversion."
        )

    if language in ["French", "English", "Spanish", "Portuguese", "German", "Italian"]:
        return (
            "Automatic IPA-like transcription is generally usable for first-pass display, "
            "but should be verified manually for research-level phonetic analysis."
        )

    if language in ["Yoruba", "Igbo", "Hausa"]:
        return (
            "Automatic phonetic transcription for Nigerian languages is approximate. "
            "Tone, vowel quality, orthographic variation, and dialectal differences may "
            "not be fully captured. Verify with TextGrid, Praat, and a language expert."
        )

    if language in ["Mandarin", "Chinese", "Japanese", "Korean", "Arabic", "Hindi"]:
        return (
            "Automatic phonetic transcription may depend strongly on script, tokenization, "
            "and language-specific rules. Verify manually before publication."
        )

    return (
        "Automatic phonetic transcription is approximate. Verify manually for research use."
    )


# ============================================================
# Text normalization
# ============================================================

def normalize_text_for_g2p(text: str) -> str:
    """
    Normalize whitespace while preserving punctuation.
    """
    if not text:
        return ""

    text = re.sub(r"\s+", " ", text.strip())
    return text


# ============================================================
# Engine 1: phonemizer + eSpeak-NG
# ============================================================

def phonemize_with_espeak(text: str, language: str) -> Tuple[str, Dict]:
    """
    Generate IPA-like transcription using phonemizer + eSpeak-NG.
    """
    from phonemizer import phonemize

    language_code = PHONEMIZER_LANGUAGE_CODES.get(language, "fr-fr")

    ipa = phonemize(
        text,
        language=language_code,
        backend="espeak",
        strip=True,
        preserve_punctuation=True,
        with_stress=False,
        njobs=1,
    )

    metadata = {
        "engine_used": "phonemizer_espeak",
        "language_code_used": language_code,
        "fallback_used": False,
    }

    return ipa.strip(), metadata


# ============================================================
# Engine 2: Epitran
# ============================================================

def phonemize_with_epitran(text: str, language: str) -> Tuple[str, Dict]:
    """
    Generate IPA using Epitran where available.
    """
    import epitran

    language_code = EPITRAN_LANGUAGE_CODES.get(language)

    if not language_code:
        raise ValueError(f"No Epitran code configured for language: {language}")

    epi = epitran.Epitran(language_code)

    # Epitran works best token by token for many languages.
    tokens = text.split()
    ipa_tokens = []

    for token in tokens:
        try:
            ipa_tokens.append(epi.transliterate(token))
        except Exception:
            ipa_tokens.append(token)

    ipa = " ".join(ipa_tokens)

    metadata = {
        "engine_used": "epitran",
        "language_code_used": language_code,
        "fallback_used": False,
    }

    return ipa.strip(), metadata


# ============================================================
# Engine 3: Custom mapping fallback
# ============================================================

IGBO_APPROX_MAP = {
    "ch": "tʃ",
    "gb": "ɡ͡b",
    "gh": "ɣ",
    "gw": "ɡʷ",
    "kp": "k͡p",
    "kw": "kʷ",
    "ny": "ɲ",
    "sh": "ʃ",
    "a": "a",
    "b": "b",
    "c": "k",
    "d": "d",
    "e": "e",
    "f": "f",
    "g": "ɡ",
    "h": "h",
    "i": "i",
    "ị": "ɪ",
    "j": "dʒ",
    "k": "k",
    "l": "l",
    "m": "m",
    "n": "n",
    "o": "o",
    "ọ": "ɔ",
    "p": "p",
    "r": "r",
    "s": "s",
    "t": "t",
    "u": "u",
    "ụ": "ʊ",
    "v": "v",
    "w": "w",
    "y": "j",
    "z": "z",
}


YORUBA_APPROX_MAP = {
    "ṣ": "ʃ",
    "gb": "ɡ͡b",
    "kp": "k͡p",
    "a": "a",
    "b": "b",
    "d": "d",
    "e": "e",
    "ẹ": "ɛ",
    "f": "f",
    "g": "ɡ",
    "h": "h",
    "i": "i",
    "j": "dʒ",
    "k": "k",
    "l": "l",
    "m": "m",
    "n": "n",
    "o": "o",
    "ọ": "ɔ",
    "p": "p",
    "r": "r",
    "s": "s",
    "t": "t",
    "u": "u",
    "w": "w",
    "y": "j",
}


HAUSA_APPROX_MAP = {
    "sh": "ʃ",
    "ts": "ts",
    "ƙ": "kʼ",
    "ƴ": "ʔʲ",
    "ɗ": "ɗ",
    "a": "a",
    "b": "b",
    "c": "tʃ",
    "d": "d",
    "e": "e",
    "f": "f",
    "g": "ɡ",
    "h": "h",
    "i": "i",
    "j": "dʒ",
    "k": "k",
    "l": "l",
    "m": "m",
    "n": "n",
    "o": "o",
    "r": "r",
    "s": "s",
    "t": "t",
    "u": "u",
    "w": "w",
    "y": "j",
    "z": "z",
}


def apply_custom_mapping_word(word: str, mapping: Dict[str, str]) -> str:
    """
    Apply simple longest-match grapheme mapping.
    """
    original = word
    word_lower = word.lower()

    output = []
    i = 0

    keys = sorted(mapping.keys(), key=len, reverse=True)

    while i < len(word_lower):
        matched = False

        for key in keys:
            if word_lower.startswith(key, i):
                output.append(mapping[key])
                i += len(key)
                matched = True
                break

        if not matched:
            char = word_lower[i]
            if char.isalpha():
                output.append(char)
            else:
                output.append(char)
            i += 1

    result = "".join(output)

    if not result:
        return original

    return result


def phonemize_with_custom_mapping(text: str, language: str) -> Tuple[str, Dict]:
    """
    Lightweight custom fallback for selected African languages.

    This is not a full phonological model. It is useful for transparent
    approximation and can later be replaced with a richer mapping file.
    """
    if language == "Igbo":
        mapping = IGBO_APPROX_MAP
    elif language == "Yoruba":
        mapping = YORUBA_APPROX_MAP
    elif language == "Hausa":
        mapping = HAUSA_APPROX_MAP
    else:
        raise ValueError(f"No custom mapping configured for language: {language}")

    tokens = text.split()
    ipa_tokens = [apply_custom_mapping_word(token, mapping) for token in tokens]
    ipa = " ".join(ipa_tokens)

    metadata = {
        "engine_used": "custom_mapping",
        "language_code_used": f"{language}_custom",
        "fallback_used": False,
    }

    return ipa.strip(), metadata


# ============================================================
# Engine routing
# ============================================================

def get_engine_sequence(language: str, phonetic_engine: str) -> List[str]:
    """
    Decide engine order based on user choice.
    """
    if phonetic_engine == "Auto global engine":
        return LANGUAGE_ENGINE_PRIORITY.get(
            language,
            ["phonemizer_espeak", "epitran", "custom_mapping"],
        )

    if phonetic_engine == "eSpeak-NG / phonemizer":
        return ["phonemizer_espeak"]

    if phonetic_engine == "Epitran":
        return ["epitran"]

    if phonetic_engine == "Custom mapping":
        return ["custom_mapping"]

    if phonetic_engine == "TextGrid only":
        return ["textgrid_only"]

    return ["phonemizer_espeak"]


def run_engine(text: str, language: str, engine: str) -> Tuple[str, Dict]:
    """
    Run a selected phonetic engine.
    """
    if engine == "phonemizer_espeak":
        return phonemize_with_espeak(text, language)

    if engine == "epitran":
        return phonemize_with_epitran(text, language)

    if engine == "custom_mapping":
        return phonemize_with_custom_mapping(text, language)

    if engine == "textgrid_only":
        return (
            "",
            {
                "engine_used": "textgrid_only",
                "language_code_used": "TextGrid",
                "fallback_used": False,
            },
        )

    raise ValueError(f"Unknown phonetic engine: {engine}")


def get_global_phonetic_transcription(
    text: str,
    language: str = "French",
    phonetic_engine: str = "Auto global engine",
) -> Dict:
    """
    Global phonetic transcription router.

    Returns:
    {
        "phonetic_transcription": "...",
        "engine_used": "...",
        "language_code_used": "...",
        "fallback_used": bool,
        "attempted_engines": "...",
        "reliability_note": "...",
        "error": ""
    }
    """
    text = normalize_text_for_g2p(text)

    if not text:
        return {
            "phonetic_transcription": "",
            "engine_used": "",
            "language_code_used": "",
            "fallback_used": False,
            "attempted_engines": "",
            "reliability_note": "No text was provided.",
            "error": "",
        }

    engine_sequence = get_engine_sequence(language, phonetic_engine)
    attempted = []
    errors = []

    for idx, engine in enumerate(engine_sequence):
        attempted.append(engine)

        try:
            ipa, metadata = run_engine(text, language, engine)

            fallback_used = idx > 0

            return {
                "phonetic_transcription": ipa,
                "engine_used": metadata.get("engine_used", engine),
                "language_code_used": metadata.get("language_code_used", ""),
                "fallback_used": fallback_used,
                "attempted_engines": " → ".join(attempted),
                "reliability_note": get_reliability_note(language, engine),
                "error": "",
            }

        except Exception as e:
            errors.append(f"{engine}: {e}")

    # Final fallback: return original text with warning
    return {
        "phonetic_transcription": text,
        "engine_used": "orthographic_fallback",
        "language_code_used": "none",
        "fallback_used": True,
        "attempted_engines": " → ".join(attempted),
        "reliability_note": (
            "No phonetic engine succeeded. Orthographic text is shown as fallback. "
            "Use TextGrid alignment or manual phonetic transcription."
        ),
        "error": " | ".join(errors),
    }


# ============================================================
# Final unit estimation
# ============================================================

def split_into_syllable_like_units(ipa: str) -> list:
    """
    Simple visible segmentation by spaces.
    """
    if not ipa:
        return []

    clean = ipa.split("\n\n[Note:")[0]
    return clean.replace("ː", "").split()


def estimate_final_syllable_from_ipa(ipa: str) -> str:
    """
    Estimate final pronounced unit from IPA-like transcription.
    """
    units = split_into_syllable_like_units(ipa)

    if not units:
        return ""

    return units[-1].strip(".,?!;:")
