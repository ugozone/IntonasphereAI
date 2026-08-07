import os
import pandas as pd
import streamlit as st
from pathlib import Path

BASE_DATA_DIR = Path(os.getenv("INTONASPHERE_DATA_DIR", "."))

UPLOAD_DIR = BASE_DATA_DIR / "uploads"
OUTPUT_DIR = BASE_DATA_DIR / "outputs"
PFC_AUDIO_DIR = BASE_DATA_DIR / "pfc_audio"
PFC_TEXTGRID_DIR = BASE_DATA_DIR / "pfc_textgrids"

for folder in [
    UPLOAD_DIR,
    OUTPUT_DIR,
    OUTPUT_DIR / "csv",
    OUTPUT_DIR / "excel",
    OUTPUT_DIR / "logs",
    PFC_AUDIO_DIR,
    PFC_TEXTGRID_DIR,
]:
    folder.mkdir(parents=True, exist_ok=True)
import matplotlib.pyplot as plt
from jiwer import wer

from ui_components import (
    load_global_css,
    render_mobile_responsive_navbar,
    render_global_hero,
    render_global_feature_cards,
    render_research_workflow,
    render_trust_banner,
    render_global_footer,
)

from media_utils import (
    save_uploaded_file,
    convert_to_wav,
    download_media_from_url,
    check_ffmpeg_installed,
    extract_speaker_id_from_filename,
)

from transcriber import transcribe_audio

from global_phonetic_utils import (
    get_global_phonetic_transcription,
    estimate_final_syllable_from_ipa,
)

from praat_analysis import (
    analyze_audio_with_praat,
    analyze_final_pitch_movement,
    analyze_prominence_and_tune,
    analyze_final_syllable_alignment,
    analyze_textgrid_final_interval_alignment,
    extract_pitch_track,
    build_acoustic_dataframe,
)

from textgrid_utils import (
    match_audio_textgrid_pairs,
    get_tier_names,
    find_best_tier_name,
    get_final_interval_from_textgrid,
    get_interval_at_time,
    get_phonetic_portions_for_ap_ip_final,
    get_prominence_material_at_time,
    build_interrogativity_marker_statement,
    extract_reference_transcript_from_textgrid,
    summarize_textgrid,
)

from voiceprint_analysis import (
    analyze_voiceprint_features,
    voiceprint_results_to_dataframe,
    voiceprint_disclaimer,
)

from export_utils import (
    save_transcript_txt,
    save_transcript_docx,
    save_transcript_pdf,
    save_acoustic_csv,
    save_acoustic_excel,
    save_srt,
    save_pitch_contour_image,
    save_transcription_report_txt,
    save_full_analysis_txt,
    save_full_analysis_docx,
    save_full_analysis_pdf,
    save_full_analysis_excel,
    save_full_analysis_csv,
    save_batch_analysis_csv,
    save_batch_analysis_excel,
    save_batch_analysis_txt,
    save_batch_analysis_docx,
    read_binary_file,
)


# ============================================================
# Session state
# ============================================================

if "analysis_results" not in st.session_state:
    st.session_state.analysis_results = []

if "last_batch_df" not in st.session_state:
    st.session_state.last_batch_df = None

if "batch_export_paths" not in st.session_state:
    st.session_state.batch_export_paths = {}

if "batch_errors" not in st.session_state:
    st.session_state.batch_errors = []


if "current_transcript" not in st.session_state:
    st.session_state.current_transcript = ""

if "current_speaker_id" not in st.session_state:
    st.session_state.current_speaker_id = ""

if "current_file_name" not in st.session_state:
    st.session_state.current_file_name = ""


# ============================================================
# Page setup
# ============================================================

st.set_page_config(
    page_title="IntonaSphere AI",
    layout="wide",
    initial_sidebar_state="expanded",
)

load_global_css()
render_mobile_responsive_navbar()
render_global_hero()
render_global_feature_cards()
render_research_workflow()
render_trust_banner()


st.info(
    "Settings are available in the left sidebar: input type, language, phonetic engine, "
    "Whisper model, audio cleaning, TextGrid options, and analysis settings."
)


# ============================================================
# Helper functions
# ============================================================

def stable_download_button(label, data, file_name, mime):
    """
    Download button that does not trigger a full Streamlit rerun.
    """
    st.download_button(
        label,
        data=data,
        file_name=file_name,
        mime=mime,
        on_click="ignore",
    )


def count_words(text: str) -> int:
    """
    Simple word counter for reference and hypothesis texts.
    """
    if not text:
        return 0
    return len(text.strip().split())


def interpret_wer(error_rate: float) -> dict:
    """
    Interpret Word Error Rate using practical transcription-quality criteria.

    WER = (Substitutions + Deletions + Insertions) / Reference word count.

    Lower WER is better.
    """
    accuracy = max(0, 1 - error_rate) * 100

    if error_rate <= 0.05:
        label = "Excellent transcription match"
        recommendation = (
            "The transcript is highly reliable. Only light verification is needed."
        )
    elif error_rate <= 0.15:
        label = "Very good transcription match"
        recommendation = (
            "The transcript is usable, but verify names, liaison, clitics, and punctuation."
        )
    elif error_rate <= 0.30:
        label = "Acceptable transcription match"
        recommendation = (
            "The transcript can be used after manual correction. Review carefully before analysis."
        )
    elif error_rate <= 0.50:
        label = "Weak transcription match"
        recommendation = (
            "The transcript contains many errors. Correct it manually before phonetic/prosodic analysis."
        )
    else:
        label = "Poor transcription match"
        recommendation = (
            "The transcript is not reliable. Re-record, improve audio quality, or manually transcribe."
        )

    return {
        "wer": error_rate,
        "accuracy": accuracy,
        "label": label,
        "recommendation": recommendation,
    }


def display_accuracy_criteria():
    """
    Display the criteria/indices used by the transcription accuracy checker.
    """
    with st.expander("Accuracy criteria / indices", expanded=False):
        st.markdown(
            """
            **Purpose:** This module evaluates **transcription accuracy**, not pronunciation quality.

            **Reference text:** the correct sentence typed by the user.  
            **Machine transcript:** the transcript generated by the app.

            **Main index: Word Error Rate (WER)**

            `WER = (Substitutions + Deletions + Insertions) / Total words in reference`

            **Derived index: Accuracy**

            `Accuracy = max(0, 1 - WER) × 100`

            | WER | Accuracy | Interpretation |
            |---:|---:|---|
            | 0.00–0.05 | 95–100% | Excellent transcription match |
            | 0.06–0.15 | 85–94% | Very good transcription match |
            | 0.16–0.30 | 70–84% | Acceptable, but needs review |
            | 0.31–0.50 | 50–69% | Weak transcription; many errors |
            | Above 0.50 | Below 50% | Poor transcription; manual correction needed |
            """
        )


def display_accuracy_checker(reference_key: str, speaker_id: str, transcript: str) -> dict:
    """
    Display transcription accuracy checker with clear indices.

    Returns a dictionary that can be exported in the full report.
    """
    st.subheader("Transcription Accuracy Checker")

    st.markdown(
        """
        This checker compares the **reference text** you type with the **machine transcript**.
        It measures transcription reliability, not pronunciation quality.
        """
    )

    display_accuracy_criteria()

    reference_text = st.text_area(
        f"Paste the correct/reference text for speaker {speaker_id}",
        key=reference_key,
        height=150,
    )

    latest_accuracy_info = {}

    if reference_text.strip():
        try:
            error_rate = wer(reference_text, transcript)
            accuracy_info = interpret_wer(error_rate)

            reference_word_count = count_words(reference_text)
            machine_word_count = count_words(transcript)

            latest_accuracy_info = {
                "reference_text": reference_text,
                "machine_transcript": transcript,
                "reference_word_count": reference_word_count,
                "machine_word_count": machine_word_count,
                "word_error_rate": accuracy_info["wer"],
                "estimated_accuracy_percent": accuracy_info["accuracy"],
                "interpretation_level": accuracy_info["label"],
                "recommendation": accuracy_info["recommendation"],
            }

            col1, col2, col3, col4 = st.columns(4)

            col1.metric("Word Error Rate", f"{accuracy_info['wer']:.2f}")
            col2.metric("Estimated Accuracy", f"{accuracy_info['accuracy']:.2f}%")
            col3.metric("Reference Words", reference_word_count)
            col4.metric("Machine Words", machine_word_count)

            st.markdown("### Accuracy Interpretation")
            st.write(f"**Level:** {accuracy_info['label']}")
            st.write(f"**Recommendation:** {accuracy_info['recommendation']}")

            st.markdown("### Machine transcript being checked")
            st.code(transcript)

        except Exception as e:
            st.error(f"Accuracy calculation failed: {e}")

    return latest_accuracy_info




# ============================================================
# Batch analysis helpers
# ============================================================

def make_failed_batch_row(file_name: str, speaker_id: str, error_message: str) -> pd.DataFrame:
    """
    Create a one-row dataframe when a file fails, so the batch output still records it.
    """
    return pd.DataFrame(
        [
            {
                "speaker_id": speaker_id,
                "file_name": file_name,
                "analysis_status": "failed",
                "analysis_error": error_message,
            }
        ]
    )


def build_master_batch_dataframe(result_dfs: list) -> pd.DataFrame:
    """
    Combine all individual speaker/file dataframes into one master batch dataframe.
    Pandas automatically aligns columns and fills missing values with NaN.
    """
    valid = [df for df in result_dfs if df is not None and not df.empty]

    if not valid:
        return pd.DataFrame()

    batch_df = pd.concat(valid, ignore_index=True, sort=False)

    # Put important identifying columns first when they exist.
    priority_cols = [
        "speaker_id",
        "file_name",
        "textgrid_file",
        "language_setting",
        "analysis_status",
        "analysis_error",
        "sentence_for_analysis",
        "whisper_transcript",
        "textgrid_reference_transcript",
        "phonetic_transcription",
        "estimated_final_unit",
    ]

    existing_priority = [col for col in priority_cols if col in batch_df.columns]
    remaining_cols = [col for col in batch_df.columns if col not in existing_priority]

    batch_df = batch_df[existing_priority + remaining_cols]

    return batch_df


def create_batch_export_files(batch_df: pd.DataFrame, prefix: str = "batch_acoustic_analysis") -> dict:
    """
    Save batch dataframe in multiple formats and return paths.
    """
    paths = {}

    paths["csv"] = save_batch_analysis_csv(
        batch_df,
        filename=f"{prefix}.csv",
    )

    paths["excel"] = save_batch_analysis_excel(
        batch_df,
        filename=f"{prefix}.xlsx",
    )

    paths["txt"] = save_batch_analysis_txt(
        batch_df,
        filename=f"{prefix}.txt",
    )

    paths["docx"] = save_batch_analysis_docx(
        batch_df,
        filename=f"{prefix}.docx",
    )

    return paths


def render_batch_download_buttons(batch_df: pd.DataFrame, prefix: str = "batch_acoustic_analysis"):
    """
    Render batch dataframe and stable download buttons.
    """
    if batch_df is None or batch_df.empty:
        st.warning("No batch dataframe available yet.")
        return

    st.subheader("Combined Batch Acoustic / Prosodic Dataframe")
    st.dataframe(batch_df, use_container_width=True)

    export_paths = create_batch_export_files(batch_df, prefix=prefix)

    st.session_state.last_batch_df = batch_df
    st.session_state.batch_export_paths = export_paths

    st.markdown("### Download Combined Batch File")

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        stable_download_button(
            "Batch CSV",
            data=read_binary_file(export_paths["csv"]),
            file_name=f"{prefix}.csv",
            mime="text/csv",
        )

    with col2:
        stable_download_button(
            "Batch Excel",
            data=read_binary_file(export_paths["excel"]),
            file_name=f"{prefix}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    with col3:
        stable_download_button(
            "Batch TXT",
            data=read_binary_file(export_paths["txt"]),
            file_name=f"{prefix}.txt",
            mime="text/plain",
        )

    with col4:
        stable_download_button(
            "Batch DOCX",
            data=read_binary_file(export_paths["docx"]),
            file_name=f"{prefix}.docx",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )


def render_persistent_batch_downloads():
    """
    Keep latest batch results downloadable even after Streamlit reruns.
    """
    batch_df = st.session_state.get("last_batch_df", None)
    export_paths = st.session_state.get("batch_export_paths", {})

    if batch_df is None or batch_df.empty:
        return

    with st.expander("Latest Batch Results and Downloads", expanded=False):
        st.dataframe(batch_df, use_container_width=True)

        if not export_paths:
            export_paths = create_batch_export_files(
                batch_df,
                prefix="latest_batch_acoustic_analysis",
            )
            st.session_state.batch_export_paths = export_paths

        col1, col2, col3, col4 = st.columns(4)

        with col1:
            stable_download_button(
                "Download Latest CSV",
                data=read_binary_file(export_paths["csv"]),
                file_name="latest_batch_acoustic_analysis.csv",
                mime="text/csv",
            )

        with col2:
            stable_download_button(
                "Download Latest Excel",
                data=read_binary_file(export_paths["excel"]),
                file_name="latest_batch_acoustic_analysis.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )

        with col3:
            stable_download_button(
                "Download Latest TXT",
                data=read_binary_file(export_paths["txt"]),
                file_name="latest_batch_acoustic_analysis.txt",
                mime="text/plain",
            )

        with col4:
            stable_download_button(
                "Download Latest DOCX",
                data=read_binary_file(export_paths["docx"]),
                file_name="latest_batch_acoustic_analysis.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )



# ============================================================
# System check
# ============================================================

with st.expander("System Check"):
    if check_ffmpeg_installed():
        st.success("FFmpeg is installed and available.")
    else:
        st.error("FFmpeg is not installed. On Mac, run: brew install ffmpeg")

    st.info(
        """
        For phonetic transcription, this app uses phonemizer + eSpeak-NG.
        On your Mac, the eSpeak-NG library should be available at:
        /opt/homebrew/lib/libespeak-ng.dylib
        """
    )


# ============================================================
# Sidebar settings
# ============================================================


st.sidebar.header("Analysis Modules")

analysis_modules = st.sidebar.multiselect(
    "Select analysis module(s)",
    [
        "Transcription",
        "Phonetic transcription",
        "Praat acoustic/prosodic analysis",
        "TextGrid alignment analysis",
        "Voiceprint / Vocal Empreinte analysis",
        "Full combined analysis",
    ],
    default=[
        "Transcription",
        "Phonetic transcription",
        "Praat acoustic/prosodic analysis",
    ],
    help=(
        "Choose the type of analysis to perform. "
        "For speaker identity-style profiling, choose Voiceprint / Vocal Empreinte analysis. "
        "For dissertation prosody work, choose Praat and TextGrid analysis."
    ),
)

run_full_combined_module = "Full combined analysis" in analysis_modules

run_transcription_module = (
    "Transcription" in analysis_modules
    or "Phonetic transcription" in analysis_modules
    or "Praat acoustic/prosodic analysis" in analysis_modules
    or "TextGrid alignment analysis" in analysis_modules
    or run_full_combined_module
)

run_phonetic_module = (
    "Phonetic transcription" in analysis_modules
    or run_full_combined_module
)

run_praat_module = (
    "Praat acoustic/prosodic analysis" in analysis_modules
    or run_full_combined_module
)

run_textgrid_module = (
    "TextGrid alignment analysis" in analysis_modules
    or run_full_combined_module
)

run_voiceprint_module = (
    "Voiceprint / Vocal Empreinte analysis" in analysis_modules
    or run_full_combined_module
)

st.sidebar.divider()
st.sidebar.header("Settings")


input_mode = st.sidebar.radio(
    "Choose input type",
    [
        "Upload audio/video",
        "Upload audio + TextGrid pairs",
        "Record voice",
        "Paste media URL",
    ],
)

language = st.sidebar.selectbox(
    "Transcription language",
    [
        "Auto-detect",
        "English",
        "Nigerian English",
        "French",
        "Spanish",
        "Portuguese",
        "German",
        "Italian",

        "Igbo",
        "Yoruba",
        "Hausa",
        "Swahili",
        "Amharic",

        "Arabic",
        "Hindi",
        "Mandarin",
        "Chinese",
        "Japanese",
        "Korean",

        "Russian",
        "Turkish",

        "Pidgin",
        "Nigerian Pidgin",
    ],
)

phonetic_engine = st.sidebar.selectbox(
    "Phonetic transcription engine",
    [
        "Auto global engine",
        "eSpeak-NG / phonemizer",
        "Epitran",
        "Custom mapping",
        "TextGrid only",
    ],
    index=0,
    help=(
        "Auto global engine chooses the best available phonetic backend for the language. "
        "TextGrid only is best when you want aligned tiers to carry the phonetic analysis."
    ),
)


model_size = st.sidebar.selectbox(
    "Whisper model size",
    ["tiny", "base", "small", "medium", "large-v3"],
    index=2,
    help=(
        "Use small or medium for normal work. Use large-v3 for best accuracy, "
        "but it will be slower on a MacBook."
    ),
)

transcription_prompt = st.sidebar.text_area(
    "Optional transcription prompt",
    value=(
        "Transcribe carefully in the selected language. "
        "For French, preserve formal read-speech wording, inversion, liaison, "
        "proper names, accents, and punctuation. "
        "Examples: Le Premier Ministre ira-t-il à Beaulieu ? "
        "Comment peut-on éviter les manifestations qui ont eu lieu pendant les visites officielles ?"
    ),
    height=140,
)

clean_audio_for_transcription = st.sidebar.checkbox(
    "Clean/normalize audio before transcription",
    value=True,
    help=(
        "Uses FFmpeg highpass, lowpass, mono conversion, resampling, and loudness normalization. "
        "Recommended for transcription accuracy."
    ),
)

use_textgrid_reference_transcript = st.sidebar.checkbox(
    "Use TextGrid transcript as reference when available",
    value=True,
    help=(
        "When an audio + TextGrid pair is uploaded, the app can use TRN or ORT-MAU "
        "as the reference sentence for analysis instead of relying only on Whisper."
    ),
)


sample_rate = st.sidebar.selectbox(
    "Audio sample rate",
    [16000, 44100],
    index=0,
    help=(
        "Use 16000 Hz for faster transcription. "
        "Use 44100 Hz for better acoustic analysis when source audio quality is high."
    ),
)

voiceprint_pitch_floor = st.sidebar.number_input(
    "Voiceprint pitch floor Hz",
    min_value=40.0,
    max_value=300.0,
    value=75.0,
    step=5.0,
    help="Use lower values for male/deep voices; higher if the pitch tracker misses high voices.",
)

voiceprint_pitch_ceiling = st.sidebar.number_input(
    "Voiceprint pitch ceiling Hz",
    min_value=150.0,
    max_value=900.0,
    value=500.0,
    step=25.0,
    help="Use higher values for children or high-pitched voices.",
)

final_syllable_window = st.sidebar.slider(
    "Final syllable-like window duration",
    min_value=0.10,
    max_value=0.80,
    value=0.30,
    step=0.05,
    help=(
        "This approximates the final syllable duration in seconds. "
        "TextGrid mode uses exact interval boundaries instead."
    ),
)

run_acoustic_analysis = st.sidebar.checkbox(
    "Run Praat acoustic analysis",
    value=True,
)

run_accuracy_test = st.sidebar.checkbox(
    "Enable transcription accuracy testing",
    value=True,
)

run_transcription_in_textgrid_mode = st.sidebar.checkbox(
    "Run Whisper transcription in TextGrid mode",
    value=True,
    help=(
        "Turn this off if your TextGrid already contains the correct transcript "
        "and you only want acoustic extraction."
    ),
)


# ============================================================
# Main processing function
# ============================================================

def process_media(
    input_path: str,
    original_file_name: str = "",
    manual_speaker_id: str = "",
    textgrid_path: str = "",
    selected_textgrid_tier: str = "",
):
    """
    Main processing function.

    It performs:
    1. Speaker ID extraction.
    2. WAV conversion.
    3. Orthographic transcription.
    4. Phonetic transcription.
    5. Transcription accuracy indices.
    6. Praat acoustic/prosodic analysis.
    7. TextGrid-based final interval analysis.
    8. AP/IP/final-syllable word/syllable/phone extraction.
    9. F0 peak/prominence/interrogativity marker mapping.
    10. Full coherent report export.
    """

    # --------------------------------------------------------
    # Speaker and file information
    # --------------------------------------------------------

    if manual_speaker_id.strip():
        speaker_id = manual_speaker_id.strip()
    else:
        speaker_id = extract_speaker_id_from_filename(original_file_name or input_path)

    file_name = original_file_name or os.path.basename(input_path)

    # Default TextGrid reference transcript info.
    # This must be defined early so it is always available,
    # even when no TextGrid transcript is found or extraction fails.
    textgrid_reference_info = {
        "reference_transcript": "",
        "reference_tier_used": "",
        "reference_source": "",
        "error": "",
    }

    if textgrid_path:
        try:
            textgrid_reference_info = extract_reference_transcript_from_textgrid(
                textgrid_path
            )
        except Exception as e:
            textgrid_reference_info = {
                "reference_transcript": "",
                "reference_tier_used": "",
                "reference_source": "TextGrid",
                "error": str(e),
            }

    st.subheader("Speaker and File Information")

    speaker_info = {
        "speaker_id": speaker_id,
        "file_name": file_name,
        "input_path": input_path,
        "textgrid_path": textgrid_path or "No TextGrid provided",
        "language_setting": language,
    }

    st.dataframe(pd.DataFrame([speaker_info]), use_container_width=True)

    # --------------------------------------------------------
    # Convert media to WAV
    # --------------------------------------------------------

    try:
        with st.spinner("Converting media to WAV..."):
            audio_path = convert_to_wav(
                input_path,
                sample_rate=sample_rate,
                clean_audio=clean_audio_for_transcription,
            )

        st.subheader("Processed Audio")
        st.audio(audio_path)

    except Exception as e:
        st.error(f"Audio/video conversion failed: {e}")
        return None

    # --------------------------------------------------------
    # Transcription
    # --------------------------------------------------------

    transcript = ""
    segments = []
    metadata = {
        "detected_language": None,
        "language_probability": None,
        "duration": None,
    }

    should_transcribe = run_transcription_module

    if textgrid_path and not run_transcription_in_textgrid_mode:
        should_transcribe = False

    if should_transcribe:
        try:
            with st.spinner("Transcribing audio... This may take some time."):
                transcript, segments, metadata = transcribe_audio(
                    audio_path=audio_path,
                    language=language,
                    model_size=model_size,
                    initial_prompt=transcription_prompt,
                )

            st.success("Transcription completed.")

            st.session_state.current_transcript = transcript
            st.session_state.current_speaker_id = speaker_id
            st.session_state.current_file_name = file_name

        except Exception as e:
            st.error(f"Transcription failed: {e}")
            transcript = ""
            segments = []
    else:
        st.info("Whisper transcription skipped for this TextGrid analysis.")

    # --------------------------------------------------------
    # Orthographic transcript
    # --------------------------------------------------------

    st.subheader("Orthographic Transcript")

    if transcript:
        st.text_area(
            f"Generated orthographic transcript for speaker {speaker_id}",
            transcript,
            height=300,
        )
    else:
        st.text_area(
            f"Orthographic transcript for speaker {speaker_id}",
            "",
            height=120,
            placeholder="No Whisper transcript generated. You may paste/correct a sentence below.",
        )

    col_meta1, col_meta2, col_meta3 = st.columns(3)

    col_meta1.metric(
        "Detected language",
        metadata.get("detected_language") or "N/A",
    )

    lang_prob = metadata.get("language_probability")
    if lang_prob is not None:
        col_meta2.metric("Language probability", f"{lang_prob:.2f}")
    else:
        col_meta2.metric("Language probability", "N/A")

    duration = metadata.get("duration")
    if duration is not None:
        col_meta3.metric("Audio duration", f"{duration:.2f} sec")
    else:
        col_meta3.metric("Audio duration", "N/A")

    # --------------------------------------------------------
    # Phonetic transcription
    # --------------------------------------------------------

    st.subheader("Sentence and Phonetic Transcription")

    preferred_sentence = transcript

    if (
        textgrid_path
        and use_textgrid_reference_transcript
        and textgrid_reference_info.get("reference_transcript")
    ):
        preferred_sentence = textgrid_reference_info.get("reference_transcript")

    sentence_for_analysis = st.text_area(
        f"Sentence to analyze for speaker {speaker_id}",
        value=preferred_sentence,
        height=100,
        help=(
            "You can edit this sentence before generating phonetic and prosodic interpretation. "
            "When TextGrid reference is available, it is preferred over raw Whisper output."
        ),
    )

    phonetic_language = language if language != "Auto-detect" else "French"

    phonetic_result = get_global_phonetic_transcription(
        sentence_for_analysis,
        language=phonetic_language,
        phonetic_engine=phonetic_engine,
    )

    phonetic_transcription = phonetic_result.get("phonetic_transcription", "")

    phonetic_engine_used = phonetic_result.get("engine_used", "")
    phonetic_language_code_used = phonetic_result.get("language_code_used", "")
    phonetic_fallback_used = phonetic_result.get("fallback_used", False)
    phonetic_attempted_engines = phonetic_result.get("attempted_engines", "")
    phonetic_reliability_note = phonetic_result.get("reliability_note", "")
    phonetic_error = phonetic_result.get("error", "")

    estimated_final_syllable = estimate_final_syllable_from_ipa(
        phonetic_transcription
    )

    col_phon1, col_phon2 = st.columns(2)

    with col_phon1:
        st.markdown("**Visible phonetic transcription**")
        st.code(phonetic_transcription)

    with col_phon2:
        st.markdown("**Estimated final pronounced unit / syllable-like unit**")
        st.code(estimated_final_syllable)

    st.markdown("### Global Phonetic Engine Information")

    phonetic_engine_table = {
        "Field": [
            "Engine requested",
            "Engine used",
            "Language code used",
            "Fallback used",
            "Attempted engines",
            "Reliability note",
            "Error/status",
        ],
        "Value": [
            phonetic_engine,
            phonetic_engine_used,
            phonetic_language_code_used,
            phonetic_fallback_used,
            phonetic_attempted_engines,
            phonetic_reliability_note,
            phonetic_error or "OK",
        ],
    }

    st.dataframe(phonetic_engine_table, use_container_width=True)

    st.caption(
        "Automatic phonetic transcription is a first-pass representation. "
        "For dissertation-level work, verify pronunciation with Praat, TextGrid, "
        "forced alignment, and language-specific expertise."
    )

    # --------------------------------------------------------
    # TextGrid summary
    # --------------------------------------------------------

    textgrid_reference_info = {
        "reference_transcript": "",
        "reference_tier_used": "",
        "reference_source": "",
        "error": "",
    }

    if textgrid_path:
        st.subheader("TextGrid Summary")

        try:
            tg_summary = summarize_textgrid(textgrid_path)
            st.dataframe(pd.DataFrame([tg_summary]), use_container_width=True)
        except Exception as e:
            st.error(f"TextGrid summary failed: {e}")

        try:
            textgrid_reference_info = extract_reference_transcript_from_textgrid(
                textgrid_path
            )

            if textgrid_reference_info.get("reference_transcript"):
                st.markdown("### TextGrid Reference Transcript")
                st.info(
                    f"Reference source: "
                    f"{textgrid_reference_info.get('reference_source')} | "
                    f"Tier: {textgrid_reference_info.get('reference_tier_used')}"
                )
                st.text_area(
                    "Reference transcript extracted from TextGrid",
                    value=textgrid_reference_info.get("reference_transcript", ""),
                    height=100,
                    key=f"textgrid_reference_{speaker_id}_{file_name}",
                )
            elif textgrid_reference_info.get("error"):
                st.warning(
                    f"Could not extract TextGrid reference transcript: "
                    f"{textgrid_reference_info.get('error')}"
                )

        except Exception as e:
            st.warning(f"TextGrid transcript extraction failed: {e}")

    # --------------------------------------------------------
    # Timestamped transcript
    # --------------------------------------------------------

    with st.expander("Timestamped Transcript"):
        if segments:
            for segment in segments:
                st.write(
                    f"[{segment['start']:.2f}s - {segment['end']:.2f}s] "
                    f"{segment['text']}"
                )
        else:
            st.write("No timestamped segments available.")

    # --------------------------------------------------------
    # Accuracy checker
    # --------------------------------------------------------

    latest_accuracy_info = {}

    if run_accuracy_test and transcript:
        latest_accuracy_info = display_accuracy_checker(
            reference_key=f"reference_text_{speaker_id}_{file_name}",
            speaker_id=speaker_id,
            transcript=transcript,
        )

    # --------------------------------------------------------
    # Acoustic/prosodic analysis
    # --------------------------------------------------------

    acoustic_df = None
    highest_f0_sound_info = {}
    ap_ip_phonetic_results = {}
    prominence_material_results = {}
    interrogativity_marker_statement = ""
    pitch_image_path = None

    if run_acoustic_analysis and run_praat_module:
        st.subheader("Praat / Acoustic and Prosodic Analysis")

        try:
            global_results = analyze_audio_with_praat(audio_path)

            final_results = analyze_final_pitch_movement(audio_path)

            tune_results = analyze_prominence_and_tune(
                audio_path,
                transcript=sentence_for_analysis,
            )

            alignment_results = analyze_final_syllable_alignment(
                audio_path,
                final_syllable_window=final_syllable_window,
            )

            textgrid_alignment_results = None
            final_interval = None

            # ------------------------------------------------
            # TextGrid-based analysis
            # ------------------------------------------------

            if textgrid_path:
                if selected_textgrid_tier:
                    tier_to_use = selected_textgrid_tier
                else:
                    tier_to_use = find_best_tier_name(textgrid_path)

                final_interval = get_final_interval_from_textgrid(
                    textgrid_path,
                    tier_name=tier_to_use,
                )

                textgrid_alignment_results = analyze_textgrid_final_interval_alignment(
                    audio_path,
                    final_interval,
                )

                # F0 peak → word/syllable/phone carrying prominence
                try:
                    peak_time_for_prominence = textgrid_alignment_results.get(
                        "textgrid_f0_peak_time_in_interval"
                    )

                    if peak_time_for_prominence is not None:
                        prominence_material_results = get_prominence_material_at_time(
                            textgrid_path,
                            peak_time_for_prominence,
                        )

                        prominence_material_results["prominence_f0_peak_time"] = (
                            peak_time_for_prominence
                        )

                        prominence_material_results["prominence_f0_peak_value_hz"] = (
                            textgrid_alignment_results.get(
                                "textgrid_f0_peak_value_in_interval_hz"
                            )
                        )

                        interrogativity_marker_statement = (
                            build_interrogativity_marker_statement(
                                prominence_material_results,
                                tune_decision=textgrid_alignment_results.get(
                                    "textgrid_lh_or_hh_tune_decision", ""
                                ),
                                domain=tune_results.get("prosodic_domain", ""),
                            )
                        )
                    else:
                        prominence_material_results = {
                            "prominence_lookup_status": "No F0 peak time available.",
                        }

                except Exception as e:
                    prominence_material_results = {
                        "prominence_lookup_status": str(e),
                    }

                # Highest F0 sound/interval using MAU when available
                try:
                    tier_names = get_tier_names(textgrid_path)
                    tier_names_lower = {name.lower(): name for name in tier_names}

                    if "mau" in tier_names_lower:
                        highest_f0_tier = tier_names_lower["mau"]
                    elif "mas" in tier_names_lower:
                        highest_f0_tier = tier_names_lower["mas"]
                    else:
                        highest_f0_tier = tier_to_use

                    peak_time_for_sound = textgrid_alignment_results.get(
                        "textgrid_f0_peak_time_in_interval"
                    )

                    if peak_time_for_sound is not None:
                        highest_interval = get_interval_at_time(
                            textgrid_path,
                            peak_time_for_sound,
                            tier_name=highest_f0_tier,
                        )

                        highest_f0_sound_info = {
                            "highest_f0_tier": highest_interval.get("tier_name"),
                            "highest_f0_sound_label": highest_interval.get("label"),
                            "highest_f0_sound_start": highest_interval.get("start"),
                            "highest_f0_sound_end": highest_interval.get("end"),
                            "highest_f0_time": peak_time_for_sound,
                            "highest_f0_value_hz": textgrid_alignment_results.get(
                                "textgrid_f0_peak_value_in_interval_hz"
                            ),
                            "highest_f0_interval_error": highest_interval.get("error"),
                        }
                    else:
                        highest_f0_sound_info = {
                            "highest_f0_tier": highest_f0_tier,
                            "highest_f0_sound_label": "",
                            "highest_f0_sound_start": None,
                            "highest_f0_sound_end": None,
                            "highest_f0_time": None,
                            "highest_f0_value_hz": None,
                            "highest_f0_interval_error": "No F0 peak time available.",
                        }

                except Exception as e:
                    highest_f0_sound_info = {
                        "highest_f0_interval_error": str(e),
                    }

                # Prosodic region → words/syllables/phones
                try:
                    ap_ip_phonetic_results = get_phonetic_portions_for_ap_ip_final(
                        textgrid_path=textgrid_path,
                        duration=global_results.get("duration_seconds"),
                        final_syllable_window=final_syllable_window,
                        ap_window=tune_results.get("ap_window_seconds", 0.75),
                        ip_window=tune_results.get("ip_window_seconds", 1.20),
                    )
                except Exception as e:
                    ap_ip_phonetic_results = {
                        "ap_ip_phonetic_error": str(e),
                    }

            # ------------------------------------------------
            # Build final dataframe
            # ------------------------------------------------

            acoustic_df = build_acoustic_dataframe(
                global_results,
                final_results,
                tune_results,
                alignment_results,
                textgrid_alignment_results,
            )

            acoustic_df.insert(0, "speaker_id", speaker_id)
            acoustic_df.insert(1, "file_name", file_name)
            acoustic_df.insert(
                2,
                "textgrid_file",
                os.path.basename(textgrid_path) if textgrid_path else "",
            )
            acoustic_df.insert(3, "language_setting", language)
            acoustic_df.insert(4, "sentence_for_analysis", sentence_for_analysis)
            acoustic_df.insert(5, "whisper_transcript", transcript)
            acoustic_df.insert(
                6,
                "textgrid_reference_transcript",
                textgrid_reference_info.get("reference_transcript", ""),
            )
            acoustic_df.insert(
                7,
                "textgrid_reference_tier_used",
                textgrid_reference_info.get("reference_tier_used", ""),
            )
            acoustic_df.insert(
                8,
                "textgrid_reference_source",
                textgrid_reference_info.get("reference_source", ""),
            )
            acoustic_df.insert(9, "phonetic_transcription", phonetic_transcription)
            acoustic_df.insert(10, "estimated_final_unit", estimated_final_syllable)
            acoustic_df.insert(11, "phonetic_engine_requested", phonetic_engine)
            acoustic_df.insert(12, "phonetic_engine_used", phonetic_engine_used)
            acoustic_df.insert(13, "phonetic_language_code_used", phonetic_language_code_used)
            acoustic_df.insert(14, "phonetic_fallback_used", phonetic_fallback_used)
            acoustic_df.insert(15, "phonetic_attempted_engines", phonetic_attempted_engines)
            acoustic_df.insert(16, "phonetic_reliability_note", phonetic_reliability_note)
            acoustic_df.insert(17, "phonetic_error", phonetic_error)

            for key, value in highest_f0_sound_info.items():
                acoustic_df[key] = value

            for key, value in ap_ip_phonetic_results.items():
                acoustic_df[key] = value

            for key, value in prominence_material_results.items():
                acoustic_df[key] = value

            acoustic_df["interrogativity_marker_statement"] = (
                interrogativity_marker_statement
            )

            for key, value in latest_accuracy_info.items():
                acoustic_df[key] = value

            st.markdown("### Full Acoustic Measurement Table")
            st.dataframe(acoustic_df, use_container_width=True)

            contour_label = final_results.get("contour_label", "N/A")
            st.info(f"Estimated final contour: {contour_label}")

            # ------------------------------------------------
            # Interrogativity/prominence/tune
            # ------------------------------------------------

            st.subheader("Interrogativity, Prominence, and Tune Interpretation")

            col_tune1, col_tune2 = st.columns(2)

            with col_tune1:
                st.markdown("**Interrogativity marking**")
                st.write(tune_results.get("interrogativity_marking", "N/A"))

                st.markdown("**Prosodic domain**")
                st.write(tune_results.get("prosodic_domain", "N/A"))

            with col_tune2:
                st.markdown("**Prominence location**")
                st.write(tune_results.get("prominence_location", "N/A"))

                st.markdown("**Tune label candidate**")
                st.write(tune_results.get("tune_label_candidate", "N/A"))

            # ------------------------------------------------
            # AP/IP/final syllable measurements
            # ------------------------------------------------

            st.markdown("### Approximate AP/IP/Final Syllable Measurements")

            ap_ip_table = {
                "Region": [
                    "Final syllable-like region",
                    "Final Accentual Phrase region",
                    "Final Intonational Phrase region",
                ],
                "Window": [
                    f"{tune_results.get('final_syllable_window_seconds')} sec",
                    f"{tune_results.get('ap_window_seconds')} sec",
                    f"{tune_results.get('ip_window_seconds')} sec",
                ],
                "F0 change Hz": [
                    tune_results.get("final_syllable_f0_change_hz"),
                    tune_results.get("ap_final_f0_change_hz"),
                    tune_results.get("ip_final_f0_change_hz"),
                ],
                "Slope Hz/sec": [
                    tune_results.get("final_syllable_slope_hz_per_sec"),
                    tune_results.get("ap_final_slope_hz_per_sec"),
                    tune_results.get("ip_final_slope_hz_per_sec"),
                ],
            }

            st.dataframe(ap_ip_table, use_container_width=True)

            # ------------------------------------------------
            # Prosodic domain → words/syllables/phones
            # ------------------------------------------------

            if ap_ip_phonetic_results:
                st.markdown(
                    "### Words, Syllables, and Phones Corresponding to AP/IP/Final Syllable Regions"
                )

                ap_ip_phonetic_table = {
                    "Prosodic region": [
                        "Final syllable-like region",
                        "Final Accentual Phrase region",
                        "Final Intonational Phrase region",
                    ],
                    "Time window": [
                        (
                            f"{ap_ip_phonetic_results.get('final_syllable_region_start')} "
                            f"– {ap_ip_phonetic_results.get('final_syllable_region_end')} sec"
                        ),
                        (
                            f"{ap_ip_phonetic_results.get('ap_region_start')} "
                            f"– {ap_ip_phonetic_results.get('ap_region_end')} sec"
                        ),
                        (
                            f"{ap_ip_phonetic_results.get('ip_region_start')} "
                            f"– {ap_ip_phonetic_results.get('ip_region_end')} sec"
                        ),
                    ],
                    "Corresponding word(s)": [
                        ap_ip_phonetic_results.get(
                            "final_syllable_region_word_labels"
                        ),
                        ap_ip_phonetic_results.get("ap_region_word_labels"),
                        ap_ip_phonetic_results.get("ip_region_word_labels"),
                    ],
                    "Corresponding syllable(s)": [
                        ap_ip_phonetic_results.get(
                            "final_syllable_region_syllable_labels"
                        ),
                        ap_ip_phonetic_results.get("ap_region_syllable_labels"),
                        ap_ip_phonetic_results.get("ip_region_syllable_labels"),
                    ],
                    "Corresponding phone/sound sequence": [
                        ap_ip_phonetic_results.get(
                            "final_syllable_region_phone_labels"
                        ),
                        ap_ip_phonetic_results.get("ap_region_phone_labels"),
                        ap_ip_phonetic_results.get("ip_region_phone_labels"),
                    ],
                }

                st.dataframe(ap_ip_phonetic_table, use_container_width=True)

                with st.expander("Detailed AP/IP interval labels with timings"):
                    detailed_ap_ip_table = {
                        "Prosodic region": [
                            "Final syllable-like region",
                            "Final Accentual Phrase region",
                            "Final Intonational Phrase region",
                        ],
                        "Word intervals": [
                            ap_ip_phonetic_results.get(
                                "final_syllable_region_word_intervals"
                            ),
                            ap_ip_phonetic_results.get("ap_region_word_intervals"),
                            ap_ip_phonetic_results.get("ip_region_word_intervals"),
                        ],
                        "Syllable intervals": [
                            ap_ip_phonetic_results.get(
                                "final_syllable_region_syllable_intervals"
                            ),
                            ap_ip_phonetic_results.get("ap_region_syllable_intervals"),
                            ap_ip_phonetic_results.get("ip_region_syllable_intervals"),
                        ],
                        "Phone intervals": [
                            ap_ip_phonetic_results.get(
                                "final_syllable_region_phone_intervals"
                            ),
                            ap_ip_phonetic_results.get("ap_region_phone_intervals"),
                            ap_ip_phonetic_results.get("ip_region_phone_intervals"),
                        ],
                    }

                    st.dataframe(detailed_ap_ip_table, use_container_width=True)

                st.caption(
                    f"Word tier used: "
                    f"{ap_ip_phonetic_results.get('word_tier_used_for_ap_ip', 'N/A')} | "
                    f"Syllable tier used: "
                    f"{ap_ip_phonetic_results.get('syllable_tier_used_for_ap_ip', 'N/A')} | "
                    f"Phone/sound tier used: "
                    f"{ap_ip_phonetic_results.get('phonetic_tier_used_for_ap_ip', 'N/A')}"
                )

            # ------------------------------------------------
            # F0 peak → prominence/interrogativity marker
            # ------------------------------------------------

            if prominence_material_results:
                st.markdown(
                    "### Phonetic Location of Prominence / F0 Peak Marking Interrogativity"
                )

                prominence_table = {
                    "Level": [
                        "Word carrying F0 peak",
                        "Syllable carrying F0 peak",
                        "Phone/sound carrying F0 peak",
                        "Combined prominence transcription",
                        "F0 peak time",
                        "F0 peak value",
                        "Status",
                    ],
                    "Label / Value": [
                        prominence_material_results.get("prominence_word_label"),
                        prominence_material_results.get("prominence_syllable_label"),
                        prominence_material_results.get("prominence_phone_label"),
                        prominence_material_results.get(
                            "prominence_combined_transcription"
                        ),
                        prominence_material_results.get("prominence_f0_peak_time"),
                        prominence_material_results.get("prominence_f0_peak_value_hz"),
                        prominence_material_results.get("prominence_lookup_status"),
                    ],
                    "Tier / Unit": [
                        prominence_material_results.get("prominence_word_tier"),
                        prominence_material_results.get("prominence_syllable_tier"),
                        prominence_material_results.get("prominence_phone_tier"),
                        "",
                        "seconds",
                        "Hz",
                        "",
                    ],
                }

                st.dataframe(prominence_table, use_container_width=True)

                if interrogativity_marker_statement:
                    st.success(interrogativity_marker_statement)

            # ------------------------------------------------
            # Approximate final syllable F0 alignment
            # ------------------------------------------------

            st.markdown("### Approximate Final Syllable F0 Alignment Measurements")

            alignment_table = {
                "Measurement": [
                    "Time of final syllable onset",
                    "Time of final syllable midpoint",
                    "Time of final syllable offset",
                    "Time of phrase boundary",
                    "F0 at start of final syllable",
                    "F0 at midpoint of final syllable",
                    "F0 at end of final syllable",
                    "F0 at phrase boundary",
                    "Nearest voiced time before final syllable end",
                    "Nearest voiced F0 before final syllable end",
                    "Nearest voiced time before phrase boundary",
                    "Nearest voiced F0 before phrase boundary",
                    "Time of F0 peak",
                    "Value of F0 peak",
                ],
                "Value": [
                    alignment_results.get("final_syllable_onset_time"),
                    alignment_results.get("final_syllable_midpoint_time"),
                    alignment_results.get("final_syllable_offset_time"),
                    alignment_results.get("phrase_boundary_time"),
                    alignment_results.get("f0_at_final_syllable_start_hz"),
                    alignment_results.get("f0_at_final_syllable_midpoint_hz"),
                    alignment_results.get("f0_at_final_syllable_end_hz"),
                    alignment_results.get("f0_at_phrase_boundary_hz"),
                    alignment_results.get(
                        "nearest_voiced_time_before_final_syllable_end"
                    ),
                    alignment_results.get(
                        "nearest_voiced_f0_before_final_syllable_end_hz"
                    ),
                    alignment_results.get(
                        "nearest_voiced_time_before_phrase_boundary"
                    ),
                    alignment_results.get(
                        "nearest_voiced_f0_before_phrase_boundary_hz"
                    ),
                    alignment_results.get("f0_peak_time_in_final_syllable"),
                    alignment_results.get("f0_peak_value_in_final_syllable_hz"),
                ],
                "Unit": [
                    "seconds",
                    "seconds",
                    "seconds",
                    "seconds",
                    "Hz",
                    "Hz",
                    "Hz",
                    "Hz",
                    "seconds",
                    "Hz",
                    "seconds",
                    "Hz",
                    "seconds",
                    "Hz",
                ],
            }

            st.dataframe(alignment_table, use_container_width=True)

            # ------------------------------------------------
            # TextGrid-based final interval alignment
            # ------------------------------------------------

            if textgrid_path and final_interval and textgrid_alignment_results:
                st.markdown("### TextGrid-Based Final Interval Alignment")

                textgrid_table = {
                    "Measurement": [
                        "TextGrid tier used",
                        "Final interval label",
                        "Final interval onset",
                        "Final interval midpoint",
                        "Final interval offset",
                        "Phrase boundary time",
                        "F0 at interval start",
                        "F0 at interval midpoint",
                        "F0 at interval end",
                        "F0 at phrase boundary",
                        "Nearest voiced time before interval end",
                        "Nearest voiced F0 before interval end",
                        "Nearest voiced time before phrase boundary",
                        "Nearest voiced F0 before phrase boundary",
                        "Time of F0 peak in interval",
                        "Value of F0 peak in interval",
                    ],
                    "Value": [
                        textgrid_alignment_results.get("textgrid_tier_used"),
                        textgrid_alignment_results.get("textgrid_final_interval_label"),
                        textgrid_alignment_results.get("textgrid_final_interval_start"),
                        textgrid_alignment_results.get(
                            "textgrid_final_interval_midpoint"
                        ),
                        textgrid_alignment_results.get("textgrid_final_interval_end"),
                        textgrid_alignment_results.get("textgrid_phrase_boundary_time"),
                        textgrid_alignment_results.get(
                            "textgrid_f0_at_interval_start_hz"
                        ),
                        textgrid_alignment_results.get(
                            "textgrid_f0_at_interval_midpoint_hz"
                        ),
                        textgrid_alignment_results.get(
                            "textgrid_f0_at_interval_end_hz"
                        ),
                        textgrid_alignment_results.get(
                            "textgrid_f0_at_phrase_boundary_hz"
                        ),
                        textgrid_alignment_results.get(
                            "textgrid_nearest_voiced_time_before_interval_end"
                        ),
                        textgrid_alignment_results.get(
                            "textgrid_nearest_voiced_f0_before_interval_end_hz"
                        ),
                        textgrid_alignment_results.get(
                            "textgrid_nearest_voiced_time_before_phrase_boundary"
                        ),
                        textgrid_alignment_results.get(
                            "textgrid_nearest_voiced_f0_before_phrase_boundary_hz"
                        ),
                        textgrid_alignment_results.get(
                            "textgrid_f0_peak_time_in_interval"
                        ),
                        textgrid_alignment_results.get(
                            "textgrid_f0_peak_value_in_interval_hz"
                        ),
                    ],
                    "Unit": [
                        "",
                        "",
                        "seconds",
                        "seconds",
                        "seconds",
                        "seconds",
                        "Hz",
                        "Hz",
                        "Hz",
                        "Hz",
                        "seconds",
                        "Hz",
                        "seconds",
                        "Hz",
                        "seconds",
                        "Hz",
                    ],
                }

                st.dataframe(textgrid_table, use_container_width=True)

                st.markdown("### TextGrid-Based L* H% vs H* H% Interpretation")
                st.write(
                    textgrid_alignment_results.get(
                        "textgrid_alignment_interpretation",
                        "No TextGrid alignment interpretation available.",
                    )
                )
                st.info(
                    textgrid_alignment_results.get(
                        "textgrid_lh_or_hh_tune_decision",
                        "No TextGrid tune decision available.",
                    )
                )

            # ------------------------------------------------
            # Highest-F0 sound/interval
            # ------------------------------------------------

            if highest_f0_sound_info:
                st.markdown("### Sound / Interval Carrying the Highest F0")

                highest_f0_table = {
                    "Measurement": [
                        "Tier used",
                        "Sound/interval label",
                        "Sound/interval start",
                        "Sound/interval end",
                        "Time of highest F0",
                        "Highest F0 value",
                        "Error/status",
                    ],
                    "Value": [
                        highest_f0_sound_info.get("highest_f0_tier"),
                        highest_f0_sound_info.get("highest_f0_sound_label"),
                        highest_f0_sound_info.get("highest_f0_sound_start"),
                        highest_f0_sound_info.get("highest_f0_sound_end"),
                        highest_f0_sound_info.get("highest_f0_time"),
                        highest_f0_sound_info.get("highest_f0_value_hz"),
                        highest_f0_sound_info.get("highest_f0_interval_error"),
                    ],
                    "Unit": [
                        "",
                        "",
                        "seconds",
                        "seconds",
                        "seconds",
                        "Hz",
                        "",
                    ],
                }

                st.dataframe(highest_f0_table, use_container_width=True)

            # ------------------------------------------------
            # Approximate L* H% vs H* H%
            # ------------------------------------------------

            st.markdown("### Approximate L* H% vs H* H% Alignment Interpretation")

            st.write(
                alignment_results.get(
                    "pitch_accent_alignment_interpretation",
                    "No alignment interpretation available.",
                )
            )

            st.info(
                alignment_results.get(
                    "lh_or_hh_tune_decision",
                    "No tune decision available.",
                )
            )

        except Exception as e:
            st.error(f"Praat acoustic/prosodic analysis failed: {e}")

        # ----------------------------------------------------
        # Pitch contour plot + downloadable PNG
        # ----------------------------------------------------

        try:
            st.subheader("Pitch / F0 Contour")

            pitch_df = extract_pitch_track(audio_path)

            fig, ax = plt.subplots()
            ax.plot(pitch_df["time_seconds"], pitch_df["f0_hz"])
            ax.set_xlabel("Time (seconds)")
            ax.set_ylabel("F0 (Hz)")
            ax.set_title(f"Pitch Contour - Speaker {speaker_id}")
            st.pyplot(fig)

            pitch_image_path = save_pitch_contour_image(
                pitch_df,
                speaker_id=speaker_id,
                filename=f"{speaker_id}_pitch_contour.png",
            )

            stable_download_button(
                "Download Pitch/F0 Contour Image",
                data=read_binary_file(pitch_image_path),
                file_name=f"{speaker_id}_pitch_contour.png",
                mime="image/png",
            )

        except Exception as e:
            st.error(f"Pitch contour plotting failed: {e}")

    # --------------------------------------------------------
    # Export results
    # --------------------------------------------------------

    st.subheader("Export Results")

    try:
        txt_path = save_transcript_txt(
            transcript,
            filename=f"{speaker_id}_transcript.txt",
        )

        docx_path = save_transcript_docx(
            transcript,
            filename=f"{speaker_id}_transcript.docx",
        )

        pdf_path = save_transcript_pdf(
            transcript,
            filename=f"{speaker_id}_transcript.pdf",
        )

        srt_path = save_srt(
            segments,
            filename=f"{speaker_id}_subtitles.srt",
        )

        short_report_path = save_transcription_report_txt(
            speaker_id=speaker_id,
            file_name=file_name,
            orthographic_transcript=transcript,
            phonetic_transcription=phonetic_transcription,
            highest_f0_info=highest_f0_sound_info,
            filename=f"{speaker_id}_short_transcription_report.txt",
        )

        full_txt_path = save_full_analysis_txt(
            speaker_id=speaker_id,
            file_name=file_name,
            orthographic_transcript=transcript,
            phonetic_transcription=phonetic_transcription,
            acoustic_df=acoustic_df,
            pitch_image_path=pitch_image_path,
            accuracy_info=latest_accuracy_info,
            filename=f"{speaker_id}_full_analysis_report.txt",
        )

        full_docx_path = save_full_analysis_docx(
            speaker_id=speaker_id,
            file_name=file_name,
            orthographic_transcript=transcript,
            phonetic_transcription=phonetic_transcription,
            acoustic_df=acoustic_df,
            pitch_image_path=pitch_image_path,
            accuracy_info=latest_accuracy_info,
            filename=f"{speaker_id}_full_analysis_report.docx",
        )

        full_pdf_path = save_full_analysis_pdf(
            speaker_id=speaker_id,
            file_name=file_name,
            orthographic_transcript=transcript,
            phonetic_transcription=phonetic_transcription,
            acoustic_df=acoustic_df,
            pitch_image_path=pitch_image_path,
            accuracy_info=latest_accuracy_info,
            filename=f"{speaker_id}_full_analysis_report.pdf",
        )

        full_excel_path = save_full_analysis_excel(
            speaker_id=speaker_id,
            file_name=file_name,
            orthographic_transcript=transcript,
            phonetic_transcription=phonetic_transcription,
            acoustic_df=acoustic_df,
            accuracy_info=latest_accuracy_info,
            filename=f"{speaker_id}_full_analysis_report.xlsx",
        )

        full_csv_path = save_full_analysis_csv(
            acoustic_df=acoustic_df,
            speaker_id=speaker_id,
            filename=f"{speaker_id}_full_analysis_report.csv",
        )

        st.markdown("### Basic transcript exports")

        col_a, col_b, col_c, col_d = st.columns(4)

        with col_a:
            stable_download_button(
                "Download Transcript TXT",
                data=read_binary_file(txt_path),
                file_name=f"{speaker_id}_transcript.txt",
                mime="text/plain",
            )

        with col_b:
            stable_download_button(
                "Download Transcript DOCX",
                data=read_binary_file(docx_path),
                file_name=f"{speaker_id}_transcript.docx",
                mime=(
                    "application/vnd.openxmlformats-officedocument."
                    "wordprocessingml.document"
                ),
            )

        with col_c:
            stable_download_button(
                "Download Transcript PDF",
                data=read_binary_file(pdf_path),
                file_name=f"{speaker_id}_transcript.pdf",
                mime="application/pdf",
            )

        with col_d:
            stable_download_button(
                "Download SRT",
                data=read_binary_file(srt_path),
                file_name=f"{speaker_id}_subtitles.srt",
                mime="text/plain",
            )

        st.markdown("### Coherent full analysis reports")

        col_e, col_f, col_g, col_h, col_i = st.columns(5)

        with col_e:
            stable_download_button(
                "Full Report TXT",
                data=read_binary_file(full_txt_path),
                file_name=f"{speaker_id}_full_analysis_report.txt",
                mime="text/plain",
            )

        with col_f:
            stable_download_button(
                "Full Report DOCX",
                data=read_binary_file(full_docx_path),
                file_name=f"{speaker_id}_full_analysis_report.docx",
                mime=(
                    "application/vnd.openxmlformats-officedocument."
                    "wordprocessingml.document"
                ),
            )

        with col_g:
            stable_download_button(
                "Full Report PDF",
                data=read_binary_file(full_pdf_path),
                file_name=f"{speaker_id}_full_analysis_report.pdf",
                mime="application/pdf",
            )

        with col_h:
            stable_download_button(
                "Full Report Excel",
                data=read_binary_file(full_excel_path),
                file_name=f"{speaker_id}_full_analysis_report.xlsx",
                mime=(
                    "application/vnd.openxmlformats-officedocument."
                    "spreadsheetml.sheet"
                ),
            )

        with col_i:
            stable_download_button(
                "Full Report CSV",
                data=read_binary_file(full_csv_path),
                file_name=f"{speaker_id}_full_analysis_report.csv",
                mime="text/csv",
            )

        st.markdown("### Short report")

        stable_download_button(
            "Download Short Orthographic + Phonetic Report",
            data=read_binary_file(short_report_path),
            file_name=f"{speaker_id}_short_transcription_report.txt",
            mime="text/plain",
        )

    except Exception as e:
        st.error(f"Transcript/report export failed: {e}")

    if acoustic_df is not None:
        try:
            csv_path = save_acoustic_csv(
                acoustic_df,
                filename=f"{speaker_id}_acoustic_analysis.csv",
            )

            excel_path = save_acoustic_excel(
                acoustic_df,
                filename=f"{speaker_id}_acoustic_analysis.xlsx",
            )

            col_j, col_k = st.columns(2)

            with col_j:
                stable_download_button(
                    "Download Acoustic CSV",
                    data=read_binary_file(csv_path),
                    file_name=f"{speaker_id}_acoustic_analysis.csv",
                    mime="text/csv",
                )

            with col_k:
                stable_download_button(
                    "Download Acoustic Excel",
                    data=read_binary_file(excel_path),
                    file_name=f"{speaker_id}_acoustic_analysis.xlsx",
                    mime=(
                        "application/vnd.openxmlformats-officedocument."
                        "spreadsheetml.sheet"
                    ),
                )

        except Exception as e:
            st.error(f"Acoustic export failed: {e}")

    if acoustic_df is not None:
        st.session_state.analysis_results.append(acoustic_df)

    return acoustic_df


# ============================================================
# Input mode: Upload audio/video
# ============================================================

if input_mode == "Upload audio/video":
    st.header("Upload Audio or Video")
    st.markdown('<div id="input"></div>', unsafe_allow_html=True)

    uploaded_files = st.file_uploader(
        "Upload one or more audio/video files",
        type=[
            "wav",
            "mp3",
            "m4a",
            "aac",
            "flac",
            "ogg",
            "opus",
            "mp4",
            "mov",
            "mkv",
            "webm",
            "avi",
            "m4v",
        ],
        accept_multiple_files=True,
    )

    manual_speaker_id = ""

    if uploaded_files:
        st.success(f"{len(uploaded_files)} file(s) uploaded.")

        st.info(
            """
            Batch mode is enabled. The app will process each uploaded file, extract
            a speaker ID from the filename, and combine all speaker-level acoustic,
            phonetic, prosodic, and transcription variables into one master dataframe.
            """
        )

        if len(uploaded_files) == 1:
            suggested_id = extract_speaker_id_from_filename(uploaded_files[0].name)
            manual_speaker_id = st.text_input(
                "Speaker ID override for this file",
                value=suggested_id,
            )

        batch_prefix = st.text_input(
            "Batch output filename prefix",
            value="batch_audio_video_acoustic_analysis",
            help="This prefix will be used for the combined CSV, Excel, TXT, and DOCX downloads.",
        )

        show_individual_outputs = st.checkbox(
            "Show detailed output for each file while processing",
            value=True,
            help=(
                "Turn this off for large batches to keep the interface cleaner. "
                "The combined batch dataframe will still be produced."
            ),
        )

        if st.button("Run Stable Batch Analysis for Uploaded File(s)"):
            all_batch_results = []
            batch_errors = []

            progress = st.progress(0)
            status_box = st.empty()

            total_files = len(uploaded_files)

            for index, uploaded_file in enumerate(uploaded_files, start=1):
                status_box.info(
                    f"Processing file {index}/{total_files}: {uploaded_file.name}"
                )

                speaker_override = manual_speaker_id if len(uploaded_files) == 1 else ""

                try:
                    input_path = save_uploaded_file(uploaded_file)

                    if show_individual_outputs:
                        st.divider()
                        st.markdown(f"## Processing: {uploaded_file.name}")

                    result_df = process_media(
                        input_path,
                        original_file_name=uploaded_file.name,
                        manual_speaker_id=speaker_override,
                    )

                    if result_df is not None and not result_df.empty:
                        result_df["analysis_status"] = "completed"
                        result_df["analysis_error"] = ""
                        all_batch_results.append(result_df)
                    else:
                        speaker_id = extract_speaker_id_from_filename(uploaded_file.name)
                        fail_df = make_failed_batch_row(
                            file_name=uploaded_file.name,
                            speaker_id=speaker_id,
                            error_message="No dataframe returned by process_media.",
                        )
                        all_batch_results.append(fail_df)
                        batch_errors.append(
                            {
                                "file_name": uploaded_file.name,
                                "error": "No dataframe returned by process_media.",
                            }
                        )

                except Exception as e:
                    speaker_id = extract_speaker_id_from_filename(uploaded_file.name)
                    error_message = str(e)

                    fail_df = make_failed_batch_row(
                        file_name=uploaded_file.name,
                        speaker_id=speaker_id,
                        error_message=error_message,
                    )

                    all_batch_results.append(fail_df)
                    batch_errors.append(
                        {
                            "file_name": uploaded_file.name,
                            "error": error_message,
                        }
                    )

                    st.error(f"Failed to process {uploaded_file.name}: {error_message}")

                progress.progress(index / total_files)

            batch_df = build_master_batch_dataframe(all_batch_results)

            st.session_state.last_batch_df = batch_df
            st.session_state.batch_errors = batch_errors

            status_box.success("Batch analysis completed.")

            if batch_errors:
                with st.expander("Batch processing errors", expanded=True):
                    st.dataframe(pd.DataFrame(batch_errors), use_container_width=True)

            st.divider()
            st.header("Final Combined Batch Results")
            render_batch_download_buttons(batch_df, prefix=batch_prefix)




# ============================================================
# Input mode: Upload audio + TextGrid pairs
# ============================================================

elif input_mode == "Upload audio + TextGrid pairs":
    st.header("Upload Audio Files with Corresponding TextGrid Files")
    st.markdown('<div id="textgrid"></div>', unsafe_allow_html=True)

    st.info(
        """
        Upload matching audio and TextGrid files. The app matches them by filename stem.

        Example:
        maabh1tw1.wav
        maabh1tw1.TextGrid

        Each matched pair becomes one row in the final combined batch dataframe.
        """
    )

    uploaded_audio_files = st.file_uploader(
        "Upload audio files",
        type=[
            "wav",
            "mp3",
            "m4a",
            "aac",
            "flac",
            "ogg",
            "opus",
            "mp4",
            "mov",
            "mkv",
            "webm",
            "avi",
            "m4v",
        ],
        accept_multiple_files=True,
        key="audio_textgrid_audio_upload",
    )

    uploaded_textgrid_files = st.file_uploader(
        "Upload corresponding TextGrid files",
        type=["TextGrid", "textgrid"],
        accept_multiple_files=True,
        key="audio_textgrid_textgrid_upload",
    )

    selected_tier = ""

    if uploaded_audio_files and uploaded_textgrid_files:
        st.success(
            f"{len(uploaded_audio_files)} audio file(s) and "
            f"{len(uploaded_textgrid_files)} TextGrid file(s) uploaded."
        )

        saved_audio_paths = []
        saved_textgrid_paths = []

        for audio_file in uploaded_audio_files:
            saved_audio_paths.append(save_uploaded_file(audio_file))

        for tg_file in uploaded_textgrid_files:
            saved_textgrid_paths.append(save_uploaded_file(tg_file))

        pairs = match_audio_textgrid_pairs(saved_audio_paths, saved_textgrid_paths)

        if not pairs:
            st.error(
                """
                No matching audio/TextGrid pairs found.
                Make sure the filenames match before the extension.

                Example:
                speaker01.wav
                speaker01.TextGrid
                """
            )
        else:
            st.subheader("Matched Audio/TextGrid Pairs")

            pair_table = []
            for pair in pairs:
                pair_table.append(
                    {
                        "stem": pair["stem"],
                        "audio": os.path.basename(pair["audio_path"]),
                        "textgrid": os.path.basename(pair["textgrid_path"]),
                        "speaker_id": extract_speaker_id_from_filename(
                            pair["audio_path"]
                        ),
                    }
                )

            st.dataframe(pd.DataFrame(pair_table), use_container_width=True)

            try:
                first_tg = pairs[0]["textgrid_path"]
                tier_names = get_tier_names(first_tg)

                selected_tier = st.selectbox(
                    "Choose TextGrid tier for final interval extraction",
                    ["Auto-detect best tier"] + tier_names,
                    help=(
                        "Choose a syllable tier if available. "
                        "For PFC/WebMAUS, MAS or syllable tiers are usually preferable. "
                        "If not available, choose word/ORT-MAU."
                    ),
                )

                if selected_tier == "Auto-detect best tier":
                    selected_tier = ""

            except Exception as e:
                st.warning(f"Could not read tier names from first TextGrid: {e}")
                selected_tier = ""

            batch_prefix = st.text_input(
                "TextGrid batch output filename prefix",
                value="batch_textgrid_acoustic_analysis",
                help="This prefix will be used for the combined CSV, Excel, TXT, and DOCX downloads.",
            )

            show_individual_outputs = st.checkbox(
                "Show detailed output for each TextGrid pair while processing",
                value=True,
                help=(
                    "Turn this off for large batches to keep the interface cleaner. "
                    "The combined batch dataframe will still be produced."
                ),
            )

            if st.button("Run Stable Batch Analysis for Audio + TextGrid Pair(s)"):
                all_batch_results = []
                batch_errors = []

                progress = st.progress(0)
                status_box = st.empty()

                total_pairs = len(pairs)

                for index, pair in enumerate(pairs, start=1):
                    audio_path = pair["audio_path"]
                    textgrid_path = pair["textgrid_path"]
                    original_file_name = os.path.basename(audio_path)
                    speaker_id = extract_speaker_id_from_filename(audio_path)

                    status_box.info(
                        f"Processing pair {index}/{total_pairs}: {pair['stem']}"
                    )

                    try:
                        if show_individual_outputs:
                            st.divider()
                            st.markdown(f"## Processing Pair: {pair['stem']}")

                        result_df = process_media(
                            audio_path,
                            original_file_name=original_file_name,
                            manual_speaker_id="",
                            textgrid_path=textgrid_path,
                            selected_textgrid_tier=selected_tier,
                        )

                        if result_df is not None and not result_df.empty:
                            result_df["analysis_status"] = "completed"
                            result_df["analysis_error"] = ""
                            all_batch_results.append(result_df)
                        else:
                            fail_df = make_failed_batch_row(
                                file_name=original_file_name,
                                speaker_id=speaker_id,
                                error_message="No dataframe returned by process_media.",
                            )
                            fail_df["textgrid_file"] = os.path.basename(textgrid_path)
                            all_batch_results.append(fail_df)
                            batch_errors.append(
                                {
                                    "file_name": original_file_name,
                                    "textgrid_file": os.path.basename(textgrid_path),
                                    "error": "No dataframe returned by process_media.",
                                }
                            )

                    except Exception as e:
                        error_message = str(e)

                        fail_df = make_failed_batch_row(
                            file_name=original_file_name,
                            speaker_id=speaker_id,
                            error_message=error_message,
                        )
                        fail_df["textgrid_file"] = os.path.basename(textgrid_path)

                        all_batch_results.append(fail_df)
                        batch_errors.append(
                            {
                                "file_name": original_file_name,
                                "textgrid_file": os.path.basename(textgrid_path),
                                "error": error_message,
                            }
                        )

                        st.error(
                            f"Failed to process pair {pair['stem']}: {error_message}"
                        )

                    progress.progress(index / total_pairs)

                batch_df = build_master_batch_dataframe(all_batch_results)

                st.session_state.last_batch_df = batch_df
                st.session_state.batch_errors = batch_errors

                status_box.success("TextGrid batch analysis completed.")

                if batch_errors:
                    with st.expander("TextGrid batch processing errors", expanded=True):
                        st.dataframe(pd.DataFrame(batch_errors), use_container_width=True)

                st.divider()
                st.header("Final Combined TextGrid Batch Results")
                render_batch_download_buttons(batch_df, prefix=batch_prefix)




# ============================================================
# Input mode: Record voice
# ============================================================

elif input_mode == "Record voice":
    st.header("Record Your Voice")

    manual_speaker_id = st.text_input(
        "Speaker ID for this recording",
        value="recorded_speaker",
    )

    recorded_audio = st.audio_input("Record your voice")

    if recorded_audio is not None:
        st.audio(recorded_audio)

        if st.button("Transcribe and Analyze Recording"):
            input_path = save_uploaded_file(recorded_audio)
            process_media(
                input_path,
                original_file_name=recorded_audio.name,
                manual_speaker_id=manual_speaker_id,
            )


# ============================================================
# Input mode: Paste media URL
# ============================================================

elif input_mode == "Paste media URL":
    st.header("Paste Public Media URL")

    st.warning(
        """
        Use this only for media you own, have permission to process,
        or are legally allowed to transcribe. Some websites may block downloads,
        require login, or change their systems.
        """
    )

    manual_speaker_id = st.text_input(
        "Speaker ID for this URL media",
        value="url_speaker",
    )

    media_url = st.text_input(
        "Paste YouTube, Facebook, X/Twitter, TikTok, Instagram, Vimeo, or direct media URL"
    )

    if media_url.strip():
        if st.button("Download, Transcribe, and Analyze URL"):
            try:
                with st.spinner("Downloading media..."):
                    downloaded_path = download_media_from_url(media_url)

                st.success("Media downloaded.")
                process_media(
                    downloaded_path,
                    original_file_name=os.path.basename(downloaded_path),
                    manual_speaker_id=manual_speaker_id,
                )

            except Exception as e:
                st.error(f"Media download failed: {e}")


# ============================================================
# Persistent accuracy checker
# ============================================================

if run_accuracy_test and st.session_state.current_transcript:
    with st.expander("Persistent Accuracy Checker", expanded=False):
        display_accuracy_checker(
            reference_key="persistent_reference_text",
            speaker_id=st.session_state.current_speaker_id or "N/A",
            transcript=st.session_state.current_transcript,
        )


# ============================================================
# Persistent session results
# ============================================================

if st.session_state.analysis_results:
    with st.expander("Previously completed analyses in this session", expanded=False):
        previous_df = pd.concat(st.session_state.analysis_results, ignore_index=True)
        st.dataframe(previous_df, use_container_width=True)

if st.session_state.last_batch_df is not None:
    render_persistent_batch_downloads()

render_global_footer()

# ============================================================
# IntonaSphere AI — PFC Q1–Q3 Prosody Extractor
# ============================================================

st.markdown("---")
st.subheader("PFC Q1–Q3 Prosody Extractor")
st.caption(
    "Run research-ready token-level extraction for PFC-style audio and TextGrid data. "
    "This module extracts F0, final slope, semitone values, intensity, duration, "
    "plateau duration, contour class, and TextGrid diagnostic information."
)

with st.expander("Configure PFC batch extraction", expanded=False):
    pfc_template_path = st.text_input(
        "Token workbook",
        value=str(BASE_DATA_DIR / "PFC_speaker_token_template dissertation.xlsx"),
    )

    pfc_audio_dir = st.text_input(
        "Audio folder",
        value=str(PFC_AUDIO_DIR),
    )

    pfc_textgrid_dir = st.text_input(
        "TextGrid folder",
        value=str(PFC_TEXTGRID_DIR),
    )

    pfc_output_xlsx = st.text_input(
        "Output Excel file",
        value=str(OUTPUT_DIR / "excel" / "PFC_clean_Q1_Q2_Q3_acoustics.xlsx"),
    )

    pfc_output_csv = st.text_input(
        "Output CSV file",
        value=str(OUTPUT_DIR / "csv" / "PFC_clean_Q1_Q2_Q3_acoustics.csv"),
    )

    pfc_tier_choices = st.multiselect(
        "Extraction target",
        [
            "ORT-MAU — final word",
            "MAS — final syllable",
        ],
        default=["ORT-MAU — final word", "MAS — final syllable"],
        help=(
            "Select one or both extraction targets. "
            "ORT-MAU extracts final-word prosody, for example beaulieu. "
            "MAS extracts final-syllable prosody, for example l j 2."
        ),
    )

    if not pfc_tier_choices:
        st.warning("Select at least one extraction target before running the extractor.")

    selected_pfc_tiers = []
    if "ORT-MAU — final word" in pfc_tier_choices:
        selected_pfc_tiers.append(("ORT-MAU", "final_word"))

    if "MAS — final syllable" in pfc_tier_choices:
        selected_pfc_tiers.append(("MAS", "final_syllable"))

    if len(selected_pfc_tiers) == 2:
        st.info("Using ORT-MAU and MAS: IntonaSphere will extract both final-word and final-syllable prosody.")
    elif selected_pfc_tiers and selected_pfc_tiers[0][0] == "ORT-MAU":
        st.info("Using ORT-MAU: IntonaSphere will extract prosody from the final word.")
    elif selected_pfc_tiers and selected_pfc_tiers[0][0] == "MAS":
        st.info("Using MAS: IntonaSphere will extract prosody from the final real syllable, ignoring pauses such as <p:>.")

    col_pf, col_pc = st.columns(2)

    with col_pf:
        pfc_pitch_floor = st.number_input(
            "Pitch floor",
            min_value=40.0,
            max_value=300.0,
            value=75.0,
            step=5.0,
        )

    with col_pc:
        pfc_pitch_ceiling = st.number_input(
            "Pitch ceiling",
            min_value=200.0,
            max_value=900.0,
            value=500.0,
            step=10.0,
        )

    run_pfc_extractor = st.button("Run PFC Q1–Q3 acoustic extraction")

    if run_pfc_extractor:
        try:
            from pathlib import Path
            from modules.research_batch_extractor import run_pfc_token_level_extraction

            if not selected_pfc_tiers:
                st.error("Please select at least one extraction target.")
            else:
                for tier_name, tier_label in selected_pfc_tiers:
                    output_csv_path = Path(pfc_output_csv)
                    output_xlsx_path = Path(pfc_output_xlsx)

                    tier_output_csv = output_csv_path.with_name(
                        output_csv_path.stem + f"_{tier_label}" + output_csv_path.suffix
                    )

                    tier_output_xlsx = output_xlsx_path.with_name(
                        output_xlsx_path.stem + f"_{tier_label}" + output_xlsx_path.suffix
                    )

                    with st.spinner(f"Running {tier_name} extraction..."):
                        pfc_df = run_pfc_token_level_extraction(
                            template_path=pfc_template_path,
                            audio_dir=pfc_audio_dir,
                            textgrid_dir=pfc_textgrid_dir,
                            output_xlsx=str(tier_output_xlsx),
                            output_csv=str(tier_output_csv),
                            preferred_tier=tier_name,
                            pitch_floor=pfc_pitch_floor,
                            pitch_ceiling=pfc_pitch_ceiling,
                        )

                    st.success(f"{tier_name} extraction complete.")
                    st.write(f"{tier_name} rows extracted: {len(pfc_df)}")
                    st.write(f"{tier_name} variables extracted: {len(pfc_df.columns)}")

                    st.dataframe(pfc_df.head(100), use_container_width=True)

                    csv_bytes = pfc_df.to_csv(index=False).encode("utf-8")

                    st.download_button(
                        label=f"Download {tier_name} CSV",
                        data=csv_bytes,
                        file_name=tier_output_csv.name,
                        mime="text/csv",
                    )

                    with open(tier_output_xlsx, "rb") as f:
                        st.download_button(
                            label=f"Download {tier_name} Excel workbook",
                            data=f,
                            file_name=tier_output_xlsx.name,
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        )

        except Exception as e:
            st.error("Extraction failed.")
            st.exception(e)