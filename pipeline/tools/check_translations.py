"""
Check that every message of the pipeline has a French translation.

    python tools/check_translations.py            # lists missing or unused French messages, exit 1 if any are missing
    python tools/check_translations.py --update   # adds missing messages to messages/fr.json (English text, to translate)

A message is any literal passed to tr(...) in modules/*.py, plus the README sheet rows of run_all
and the CODEBOOK definitions of dataset_sheet, which are translated when the workbook is written.
"""
from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def messages() -> dict:
    found = {}
    for f in sorted((ROOT / "modules").glob("*.py")) + [ROOT / "install.py"]:
        tree = ast.parse(f.read_text(encoding="utf-8"))
        for n in ast.walk(tree):
            if (isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "tr" and n.args
                    and isinstance(n.args[0], ast.Constant) and isinstance(n.args[0].value, str)):
                found.setdefault(n.args[0].value, f"{f.name}:{n.lineno}")
    from modules.run_all import README_ROWS
    from modules.dataset_sheet import CODEBOOK
    for k, v in README_ROWS:
        found.setdefault(k, "run_all.py README_ROWS"); found.setdefault(v, "run_all.py README_ROWS")
    for word in ("speaker", "file"):                 # values of --pitch-method, passed to tr() as a variable
        found.setdefault(word, "run_all.py --pitch-method")
    for _, d, _, src in CODEBOOK:
        found.setdefault(d, "dataset_sheet.py CODEBOOK"); found.setdefault(src, "dataset_sheet.py CODEBOOK")
    return found


def main() -> int:
    fr_file = ROOT / "messages" / "fr.json"
    fr = json.loads(fr_file.read_text(encoding="utf-8")) if fr_file.exists() else {}
    found = messages()
    missing = [m for m in found if m not in fr]
    unused = [m for m in fr if m not in found]
    bad = []
    import string
    for m in found:
        if m in fr:
            names = lambda s: sorted({p[1] for p in string.Formatter().parse(s) if p[1]})
            try:
                if names(m) != names(fr[m]):
                    bad.append(m)
            except ValueError:
                bad.append(m)
    if "--update" in sys.argv:
        for m in missing:
            fr[m] = m
        fr_file.write_text(json.dumps(dict(sorted(fr.items())), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"added {len(missing)} message(s) to {fr_file}; translate them")
        return 0
    print(f"{len(found)} messages; French: {len(found) - len(missing)} translated, {len(missing)} missing, "
          f"{len(unused)} no longer used, {len(bad)} with mismatched {{placeholders}}")
    for m in missing:
        print(f"  MISSING  {found[m]}: {m[:100]!r}")
    for m in bad:
        print(f"  PLACEHOLDERS  {found[m]}: {m[:100]!r}")
    for m in unused:
        print(f"  UNUSED   {m[:100]!r}")
    return 1 if missing or bad else 0


if __name__ == "__main__":
    sys.exit(main())
