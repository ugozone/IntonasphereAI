"""
IntonaSphere AI - installer in English or French / installateur en anglais ou en français
=========================================================================================

    python install.py              # asks for the language, installs, tests
    python install.py --lang fr    # en français, sans question sur la langue
    python install.py --lang en --yes --no-selftest   # no questions at all (scripts, CI)

What it does / ce qu'il fait :
  1. asks for the language (English / Français) and remembers it for every command;
  2. checks the Python version;
  3. installs the packages in requirements.txt (and, if you want, faster-whisper);
  4. runs the self-test on the synthetic recordings (no internet needed);
  5. shows the next commands to type, in your language.

Run it from the pipeline folder, with the Python you will use for the analyses
(e.g. after `conda activate ...`). On Windows type `python`, on macOS/Linux `python3`.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from modules.i18n import save_language, set_language, system_language, saved_language, t as tr  # noqa: E402

MIN_PYTHON = (3, 9)


def ask(question: str, default: bool, assume_yes: bool) -> bool:
    if assume_yes:
        return default
    hint = tr("[Y/n]") if default else tr("[y/N]")
    try:
        ans = input(f"{question} {hint} ").strip().lower()
    except EOFError:
        return default
    if not ans:
        return default
    return ans[0] in ("y", "o")                     # yes / oui


def choose_language(given: str | None, assume_yes: bool) -> str:
    if given:
        return given
    default = saved_language() or system_language() or "en"
    if assume_yes:
        return default
    print("\nIntonaSphere AI\n")
    print("  1  English")
    print("  2  Français")
    try:
        ans = input(f"Language / Langue [1/2] (default / par défaut : {'1' if default == 'en' else '2'}) : ").strip().lower()
    except EOFError:
        ans = ""
    if ans in ("1", "en", "english", "anglais"):
        return "en"
    if ans in ("2", "fr", "french", "français", "francais"):
        return "fr"
    return default


def pip_install(args, message: str) -> bool:
    print("\n" + message)
    cmd = [sys.executable, "-m", "pip", "install"] + args
    print("  " + " ".join(cmd))
    return subprocess.call(cmd, cwd=HERE) == 0


def main() -> int:
    ap = argparse.ArgumentParser(description="IntonaSphere AI installer / installateur")
    ap.add_argument("--lang", choices=["en", "fr"], help="en (English) or fr (français)")
    ap.add_argument("--yes", action="store_true", help="answer every question with its default / répondre par défaut")
    ap.add_argument("--with-asr", action="store_true",
                    help="also install faster-whisper (speech recognition) / installer aussi faster-whisper")
    ap.add_argument("--no-selftest", action="store_true", help="skip the self-test / ne pas lancer l'autotest")
    ap.add_argument("--no-pip", action="store_true",
                    help="do not install packages (e.g. only change the language) / ne pas installer de paquets")
    a = ap.parse_args()

    lang = set_language(choose_language(a.lang, a.yes))
    cfg = save_language(lang)
    print("\n" + (tr("Language: English. Every command will speak English; add --lang fr to any command for French.")
                  if lang == "en" else
                  tr("Language: French. Every command will speak French; add --lang en to any command for English.")))
    print("  " + tr("(saved in {file})", file=cfg))

    if sys.version_info < MIN_PYTHON:
        print("\n" + tr("Python {found} is too old: IntonaSphere needs Python {need} or newer. "
                        "Install a newer Python (python.org or Anaconda) and run this installer with it.",
                        found=".".join(map(str, sys.version_info[:3])), need=".".join(map(str, MIN_PYTHON))))
        return 1
    print("\n" + tr("Python {found} ({exe})", found=sys.version.split()[0], exe=sys.executable))

    if a.no_pip:
        print("\n" + tr("Packages not installed (--no-pip)."))
    elif not pip_install(["-r", "requirements.txt"], tr("Installing the required packages ...")):
        print("\n" + tr("The installation of the packages failed. Read the error above; with Anaconda, activate "
                        "your environment first (conda activate ...), then run this installer again."))
        return 1
    want_asr = a.with_asr or (not a.no_pip and ask(tr("Also install speech recognition (faster-whisper, about 1 GB with its model)? "
                                    "It is only needed for recordings that have neither a TextGrid nor a .txt."),
                                 False, a.yes))
    if want_asr and not a.no_pip and not pip_install(["faster-whisper"], tr("Installing faster-whisper ...")):
        print(tr("faster-whisper could not be installed; everything else works without it."))

    if not a.no_selftest and ask(tr("Run the self-test now (about 1 minute, no internet needed)?"), True, a.yes):
        cmd = [sys.executable, "-m", "modules.selftest", "--folder", "test_data", "--skip-network", "--lang", lang]
        print("\n  " + " ".join(cmd))
        code = subprocess.call(cmd, cwd=HERE)
        print("\n" + (tr("Self-test passed.") if code == 0 else
                      tr("The self-test reported a failure: see outputs_selftest/selftest_report.txt "
                         "and TESTING.md (TESTING.fr.md in French).")))

    py = "python" if sys.platform.startswith("win") else "python3"
    print("\n" + tr("Next steps") + "\n" + "-" * 40)
    print(tr("1. Check your data folder:") +
          f"\n   {py} -m modules.check_folder --folder ~/Desktop/pfc_all")
    print(tr("2. Run the whole analysis:") +
          f"\n   {py} -m modules.run_all --folder ~/Desktop/pfc_all --out ~/Desktop/pfc_results --align pfc")
    print(tr("3. Full self-test, including WebMAUS (needs internet):") +
          f"\n   {py} -m modules.selftest --folder test_data")
    print(tr("Guide: {file}", file=HERE / ("README.fr.md" if lang == "fr" else "README.md")))
    print(tr("Change the language at any time: {cmd}", cmd=f"{py} install.py --lang {'en' if lang == 'fr' else 'fr'} --no-pip --no-selftest --yes"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
