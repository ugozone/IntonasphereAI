# Visualiseur du domaine final (IntonaSphere AI)

[English](README_final_domain_visualizer.md) | **Français**

Produit, pour chaque question :

- **`<fichier>_final_domain.png`** : une figure dans le style de Praat avec l'oscillogramme, le spectrogramme et la courbe de F0, ainsi que les tiers. La syllabe finale est ombrée, et un panneau de zoom marque le début, le pic et la fin de la F0 avec leurs temps et leurs valeurs, la pente ajustée et la durée.
- **`<fichier>_cues.TextGrid`** : s'ouvre dans Praat à côté du WAV. Il garde vos tiers WebMAUS (ou ajoute des tiers automatiques `UTT-AUTO` / `SYL-AUTO` quand il n'y a pas de TextGrid) et ajoute :
  - `FINAL-DOMAIN` (tier d'intervalles) : la syllabe finale
  - `CUES` (tier de points) : chaque indice à son temps exact, p. ex. `F0 onset 231 Hz`, `F0 offset 248 Hz`, `RISE +5.3 ST/s fitted; dur 370 ms`
- **`final_domain_cues.csv` / `.xlsx`** : une ligne par occurrence avec chaque indice et son temps, reliée à la figure et au TextGrid.

Le texte écrit sur les figures et dans les TextGrids, ainsi que les noms de colonnes, reste en anglais dans les deux langues, pour que les résultats puissent être réunis ; `--lang fr` traduit les messages et l'aide.

## Installation

```bash
python3 install.py          # depuis le dossier pipeline ; choisissez 2 (Français)
```

ou à la main : `pip install praat-parselmouth numpy scipy matplotlib pandas openpyxl`.

Avec Parselmouth, la F0 et l'intensité viennent de Praat lui-même. Sans lui, un détecteur intégré (autocorrélation dans le style de Praat) est utilisé, et son nom figure sur chaque figure.

## Lancement

```bash
# WAV avec des TextGrids WebMAUS du même nom : syllabe finale tirée du tier MAS
python -m modules.final_domain_visualizer --folder chemin/vers/dossier --out outputs/final_domain

# WAV seuls (ou pour ignorer les TextGrids) : segmentation automatique
python -m modules.final_domain_visualizer --folder chemin/vers/dossier --out outputs/final_domain --force-auto

# options
--tier MAS                 # nom du tier des syllabes dans vos TextGrids
--slope-threshold 1.5      # limite en demi-tons/s entre montée/descente et plateau
--pitch-range 75 500       # plage fixe au lieu de la plage adaptée au locuteur en deux passes
--svg                      # enregistre aussi les figures en SVG (pour les articles)
--lang fr                  # messages et aide en français
```

## Mesures

| Colonne | Signification |
| --- | --- |
| FINAL_SYLLABLE_START / END / DURATION | Syllabe finale (tier MAS, ou automatique) |
| F0_ONSET / PEAK / VALLEY / OFFSET (_TIME, _HZ) | Le début et la fin sont les médianes des 3 premières et des 3 dernières trames voisées |
| F0_CHANGE_ST | Fin par rapport au début, en demi-tons |
| FINAL_SLOPE_ST | Pente des moindres carrés sur les trames voisées (demi-tons/s) ; utilisée pour CONTOUR_CLASS |
| FINAL_SLOPE_ENDPOINT_ST | (dernière − première trame) / durée de la syllabe : la définition du jeu de données publié |
| PEAK_ALIGNMENT_S / _PROP | Temps du pic depuis le début de la syllabe, en secondes et en proportion de la syllabe |
| MAX_F0_JUMP_ST / QC_OCTAVE_JUMP | Plus grand saut de F0 d'une trame à l'autre dans la syllabe finale ; signalé si ≥ 7 demi-tons |
| PITCH_FLOOR_HZ / CEILING_HZ | Plage adaptée au locuteur : 0,75 × Q25 et 1,5 × Q75 d'une première passe |

## Appariement des TextGrids

`64aab1tw2.wav` prend `64aab1tw2.TextGrid`. Sans correspondance exacte, une version suffixée de la même occurrence est acceptée (`64aab1tw1R.TextGrid`, `64aab1tw2m.TextGrid`, `… copy.TextGrid`), mais jamais le fichier d'une autre question. Parmi plusieurs candidats, celui qui a un tier d'intervalles de syllabes (MAS) l'emporte. Tiers de syllabes acceptés, dans l'ordre : MAS, syllabe, syllable, sylable, syllables, syll.

## Signal de qualité

`QC_OCTAVE_JUMP` = True quand la F0 saute de 7 demi-tons ou plus entre deux trames de 10 ms dans la syllabe finale, ce qui est en général une erreur de détection. Ces figures sont marquées « ⚠ check ».

## Segmentation automatique (sans TextGrid)

Les silences sont trouvés comme avec *To TextGrid (silences)* de Praat (−25 dB). Les noyaux syllabiques sont des pics d'intensité séparés par des creux d'au moins 2 dB et voisés au pic (de Jong & Wempe, 2009). Les frontières de syllabes tombent aux minima d'intensité entre les noyaux. La syllabe finale est prolongée tant que le voisement continue. C'est une approximation pour les fichiers sans alignement ; les frontières MAS de WebMAUS sont préférées dès qu'elles existent.

## La syllabe finale dans le TextGrid (x_cues.TextGrid)

| Tier | Contenu |
|---|---|
| FINAL-DOMAIN | La syllabe finale en API, son mot, ses temps de début et de fin et sa durée, p. ex. `[ljø]  final syllable of 'Beaulieu'  1.400-1.683 s  (283 ms)` |
| FINAL-PHONES | Ses phones en API, avec la voyelle marquée : `l` · `j` · `ø (vowel)` |
| CONTOUR | Montée / descente / plateau, la pente ajustée, la variation du début à la fin, l'alignement du pic et la part de la voyelle qui a une F0 |
| CUES | Points pour le début, le pic, le creux et la fin, chacun avec sa valeur, plus « F0 ends » là où la courbe de F0 s'arrête avant la fin de la syllabe |

**F0 sur la voyelle finale.** En fin de phrase, la dernière voyelle est souvent craquée, ou sa F0 descend sous le plancher : la F0 ne peut alors pas y être mesurée. Le contour est alors mesuré surtout sur les consonnes qui précèdent la voyelle.
- `FINAL_VOWEL_F0_COVERAGE` donne la part de la voyelle qui a une F0.
- `QC_FINAL_VOWEL_LOW_F0` vaut True quand cette part est inférieure à 50 %.
- Vérifiez ces occurrences dans Praat, et indiquez dans l'article comment elles ont été traitées : gardées, ou analysées à part.

## Classes de contour

| Classe | Règle |
|---|---|
| **rise-fall** (montée-descente) | La F0 culmine à l'intérieur de la syllabe finale : le pic se trouve dans les 60 % centraux de la partie voisée, est au moins 1,5 demi-ton au-dessus du début et de la fin, et a au moins 4 trames voisées (40 ms) de chaque côté. Correspond à F_ToBI (L)H* L%. |
| **fall-rise** (descente-montée) | La même règle avec un creux au lieu d'un pic. Correspond à F_ToBI L* H%. |
| **rise / fall / plateau** (montée / descente / plateau) | Sinon, d'après la pente ajustée : au moins +1,5 demi-ton/s est une montée, au plus −1,5 demi-ton/s une descente, et tout ce qui est entre les deux un plateau. |

Les noms des classes restent en anglais dans les données (`rise-fall`, `rise`, ...).

Une seule droite ne peut pas décrire un contour qui tourne : ces graphiques montrent donc deux droites ajustées, l'une avant et l'autre après le point de retournement. `CONTOUR_SLOPE_CLASS` garde la classe que donnerait la seule règle de la pente, pour comparaison avec les résultats antérieurs à trois classes. Le script Praat `verify_final_domain.praat` (ou `verify_final_domain_fr.praat`) applique la même règle.
