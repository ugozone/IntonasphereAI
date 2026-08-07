import os

os.environ.setdefault(
    "PHONEMIZER_ESPEAK_LIBRARY",
    "/opt/homebrew/lib/libespeak-ng.dylib"
)

from phonemizer import phonemize


LANGUAGE_TO_PHONEMIZER = {
    "French": "fr-fr",
    "English": "en-us",
    "Nigerian English": "en-us",

    "Igbo": "ig",
    "Yoruba": "yo",
    "Hausa": "ha",

    "Pidgin": "en-us",
    "Nigerian Pidgin": "en-us",

    "Spanish": "es",
    "Portuguese": "pt-br",
    "German": "de",
    "Italian": "it",
}


def get_phonetic_transcription(text: str, language: str = "French") -> str:
    """
    Generate visible IPA-like phonetic transcription using phonemizer + espeak-ng.
    """
    if not text or not text.strip():
        return ""

    phonemizer_lang = LANGUAGE_TO_PHONEMIZER.get(language, "fr-fr")

    try:
        ipa = phonemize(
            text,
            language=phonemizer_lang,
            backend="espeak",
            strip=True,
            preserve_punctuation=True,
            with_stress=False,
            njobs=1,
        )
        return ipa.strip()

    except Exception as e:
        try:
            ipa = phonemize(
                text,
                language="en-us",
                backend="espeak",
                strip=True,
                preserve_punctuation=True,
                with_stress=False,
                njobs=1,
            )
            return (
                ipa.strip()
                + f"\n\n[Note: {language} phonemization was not available; English fallback used.]"
            )
        except Exception:
            return f"Phonetic transcription failed: {e}"


def split_into_syllable_like_units(ipa: str) -> list:
    """
    Simple visible segmentation by phonetic word/unit.
    """
    if not ipa:
        return []

    ipa_main = ipa.split("\n\n[Note:")[0]
    units = ipa_main.replace("ː", "").split()
    return units


def estimate_final_syllable_from_ipa(ipa: str) -> str:
    """
    Estimate the final pronounced unit from the IPA-like transcription.
    """
    units = split_into_syllable_like_units(ipa)

    if not units:
        return ""

    final_unit = units[-1]
    final_unit = final_unit.strip(".,?!;:")

    return final_unit