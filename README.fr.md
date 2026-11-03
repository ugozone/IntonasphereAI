# IntonaSphere AI : transcription + analyse Praat

[English](README.md) | **Français**

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.23290623.svg)](https://doi.org/10.5281/zenodo.23290623) [![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Site web : https://intonasphereai.org/

Cette application transcrit des fichiers audio et vidéo et réalise une analyse phonétique et acoustique avec Praat, par l'intermédiaire de Parselmouth.

## En anglais ou en français

IntonaSphere AI fonctionne en anglais ou en français ; les données produites sont les mêmes dans les deux langues.

- **Application :** choisissez **Language / Langue** en haut de la barre latérale. Elle démarre dans la langue enregistrée par l'installateur de la chaîne, ou dans celle de votre ordinateur.
- **Chaîne d'analyse :** `python3 install.py` dans `pipeline/` demande une fois *Language / Langue*, puis chaque commande parle cette langue ; ajoutez `--lang en` ou `--lang fr` à n'importe quelle commande pour en changer le temps d'une analyse. Voir [pipeline/README.fr.md](pipeline/README.fr.md).
- Les noms de colonnes, de feuilles, de fichiers et les étiquettes F_ToBI ne changent jamais avec la langue : les résultats des deux langues peuvent être réunis.

## Fonctions

- Importer des fichiers audio
- Importer des fichiers vidéo
- Enregistrer sa voix directement
- Coller l'adresse d'un média public
- Convertir les médias en WAV avec FFmpeg
- Transcrire avec Faster-Whisper
- Produire des transcriptions horodatées
- Lancer une analyse acoustique Praat
- Extraire la F0, la durée, l'intensité et les formants
- Estimer le mouvement mélodique final
- Exporter en TXT, DOCX, PDF, SRT
- Exporter les résultats acoustiques en CSV et Excel
- Calculer le taux d'erreur sur les mots (WER) et la précision de la transcription

## Installation

Ouvrez le Terminal dans le dossier `IntonasphereAI` (sur Mac, p. ex. `/Users/votrenom/IntonasphereAI`, c'est-à-dire `~/IntonasphereAI`), ou placez-vous (`cd`) là où vous avez cloné le dépôt :

```bash
cd ~/IntonasphereAI          # ou : cd /chemin/vers/IntonasphereAI
conda activate jamispeak-transcriber
python -m pip install -r requirements.txt
```

**Windows :** les mêmes commandes fonctionnent dans l'Anaconda Prompt, depuis votre dossier `C:\Users\votrenom\IntonasphereAI`. L'application Streamlit demande aussi FFmpeg (`conda install -c conda-forge ffmpeg`). La chaîne d'analyse (ci-dessous) utilise `python` au lieu de `python3` ; voir [Windows dans pipeline/README.fr.md](pipeline/README.fr.md#windows).

## Lancement

```bash
conda activate jamispeak-transcriber
python -m streamlit run app.py
```

Puis choisissez **Language / Langue** dans la barre latérale.

## Chaîne d'analyse (extraction par lots, F_ToBI, jeu de données)

Le dossier [`pipeline/`](pipeline/) contient la chaîne de recherche en ligne de commande utilisée pour l'étude LSA 2027 : WAV → alignement (vos TextGrids, ou WebMAUS à partir du son et de son texte) → indices acoustiques de la syllabe finale et classe de contour → TextGrids de propositions F_ToBI → le jeu de données à 28 colonnes avec son livre de codes, plus des scripts Praat (en anglais et en français) qui remesurent les valeurs et dessinent les deux graphiques.

```bash
cd ~/IntonasphereAI/pipeline   # ou : cd /chemin/vers/IntonasphereAI/pipeline
python3 install.py             # choisissez 2 (Français) : installe les paquets et lance l'autotest
python3 -m modules.run_all --folder ~/Desktop/pfc_all --out ~/Desktop/pfc_results --align pfc --speakers metadata/pfc_speaker_table_corrected.xlsx
```

Aucun enregistrement ni aucune métadonnée de corpus n'est inclus : l'autotest fabrique ses propres enregistrements synthétiques, et le tableau des locuteurs reste sur votre ordinateur (voir [`pipeline/metadata/README.md`](pipeline/metadata/README.md)).

Voir [`pipeline/README.fr.md`](pipeline/README.fr.md) pour toutes les options (`--realign`, `compare_runs`, `check_folder`), [`pipeline/PRAAT_VERIFICATION.fr.md`](pipeline/PRAAT_VERIFICATION.fr.md) pour vérifier les valeurs dans Praat, et [`pipeline/VERSION.md`](pipeline/VERSION.md) pour le contenu de cette version.

## Comment citer

**Auteur :** Jamike Ugochukwu Okoroji, Department of Modern Languages and Classics, Barefield College of Arts and Sciences, The University of Alabama, Tuscaloosa, Alabama, États-Unis.

Si vous utilisez IntonaSphere AI dans vos recherches, merci de citer le logiciel. Le bouton **« Cite this repository »** de GitHub (barre latérale droite) donne les références APA et BibTeX tirées de [`CITATION.cff`](CITATION.cff) ; le BibTeX de l'outil et de ses principales dépendances se trouve aussi dans [`CITATION.bib`](CITATION.bib).

> Okoroji, J. U. (2026). *IntonaSphere AI: A transcription and Praat-based prosody analysis toolkit* (Version 0.2.0) [Computer software]. Zenodo. https://doi.org/10.5281/zenodo.23290623

```bibtex
@software{Okoroji_IntonaSphere_AI_2026,
  author  = {Okoroji, Jamike Ugochukwu},
  title   = {{IntonaSphere AI: A Transcription and Praat-Based Prosody Analysis Toolkit}},
  year    = {2026},
  version = {0.2.0},
  doi     = {10.5281/zenodo.23290623},
  url     = {https://github.com/ugozone/IntonasphereAI},
  note    = {Department of Modern Languages and Classics, The University of Alabama, Tuscaloosa, Alabama, USA. Project website: https://intonasphereai.org/}
}
```

Les mesures acoustiques d'IntonaSphere AI sont calculées avec Praat par l'intermédiaire de Parselmouth ; merci de citer aussi :

- Boersma, P., & Weenink, D. *Praat: doing phonetics by computer* [Computer program]. https://www.praat.org
- Jadoul, Y., Thompson, B., & de Boer, B. (2018). Introducing Parselmouth: A Python interface to Praat. *Journal of Phonetics, 71*, 1–15. https://doi.org/10.1016/j.wocn.2018.07.001

Si vous utilisez le module de transcription, citez Whisper (Radford et al., 2023) ; la référence est dans `CITATION.bib`.

Si vous utilisez l'alignement automatique de la chaîne, citez aussi WebMAUS : Kisler, T., Reichel, U., & Schiel, F. (2017). Multilingual processing of speech via web services. *Computer Speech & Language, 45*, 326–347. https://doi.org/10.1016/j.csl.2017.01.005

## Licence

IntonaSphere AI est distribué sous [licence MIT](LICENSE). © 2026 Jamike Ugochukwu Okoroji. Vous pouvez utiliser, modifier et partager le code, à condition de conserver la mention de droit d'auteur et le texte de la licence. Les enregistrements et métadonnées de corpus (p. ex. PFC) ne font pas partie de ce dépôt et restent soumis à leurs propres conditions.
