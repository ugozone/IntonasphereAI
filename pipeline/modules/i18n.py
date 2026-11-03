"""
IntonaSphere AI - language of messages (English / français)
===========================================================

Every message the pipeline prints or writes for a person to read can appear in English or in
French. Data never changes with the language: column names, sheet names, file names and F_ToBI
labels are identical in both, so results from a French and an English run can be pooled.

The language is chosen, in this order, by:
  1. the --lang en|fr option of any command;
  2. the INTONASPHERE_LANG environment variable (en or fr);
  3. the choice saved by install.py in ~/.intonasphere/config.json;
  4. the computer's language (a French-language system gives French);
  5. English.

Messages are written in English in the code as t("English text {name}", name=value). The
French text for each English message is in messages/fr.json; a message missing from that file
is shown in English, and tools/check_translations.py lists any message without a translation.
"""
from __future__ import annotations

import json
import locale
import os
import sys
from pathlib import Path
from typing import Dict, Optional

SUPPORTED = ("en", "fr")
PACKAGE_DIR = Path(__file__).resolve().parent.parent          # .../pipeline
MESSAGES_DIR = PACKAGE_DIR / "messages"
CONFIG_FILE = Path.home() / ".intonasphere" / "config.json"

_lang: Optional[str] = None
_catalog: Dict[str, str] = {}


def _normalise(code: Optional[str]) -> Optional[str]:
    if not code:
        return None
    code = str(code).strip().lower().replace("-", "_")
    for lang in SUPPORTED:
        if code == lang or code.startswith(lang + "_"):
            return lang
    if code.startswith("fran"):                     # "français", "francais", "french" handled below
        return "fr"
    if code.startswith("french"):
        return "fr"
    if code.startswith("engl") or code.startswith("angl"):
        return "en"
    return None


def saved_language() -> Optional[str]:
    """Language saved by install.py, or None."""
    try:
        return _normalise(json.loads(CONFIG_FILE.read_text(encoding="utf-8")).get("lang"))
    except (OSError, ValueError, AttributeError):
        return None


def save_language(lang: str) -> Path:
    """Remember the language for every later command (used by install.py)."""
    lang = _normalise(lang) or "en"
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    data = {}
    try:
        data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    data["lang"] = lang
    CONFIG_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return CONFIG_FILE


def system_language() -> Optional[str]:
    """Language of the computer, from the environment (macOS/Linux) or the locale (Windows)."""
    for var in ("LC_ALL", "LC_MESSAGES", "LANG", "LANGUAGE"):
        lang = _normalise(os.environ.get(var, "").split(":")[0])
        if lang:
            return lang
    try:
        loc = locale.getlocale()[0] or ""
    except (ValueError, TypeError):
        loc = ""
    if not loc and sys.platform.startswith("win"):
        try:                                          # Windows: user interface language
            import ctypes
            loc = locale.windows_locale.get(ctypes.windll.kernel32.GetUserDefaultUILanguage(), "")
        except Exception:
            loc = ""
    return _normalise(loc)


def _lang_from_argv(argv) -> Optional[str]:
    for i, arg in enumerate(argv):
        if arg == "--lang" and i + 1 < len(argv):
            return _normalise(argv[i + 1])
        if arg.startswith("--lang="):
            return _normalise(arg.split("=", 1)[1])
    return None


def set_language(lang: Optional[str]) -> str:
    """Set the language for this run and load its messages. Returns the language used."""
    global _lang, _catalog
    _lang = _normalise(lang) or "en"
    _catalog = {}
    if _lang != "en":
        try:
            _catalog = json.loads((MESSAGES_DIR / f"{_lang}.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            _catalog = {}
    return _lang


def init_language(argv=None) -> str:
    """Choose the language before the command-line parser is built, so that --help is translated."""
    argv = sys.argv[1:] if argv is None else argv
    return set_language(_lang_from_argv(argv) or _normalise(os.environ.get("INTONASPHERE_LANG"))
                        or saved_language() or system_language() or "en")


def language() -> str:
    if _lang is None:
        init_language()
    return _lang  # type: ignore[return-value]


def t(message: str, /, **values) -> str:
    """Translate an English message; {name} placeholders are filled from the keyword arguments."""
    if _lang is None:
        init_language()
    text = _catalog.get(message, message) if _catalog else message
    if values:
        try:
            return text.format(**values)
        except (KeyError, IndexError, ValueError):
            return message.format(**values)
    return text


def add_lang_option(parser) -> None:
    """Add --lang en|fr to a command (the value is already applied by init_language)."""
    parser.add_argument("--lang", choices=list(SUPPORTED), default=language(),
                        help=t("language of messages and reports: en (English) or fr (French); "
                               "data and column names are the same in both"))
    _translate_argparse()


def _translate_argparse() -> None:
    """argparse's own words (usage, options, 'show this help message and exit') in French too."""
    if language() != "fr":
        return
    import argparse
    words = {"usage: ": "utilisation : ", "options": "options", "positional arguments": "arguments positionnels",
             "show this help message and exit": "afficher cette aide et quitter",
             "the following arguments are required: %s": "arguments obligatoires manquants : %s",
             "invalid choice: %(value)r (choose from %(choices)s)": "choix non valide : %(value)r (choisir parmi %(choices)s)",
             "%(prog)s: error: %(message)s\n": "%(prog)s : erreur : %(message)s\n",
             "unrecognized arguments: %s": "arguments non reconnus : %s",
             "expected one argument": "un argument attendu"}
    argparse._ = lambda s: words.get(s, s)          # argparse looks its words up through this function
