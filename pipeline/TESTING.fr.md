# Tester IntonaSphere AI sur votre ordinateur

[English](TESTING.md) | **Français**

## 1. Installer (une seule fois)
```bash
cd IntonasphereAI/pipeline
python3 install.py                 # choisissez 2 (Français) ; Windows : python install.py
```

L'installateur installe les paquets de `requirements.txt`, propose faster-whisper (utile seulement pour tester des enregistrements sans TextGrid ni `.txt`) et lance l'autotest en français. Installation à la main, si vous préférez :

```bash
pip install -r requirements.txt
pip install faster-whisper        # seulement pour les enregistrements sans TextGrid ni .txt
```

Sous **Windows**, tapez `python` là où ces pages écrivent `python3` ; voir la section Windows de README.fr.md.

## 2. Autotest automatique (environ 5 minutes)
Le dépôt ne contient aucun enregistrement (l'audio du corpus reste privé). Quand `test_data/` ne contient aucun WAV, l'autotest crée d'abord deux courts enregistrements **synthétiques** avec `test_data/make_test_data.py` (un son en forme de voyelle /a/ qui dit « la banane » ; aucun locuteur réel) :

| Fichier | Parcours testé | Résultat attendu |
|---|---|---|
| `synth_question.wav` + `synth_question.TextGrid` | WAV + TextGrid (parcours d'origine), F_ToBI | montée, H* H% |
| `synth_statement.wav` + `synth_statement.txt` | Nom quelconque + fichier texte : WebMAUS avec votre texte | descente |

Pour tester avec de la vraie parole, préparez un petit dossier de vos propres enregistrements et donnez-le avec `--folder`, par exemple :

| Fichier | Parcours testé |
|---|---|
| `xxx1tw2.wav` + `xxx1tw2.TextGrid` | WAV + votre TextGrid |
| `xxx1tw1.wav` | Nom PFC, sans TextGrid : WebMAUS avec le texte de la question PFC |
| `ma_phrase.wav` + `ma_phrase.txt` | Nom quelconque + fichier texte : WebMAUS avec votre texte |
| `autre.wav` | Rien d'autre : reconnaissance vocale (faster-whisper), puis WebMAUS |

```bash
python -m modules.selftest --folder test_data --lang fr
```
**Envoyez-moi `outputs_selftest/selftest_report.txt`.** Chaque ligne est marquée PASS, WARN, FAIL, SKIP ou INFO (ces mots restent en anglais dans les deux langues, pour que les rapports se comparent). Sans internet, ajoutez `--skip-network` : les étapes WebMAUS sont alors marquées SKIP.

## 3. Vérifier les résultats à l'œil (environ 15 minutes)

1. **Graphiques.** Ouvrez `outputs_selftest/run/final_domain/*.png` et `outputs_selftest/run/ftobi/*.png`.
   - La F0 suit-elle ce que vous entendez ?
   - La syllabe finale est-elle la bonne ?
2. **TextGrids WebMAUS.** Dans Praat, ouvrez `synth_statement.wav` (ou un de vos enregistrements sans TextGrid) avec son fichier dans `outputs_selftest/run/aligned/`.
   - Les frontières des mots et des syllabes sont-elles au bon endroit ? (Pour le fichier synthétique, elles sont approximatives, puisque ce n'est pas de la vraie parole.)
   - Les phones sont-ils français ?
3. **Vérification F_ToBI.** Lancez `praat/check_ftobi_fr.praat`.
   - Dossier des propositions : `outputs_selftest/run/ftobi`
   - Dossier audio : `test_data`

   Corrigez un fichier et cliquez sur « Enregistrer et suivant ». Vérifiez ensuite que `*_checked.TextGrid` apparaît et que vous pouvez arrêter le script puis le reprendre.
4. **Validation.** Lancez :
   ```bash
   python -m modules.validate_ftobi --auto outputs_selftest/run/ftobi --checked outputs_selftest/run/ftobi --out outputs_selftest/validation
   ```
   Puis ouvrez `outputs_selftest/validation/ftobi_validation.xlsx`.
5. **Classeur.** Ouvrez `outputs_selftest/run/intonasphere_results.xlsx`.
   - Y a-t-il une ligne par WAV ?
   - L'`ALIGNMENT_SOURCE` de chaque fichier est-il correct ?
   - Les feuilles README et CODEBOOK sont-elles en français, et les noms de colonnes en anglais ?

## 4. Ensuite, un vrai lot
Traitez votre dossier complet une fois normalement et une fois avec `--realign`, puis comparez les deux analyses avec `python -m modules.compare_runs` (voir README.fr.md).

## Ce que signifie le plus souvent un échec
| Ligne du rapport | Cause probable et que faire |
|---|---|
| `FAIL package …` | Lancez `pip install -r requirements.txt` (ou `python3 install.py`) |
| `WARN pitch engine built-in` | Lancez `pip install praat-parselmouth`. Les résultats sont valables, mais la détection de F0 de Praat lui-même est préférable pour l'article. |
| `FAIL WebMAUS …` | Pas de connexion internet, un pare-feu, ou le serveur BAS est indisponible. Les fichiers qui ont un TextGrid fonctionnent quand même. Envoyez-moi le texte de l'erreur. |
| `WARN WebMAUS used the French model` | Des symboles allemands sont apparus dans le résultat. Envoyez-moi le rapport. |
| `FAIL output TextGrids` / `workbook` | Un bogue. Envoyez-moi le rapport. |
