"""
Check that every message of the Streamlit app (app.py, ui_components.py) has a French translation
in messages/app_fr.json.

    python tools/check_app_translations.py            # report; exit 1 if a message is missing
    python tools/check_app_translations.py --update   # add missing messages (English text, to translate)
"""
from __future__ import annotations

import ast
import json
import string
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FILES = ["app.py", "ui_components.py"]


def messages() -> dict:
    found = {}
    for name in FILES:
        tree = ast.parse((ROOT / name).read_text(encoding="utf-8"))
        for n in ast.walk(tree):
            if (isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "tr" and n.args
                    and isinstance(n.args[0], ast.Constant) and isinstance(n.args[0].value, str)):
                found.setdefault(n.args[0].value, f"{name}:{n.lineno}")
    return found


def fields(s: str):
    return sorted({p[1] for p in string.Formatter().parse(s) if p[1]})


def main() -> int:
    cat_file = ROOT / "messages" / "app_fr.json"
    fr = json.loads(cat_file.read_text(encoding="utf-8")) if cat_file.exists() else {}
    found = messages()
    missing = [m for m in found if m not in fr]
    bad = [m for m in found if m in fr and fields(m) != fields(fr[m])]
    if "--update" in sys.argv:
        fr.update({m: m for m in missing})
        cat_file.write_text(json.dumps(dict(sorted(fr.items())), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"added {len(missing)} message(s) to {cat_file}; translate them")
        return 0
    print(f"{len(found)} app messages; French: {len(found) - len(missing)} translated, {len(missing)} missing, "
          f"{len(bad)} with mismatched {{placeholders}}")
    for m in missing:
        print(f"  MISSING  {found[m]}: {m[:100]!r}")
    for m in bad:
        print(f"  PLACEHOLDERS  {found[m]}: {m[:100]!r}")
    return 1 if missing or bad else 0


if __name__ == "__main__":
    sys.exit(main())
