from faster_whisper import WhisperModel


LANGUAGE_TO_WHISPER_CODE = {
    "Auto-detect": None,

    "English": "en",
    "Nigerian English": "en",
    "French": "fr",
    "Spanish": "es",
    "Portuguese": "pt",
    "German": "de",
    "Italian": "it",

    "Igbo": None,
    "Yoruba": None,
    "Hausa": None,
    "Swahili": "sw",
    "Amharic": "am",

    "Arabic": "ar",
    "Hindi": "hi",
    "Mandarin": "zh",
    "Chinese": "zh",
    "Japanese": "ja",
    "Korean": "ko",

    "Russian": "ru",
    "Turkish": "tr",

    "Pidgin": "en",
    "Nigerian Pidgin": "en",
}


DEFAULT_TRANSCRIPTION_PROMPT = (
    "Transcribe carefully in the selected language. Preserve proper names, accents, "
    "punctuation, and formal read-speech structures. For French, preserve inversion, "
    "liaison, clitic forms, and phrases such as: Le Premier Ministre ira-t-il à Beaulieu ? "
    "Comment peut-on éviter les manifestations qui ont eu lieu pendant les visites officielles ?"
)


def get_compute_type() -> str:
    """
    Use int8 for broad Mac compatibility.
    """
    return "int8"


def transcribe_audio(
    audio_path: str,
    language: str = "Auto-detect",
    model_size: str = "base",
    initial_prompt: str = "",
):
    """
    Transcribe audio using faster-whisper with stronger, research-friendly settings.

    Improvements:
    - beam_size=10 for better search
    - best_of=5 for stronger candidate selection
    - temperature=0.0 to reduce hallucination
    - vad_filter=True to remove silence/noise
    - condition_on_previous_text=False to reduce carry-over hallucinations
    - optional initial prompt for PFC/formal French or other corpora
    """

    whisper_language = LANGUAGE_TO_WHISPER_CODE.get(language, None)

    prompt = initial_prompt.strip() if initial_prompt else DEFAULT_TRANSCRIPTION_PROMPT

    model = WhisperModel(
        model_size,
        device="cpu",
        compute_type=get_compute_type(),
    )

    segments_generator, info = model.transcribe(
        audio_path,
        language=whisper_language,
        beam_size=10,
        best_of=5,
        temperature=0.0,
        vad_filter=True,
        vad_parameters={
            "min_silence_duration_ms": 500,
            "speech_pad_ms": 300,
        },
        initial_prompt=prompt,
        condition_on_previous_text=False,
        word_timestamps=True,
    )

    segments = []
    transcript_parts = []

    for segment in segments_generator:
        item = {
            "start": float(segment.start),
            "end": float(segment.end),
            "text": segment.text.strip(),
        }

        if getattr(segment, "words", None):
            item["words"] = [
                {
                    "word": word.word,
                    "start": float(word.start) if word.start is not None else None,
                    "end": float(word.end) if word.end is not None else None,
                    "probability": float(word.probability) if word.probability is not None else None,
                }
                for word in segment.words
            ]

        segments.append(item)
        transcript_parts.append(segment.text.strip())

    transcript = " ".join(transcript_parts).strip()

    metadata = {
        "detected_language": getattr(info, "language", None),
        "language_probability": getattr(info, "language_probability", None),
        "duration": getattr(info, "duration", None),
        "model_size": model_size,
        "language_setting": language,
        "whisper_language_code": whisper_language or "auto",
        "initial_prompt_used": prompt,
    }

    return transcript, segments, metadata
