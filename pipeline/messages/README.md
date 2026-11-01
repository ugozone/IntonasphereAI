# Translations / Traductions

IntonaSphere AI writes every message in English in the code and looks up its French text here.

| File | Used by |
|---|---|
| `pipeline/messages/fr.json` | the command-line pipeline (`modules/*.py`, `install.py`) |
| `messages/app_fr.json` (repository root) | the Streamlit app (`app.py`, `ui_components.py`) |

Each file maps an English message to its French text:

```json
"Wrote {file}": "Fichier écrit : {file}"
```

## Rules

- **Keep every `{name}` placeholder** exactly as in the English, with the same name. The French may move it within the sentence.
- **Never translate data:** column names (`F0_PEAK_HZ`), sheet names, file names, option values (`--align pfc`), F_ToBI labels (`H* H%`), contour classes (`rise`) and the report keywords PASS/WARN/FAIL/SKIP/INFO.
- A message missing from the file is shown in English, so nothing breaks; the checkers below list it.
- Save the files in UTF-8.

## Adding or changing a message

1. In the code, write the English message as `tr("English text {name}", name=value)` (pipeline: `from .i18n import t as tr`; app: `from app_i18n import tr`). Only literal strings are found by the checkers.
2. Run the checkers from the repository root:

   ```bash
   python pipeline/tools/check_translations.py           # pipeline
   python tools/check_app_translations.py                # app
   ```

   They list messages with no French text, French texts no longer used, and placeholders that do not match, and exit with an error when something is missing (the GitHub tests run them).
3. `python pipeline/tools/check_translations.py --update` adds the missing messages to `fr.json` with the English text as a placeholder; translate them and run the checker again.

## Adding another language

Copy `fr.json` to, for example, `es.json`, translate it, and add the code to `SUPPORTED` in `pipeline/modules/i18n.py` and to the installer's language question in `install.py`. The app (`app_i18n.py`) currently reads only `messages/app_fr.json` and would need the same small change.

---

**En bref (français).** Les messages sont écrits en anglais dans le code et leur texte français se trouve dans `fr.json` (chaîne) et `messages/app_fr.json` (application). Gardez chaque `{nom}` tel quel, ne traduisez jamais les données (noms de colonnes, de feuilles, de fichiers, valeurs d'options, étiquettes F_ToBI), enregistrez en UTF-8, puis lancez `python pipeline/tools/check_translations.py` et `python tools/check_app_translations.py` : ils signalent toute traduction manquante.
