"""
Language of the IntonaSphere AI app (English / français).

The app's labels, headings and messages are written in English in the code as tr("English text")
and translated from messages/app_fr.json. The language is chosen in the sidebar
("Language / Langue"); its first value comes from the language saved by pipeline/install.py
(~/.intonasphere/config.json), then from the computer's language, then English.
Data (column names, file names, F_ToBI labels, option values) is never translated.
"""
from __future__ import annotations

import json
import locale
import os
from pathlib import Path

import streamlit as st

HERE = Path(__file__).resolve().parent
CATALOG = HERE / "messages" / "app_fr.json"
CONFIG_FILE = Path.home() / ".intonasphere" / "config.json"
LANGS = {"en": "English", "fr": "Français"}


@st.cache_data(show_spinner=False)
def _french() -> dict:
    try:
        return json.loads(CATALOG.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _default_language() -> str:
    try:
        lang = json.loads(CONFIG_FILE.read_text(encoding="utf-8")).get("lang")
        if lang in LANGS:
            return lang
    except (OSError, ValueError, AttributeError):
        pass
    env = os.environ.get("INTONASPHERE_LANG") or os.environ.get("LANG", "")
    try:
        env = env or (locale.getlocale()[0] or "")
    except (ValueError, TypeError):
        pass
    return "fr" if env.lower().startswith("fr") else "en"


def language() -> str:
    if "lang" not in st.session_state:
        st.session_state["lang"] = _default_language()
    return st.session_state["lang"]


def tr(message: str, /, **values) -> str:
    """Translate an English message; {name} placeholders are filled from the keyword arguments."""
    text = _french().get(message, message) if language() == "fr" else message
    if values:
        try:
            return text.format(**values)
        except (KeyError, IndexError, ValueError):
            return message.format(**values)
    return text


def language_selector() -> None:
    """Sidebar control 'Language / Langue'. Put it before the other sidebar widgets."""
    current = language()
    choice = st.sidebar.selectbox("Language / Langue", list(LANGS), index=list(LANGS).index(current),
                                  format_func=lambda k: LANGS[k], key="lang_choice")
    if choice != current:
        st.session_state["lang"] = choice
        st.rerun()
