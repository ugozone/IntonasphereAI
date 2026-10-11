"""IntonaSphere AI pipeline modules.

Cross-platform helpers used by every command (macOS, Linux and Windows):
- the console is switched to UTF-8 so IPA symbols, accents and arrows never crash a run
  on a Windows console or when the output is redirected to a file;
- user_path() expands ~ (home folder) and environment variables in paths typed on the
  command line, which Windows shells (cmd, PowerShell) do not do for Python.
"""
import os
import sys
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass


def user_path(p):
    """Path typed by the user -> Path, with ~ and %VAR% / $VAR expanded (None stays None)."""
    if p is None or p == "":
        return p
    return Path(os.path.expandvars(os.path.expanduser(str(p))))


CSV_ENCODING = "utf-8-sig"   # UTF-8 with a BOM: Excel on Windows then shows accents and IPA correctly
