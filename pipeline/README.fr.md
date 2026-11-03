# IntonaSphere AI : indices prosodiques et F_ToBI à partir d'enregistrements en français

[English](README.md) | **Français**

## Installation, en anglais ou en français

```bash
cd ~/IntonasphereAI/pipeline
python3 install.py            # Windows : python install.py
```

L'installateur demande d'abord *Language / Langue* (1 English, 2 Français), puis installe les paquets, lance l'autotest et affiche les commandes suivantes, le tout dans cette langue. Le choix est mémorisé : chaque commande affiche ensuite ses messages, son aide et ses rapports dans cette langue, et écrit dans cette langue les feuilles README et CODEBOOK du classeur.

- Changer de langue pour une seule commande : ajoutez `--lang en` ou `--lang fr` (p. ex. `python3 -m modules.run_all --lang en ...`).
- Changer de langue durablement : `python3 install.py --lang en --no-pip --no-selftest --yes` (ou `--lang fr`).
- Autres possibilités : la variable d'environnement `INTONASPHERE_LANG` (`en` ou `fr`) ; sans aucun choix, un ordinateur réglé en français obtient le français.
- **Les données ne changent jamais avec la langue.** Les noms de colonnes, de feuilles, de fichiers, les valeurs des options et les étiquettes F_ToBI sont les mêmes en anglais et en français : les résultats des deux langues peuvent être réunis et lus par les mêmes scripts.
- Scripts Praat en français : `praat/*_fr.praat` (mêmes scripts, formulaires et messages en français).
- Options de l'installateur : `--yes` (aucune question), `--with-asr` (installe aussi faster-whisper), `--no-selftest`, `--no-pip`.

**Tester d'abord :** voir TESTING.fr.md (`python -m modules.selftest --folder test_data`).
Vérifier les valeurs et dessiner les graphiques dans Praat : voir PRAAT_VERIFICATION.fr.md.

## Découper un long enregistrement en extraits par phrase

Pour un film, un entretien ou une longue lecture, `segment_media` découpe l'enregistrement en un WAV par phrase, chacun accompagné d'un `.txt` contenant ses mots. Le dossier produit va directement dans `run_all`.

```bash
python -m modules.segment_media --media ~/Desktop/film.mp4 --srt ~/Desktop/film.srt --out ~/Desktop/film_clips
python -m modules.run_all --folder ~/Desktop/film_clips --out ~/Desktop/film_results --align any --measure both
```

| D'où viennent les temps des phrases | Option |
|---|---|
| Votre propre liste (colonnes `start`, `end`, `text`, éventuellement `id`, `label`) | `--segments liste.csv` |
| Un TextGrid Praat, p. ex. une transcription PFC : chaque intervalle étiqueté d'un tier devient un extrait | `--textgrid fichier.TextGrid` (`--tier NOM` pour choisir le tier) |
| Des sous-titres, p. ex. le `.srt` exporté par IntonaSphere | `--srt fichier.srt` |
| Une transcription IntonaSphere avec des lignes `[12.34s - 15.67s] texte` (`.docx` ou `.txt`) | `--transcript fichier.docx` |
| Du texte brut sans temps : faster-whisper trouve le temps de chaque mot et vos phrases y sont appariées | `--text fichier.txt` |
| Rien : faster-whisper transcrit et les extraits suivent ses phrases (vérifiez les `.txt`) | *(aucune option)* |

L'audio comme la vidéo conviennent (WAV, MP3, M4A, MP4, MOV, ... ; tout sauf le WAV demande ffmpeg). Le dossier de sortie contient aussi `segments.csv` (temps dans l'enregistrement d'origine, texte, nom de l'extrait, remarques à vérifier) et un `<média>.TextGrid` avec un intervalle par phrase, à ouvrir dans Praat avec l'audio d'origine. Pour une vidéo, la piste audio est enregistrée sous `<média>.wav`.

Options : `--prefix 11aab1_` ajoute le code du locuteur au nom de chaque extrait, pour que les extraits de plusieurs enregistrements puissent partager un dossier ; `--pad 0.15` secondes de contexte autour de chaque phrase ; `--match '\?'` ne garde que les phrases dont le texte correspond (ici, les questions) ; `--split segments` garde les segments fournis tels quels au lieu d'un extrait par phrase ; `--keep-suspect` garde les phrases signalées comme boucles de reconnaissance.

Plusieurs enregistrements à la fois (macOS/Linux), chaque WAV avec un TextGrid du même nom, tous les extraits dans un même dossier :

```bash
for w in ~/Desktop/pfc_long/*.wav; do
  b=$(basename "$w" .wav)
  python -m modules.segment_media --media "$w" --textgrid "${w%.wav}.TextGrid" --prefix "${b}_" --out ~/Desktop/pfc_clips
done
```

Chaque passage réécrit `segments.csv` et ajoute son propre TextGrid : donnez à chaque enregistrement son propre dossier `--out` si vous avez besoin de chaque `segments.csv`.

Garde-fous :
- **La marge n'empiète jamais sur une phrase voisine.** Elle s'arrête au milieu du silence, de sorte qu'un extrait ne peut pas commencer par la fin de la réplique de quelqu'un d'autre.
- **Les boucles de reconnaissance sont écartées.** Le même texte trois fois de suite ou plus, ou un long passage presque sans mots (musique), est marqué `SUSPECT` dans `segments.csv` et n'est pas écrit.
- **Plusieurs phrases dans un segment** sont coupées à `.`, `?`, `!` quand les temps des mots sont connus (`--text` ou reconnaissance vocale). Issues de sous-titres, elles restent entières et sont signalées, pour que vous les coupiez à la main.
- **Les mots mal reconnus** au bord d'une phrase (mode `--text`) sont gardés dans la phrase, jusqu'aux phrases voisines ; une phrase dont peu de mots ont été appariés est signalée, une phrase sans aucun mot apparié est listée comme `not found`.

## Vérifier un dossier avant de le traiter

```bash
python -m modules.check_folder --folder ~/Desktop/pfc_all --speakers metadata/pfc_speaker_table_corrected.xlsx
```

Cette commande ne modifie rien. Elle signale les WAV illisibles ou silencieux, les TextGrids manquants ou mal appariés, les versions de TextGrid en trop, les alignements WebMAUS non français, les locuteurs absents du tableau, et ce que la chaîne fera de chaque fichier. Les résultats sont écrits dans `folder_check_report.txt` et `folder_check.xlsx`, à côté du dossier.

**Réparer le dossier.** Ajoutez `--fix` pour voir les corrections proposées ; rien ne change encore. Ajoutez `--fix --apply` pour les effectuer, et `--undo` pour les annuler.
- **Renommés :** les TextGrids dont le nom comporte une faute prennent le nom de leur WAV (p. ex. `maant1w4` → `maant1tw4`).
- **Déplacés dans `pfc_all/_set_aside/` :** versions en trop, TextGrids sans WAV, fichiers hors PFC, audio inutilisable, et TextGrids défectueux (mauvaise durée, tiers manquants, alignement non français). La chaîne réaligne ensuite ces enregistrements avec WebMAUS.
- **Rien n'est supprimé.** Chaque modification est notée dans `folder_fix_log.csv`.
- **Les codes de locuteur absents du tableau vous sont laissés.**

**Fichiers de la phrase déclarative (`xxxtw4.wav`).** Ils contiennent la première phrase du texte PFC, *Le village de Beaulieu est en grand émoi.* Ils sont traités comme contrôle déclaratif : SENTENCE_ID = S4 (statement), TOKEN_ID = `xxxtw_S4`, QUESTION_TYPE = declarative. Pour les laisser de côté, sortez-les du dossier.

## Une seule commande pour tout

```bash
pip install -r requirements.txt
python -m modules.run_all --folder data/wavs --out outputs
```

Pour chaque WAV du dossier, la commande enchaîne ces étapes en un seul passage :

1. **Alignement.**
   - Votre TextGrid WebMAUS est utilisé tel quel.
   - S'il n'y a pas de TextGrid, WebMAUS (français) est appelé avec l'un de ces trois textes :
     - votre fichier `.txt` ;
     - le texte de la question PFC, déduit du nom de fichier (`…tw1/2/3`) ;
     - une transcription par reconnaissance vocale.
2. **F0.** La F0 est détectée une fois par fichier, avec Praat via Parselmouth et une plage adaptée au locuteur. Les deux graphiques utilisent cette même F0.
3. **Graphique et indices du domaine final :** `outputs/final_domain/x_final_domain.png` et `x_cues.TextGrid`.
4. **Graphique et annotation F_ToBI :** `outputs/ftobi/x_ftobi.png` et `x_ftobi.TextGrid`. Les étiquettes sont des propositions, à vérifier dans Praat.
5. **Un seul classeur,** `outputs/intonasphere_results.xlsx`, avec ces feuilles :

| Feuille | Contenu |
|---|---|
| README | Ce que contient chaque feuille (dans la langue choisie) |
| ALL_TOKENS | Une ligne par enregistrement : origine de l'alignement, indices du domaine final, résumé F_ToBI, chemins des figures et `CONTOUR_VS_BOUNDARY_TONE` |
| FINAL_DOMAIN | Tous les indices de la syllabe finale |
| FTOBI_TOKENS / FTOBI_SYLLABLES | La proposition F_ToBI et sa justification pour chaque syllabe |
| ALIGNMENT | D'où vient chaque TextGrid |
| PARAMETERS | Tous les seuils utilisés, pour pouvoir refaire l'analyse à l'identique |

### Options

| Option | Effet |
|---|---|
| `--align none` | N'utiliser que les TextGrids existants, sans WebMAUS ni reconnaissance vocale. Un fichier sans TextGrid a quand même son graphique du domaine final, avec une segmentation automatique. |
| `--align pfc` | N'appeler WebMAUS que pour les noms de fichiers PFC et les fichiers qui ont un `.txt` |
| `--no-ftobi` / `--no-final-domain` | Ne produire qu'un des deux graphiques |
| `--pitch-range 75 500` | Utiliser une plage de F0 fixe au lieu de la plage adaptée au locuteur |
| `--measure both` | Mesurer aussi toute la phrase, pas seulement la syllabe finale : `PHRASE_F0_ONSET_HZ`, `PHRASE_F0_MAX_HZ`, `PHRASE_F0_MIN_HZ`, `PHRASE_F0_OFFSET_HZ`, `PHRASE_F0_MEAN_HZ`, `PHRASE_F0_RANGE_ST`, `PHRASE_F0_CHANGE_ST`, `PHRASE_SLOPE_ST` (dans la feuille FINAL_DOMAIN). La phrase va du premier mot (tier des mots du TextGrid) ou du premier passage sonore jusqu'à la fin de la syllabe finale. Par défaut, `--measure final` garde les résultats d'avant. |
| `--realign` | Ignorer tous les TextGrids existants et aligner **tous** les fichiers avec WebMAUS à partir du son et de son texte (texte PFC, ou votre `.txt`). Vos TextGrids ne sont pas modifiés ; leurs noms sont gardés dans la colonne `USER_TEXTGRID` pour comparaison. Demande `--align pfc` ou `--align any`. Si WebMAUS échoue pour un fichier, ce fichier passe en segmentation automatique (votre TextGrid n'est pas utilisé), et la feuille ALIGNMENT en donne la raison. |
| `--lang fr` / `--lang en` | Langue des messages, de l'aide, des rapports et des feuilles README/CODEBOOK ; les données ne changent pas |
| `--language fra-FR` | Langue de l'alignement WebMAUS (à ne pas confondre avec `--lang`) |

## Construire un tableau de codage pour une étude

`coding_table` réunit les résultats d'une ou plusieurs analyses `run_all` dans un seul tableau : le plan de votre étude à gauche, les mesures à droite, des formules en demi-tons, et chaque valeur à revoir dans Praat colorée en orange avec la raison à côté.

```bash
# une fois par étude : un fichier de plan à remplir (série, paire, phrase, glose, contour attendu...)
python -m modules.coding_table --results ~/Desktop/Rue_children/results ~/Desktop/Rue_shopkeeper/results --make-design ~/Desktop/rue_design.csv

# après chaque analyse
python -m modules.coding_table \
    --results Children=~/Desktop/Rue_children/results Shopkeeper=~/Desktop/Rue_shopkeeper/results \
    --design ~/Desktop/rue_design.csv --corrections ~/Desktop/rue_corrections.csv \
    --out ~/Desktop/rue_coding_table.xlsx
```

- `--results` prend des dossiers ou des fichiers de résultats. `Étiquette=chemin` nomme le locuteur (ou le groupe) de cette analyse ; sans elle, l'étiquette est le nom du dossier analysé.
- `--design` est un CSV dont la seule colonne obligatoire est `id` (le nom de l'extrait, `07_wh`, ou son numéro, `07`). Toutes les autres colonnes sont recopiées dans votre ordre. Une colonne `speaker` l'emporte sur l'étiquette de l'analyse.
- `--corrections` est un CSV avec `id, column, value, note` : des valeurs mesurées à la main dans Praat. `column` est un en-tête du tableau (p. ex. `F0 onset (Hz)`) ; une `value` vide vide la cellule. Les cellules corrigées deviennent bleues, et chaque modification est listée dans la feuille CORRECTIONS, si bien que le tableau peut être reconstruit à l'identique après une nouvelle analyse.

Pour PFC, écrivez le plan une fois par **question** et non par enregistrement : `--design-by question` avec un fichier de plan dont la colonne `question` contient Q1, Q2, Q3, S4 (ou 1, 2, ...). Chaque ligne s'applique à l'enregistrement de cette question par chaque locuteur ; la question est tirée du `SENTENCE_ID` de l'enregistrement ou de la fin de son nom (`…tw_Q3`).

```bash
python -m modules.coding_table --results ~/Desktop/pfc_results --make-design ~/Desktop/pfc_questions.csv --design-by question
python -m modules.coding_table --results ~/Desktop/pfc_results --design ~/Desktop/pfc_questions.csv --design-by question \
    --corrections ~/Desktop/pfc_corrections.csv --out ~/Desktop/pfc_coding_table.xlsx
```

Quand l'analyse avait un tableau des locuteurs, l'identifiant du locuteur, le site, le pays, le groupe de régions, l'âge, le groupe d'âge, le sexe, le type de question et la phrase sont recopiés depuis sa feuille DATASET : le tableau peut donc être filtré directement par région ou type de question (`--no-corpus-info` les laisse de côté). Sans `Étiquette=`, le locuteur d'un enregistrement PFC est son code de locuteur.

Signalé en orange : un début (ou un maximum au début) égal à 1,8 fois la F0 médiane du fichier ou plus (doublement d'octave) ; un début, une fin ou un minimum égal à 1/1,8 de la médiane ou moins (division par deux ou voix craquée) ; le signalement de saut d'octave de la chaîne ; un début ou un minimum à moins de 1,5 demi-ton du plancher de F0, un maximum à moins de 1,5 demi-ton du plafond ; une F0 présente sur moins de la moitié de la voyelle finale ; une syllabe finale de moins de 120 ms ; une classe de contour en désaccord avec le ton de frontière F_ToBI (descente avec H%, montée avec L%) ; des mots issus de la reconnaissance vocale. Un signalement vous invite à regarder ; il ne modifie aucune valeur.

## Tout aligner à partir du seul son (`--realign`) et comparer

Pour que tout le jeu de données soit aligné par une seule procédure documentée, lancez l'extraction deux fois, dans deux dossiers de sortie, puis comparez-les :

```
python3 -m modules.run_all --folder ~/Desktop/pfc_all --out ~/Desktop/pfc_results --align pfc --speakers metadata/pfc_speaker_table_corrected.xlsx
python3 -m modules.run_all --folder ~/Desktop/pfc_all --out ~/Desktop/pfc_results_realigned --align pfc --realign --speakers metadata/pfc_speaker_table_corrected.xlsx
python3 -m modules.compare_runs --a ~/Desktop/pfc_results --b ~/Desktop/pfc_results_realigned
```

`compare_runs` n'utilise que les enregistrements alignés dans les deux analyses (ajoutez `--include-unaligned` pour passer outre, `--only-user-textgrids` pour ne garder que les fichiers qui avaient votre propre TextGrid dans l'analyse A). Il indique l'écart en ms du début et de la fin de la syllabe finale (et la part à moins de 20 et 50 ms), l'écart de durée, l'écart médian et la corrélation de la pente et du début/pic/fin de F0, ainsi que l'accord et le kappa de Cohen pour la classe de contour, la classe de pente à trois valeurs et la configuration nucléaire F_ToBI. Il écrit `compare_runs_report.txt` et `compare_runs.xlsx` (SUMMARY, PER_FILE, CONTOUR_CROSSTAB) dans le second dossier. Les fichiers dont la classe de contour diffère sont listés : ouvrez les deux graphiques pour ceux-là.

### `CONTOUR_VS_BOUNDARY_TONE`

Les deux analyses décrivent la fin de la question de deux façons différentes.

- La **classe de contour** du domaine final repose sur la **pente**, la vitesse de variation en demi-tons/s.
- Le **ton de frontière** F_ToBI repose sur l'**ampleur** du mouvement : H% pour une montée d'au moins +1,5 demi-ton, L% pour une descente d'au moins −1,5 demi-ton.

Une petite montée lente peut donc compter comme « rise » dans l'une et comme plate, marquée « ? », dans l'autre. Cette colonne indique `agree`, `agree (F_ToBI label uncertain)` ou `… : check`. Regardez les lignes `check` dans Praat.

## Plage de F0 (comment la F0 est détectée)

La plage est fixée en deux passes, d'après De Looze & Hirst (2008) :

1. **Première passe,** avec une large plage choisie selon le sexe indiqué dans le tableau des locuteurs : hommes 60–300 Hz, femmes 100–500 Hz, et 60–600 Hz quand le sexe est inconnu.
2. **Seconde passe,** avec plancher = 0,75 × le 25e centile et plafond = 1,5 × le 75e centile de la F0 de la première passe.
   - Les trames de la première passe à plus de 8 demi-tons de la médiane du locuteur sont exclues de ce calcul. Ce sont des erreurs d'octave : F0 divisée ou doublée à tort.
   - Le plancher n'est jamais inférieur à 50 Hz.

**Regroupement.** Par défaut, les valeurs de la première passe sont regroupées par **locuteur**, si bien que tous les enregistrements d'un locuteur (tw1–tw4) reçoivent la même plage. `--pitch-method file` fixe la plage pour chaque enregistrement séparément, comme auparavant. `--no-sex-first-pass` utilise 60–600 Hz pour tout le monde. La méthode est notée dans PARAMETERS, et la plage de chaque fichier dans ALL_TOKENS.

**Contrôle du sexe.** Un locuteur dont la F0 médiane est inhabituelle pour le sexe indiqué dans le tableau (hommes au-dessus de 165 Hz, femmes au-dessous de 150 Hz) reçoit à la place la première passe large de 60–600 Hz, et est listé dans DATASET_WARNINGS pour que vous vérifiiez SEX. Si le tableau est juste, rien à faire. Exemple : 64aji1 est un homme à la voix aiguë (médiane d'environ 170–180 Hz).

**Commandes séparées.** Les commandes du domaine final et de F_ToBI lancées seules utilisent toujours la plage par fichier.

## La feuille du jeu de données (28 en-têtes publiés)

```bash
python -m modules.run_all --folder data/wavs --out outputs --speakers metadata/pfc_speaker_table_corrected.xlsx
```

- **Feuille DATASET** (aussi enregistrée sous `outputs/intonasphere_dataset.csv`) : une ligne par enregistrement. Elle a exactement les 28 en-têtes du jeu de données publié, dans le même ordre (TOKEN_ID … EXTRACTION_END), et chaque valeur est calculée par le code. Les en-têtes restent en anglais quelle que soit la langue choisie.
- **Feuille CODEBOOK :** la définition, l'unité et la source de chaque colonne, dans la langue choisie. Citez-la dans l'article.
- **Feuille SPEAKERS :** le tableau des locuteurs tel qu'il a été utilisé.
- **Feuille DATASET_WARNINGS :** les enregistrements dont le locuteur n'est pas dans le tableau. Chaque avertissement propose le code le plus proche.
- **AGE_GROUP** est recalculé à partir de AGE par un partage à la médiane (médiane de tous les locuteurs du tableau). Un âge égal à la médiane va dans le groupe Older ; changez cela avec `--age-tie Younger`. La médiane et la règle sont notées dans PARAMETERS.
- **Codes :** `--speaker-fix CODE_DU_TABLEAU=CODE_CORRECT` corrige un code du tableau (p. ex. `--speaker-fix 81acc1=81aac1`). `metadata/pfc_speaker_table_corrected.xlsx` contient déjà cette correction.
- **Sans tableau des locuteurs :** les colonnes démographiques restent vides et tout le reste est quand même calculé.

## Sélection des énoncés (quels énoncés sont analysés)

Chaque exécution décide aussi, pour chaque énoncé, s'il est retenu, et indique pourquoi. Les règles sont celles du contrôle de qualité de la méthodologie ; les seuils figurent dans PARAMETERS. Les valeurs des décisions restent en anglais dans les données (`Include`, `Exclude`…), comme les noms de colonnes, pour que les exécutions en anglais et en français puissent être réunies.

| Décision | Quand |
|---|---|
| **Exclude** (exclu) | (a) pas de F0 dans la syllabe finale ; (c) le groupe de mots final (*à Beaulieu*, *grand honneur*, *visites officielles*, *grand émoi*) manque, est répété ou contient une hésitation ou une autocorrection, car la configuration nucléaire se réalise précisément sur cette portion |
| **Check by listening** (à écouter) | (b) débit d'articulation inférieur à 2 syllabes par seconde : le fichier contient peut-être plus que la phrase. Écoutez, puis notez Include ou Exclude |
| **Include** (retenu) | tous les autres cas. Les hésitations plus tôt dans la phrase sont notées mais n'entraînent pas l'exclusion |
| **Include, FLAGGED = yes** (retenu, signalé) | retenu, mais marqué pour l'analyse de sensibilité : F0 sur moins de la moitié de la voyelle finale, saut de F0 de 7 demi-tons ou plus, syllabe finale de plus de 600 ms, ou classe de contour en désaccord avec le ton de frontière proposé |
| **Repair, then reassess** (à réparer) | pas de TextGrid, ou l'analyse du domaine final a échoué |
| **Pending – no data** (en attente) | un locuteur de la table n'a pas d'enregistrement de cette phrase (Q1–Q3, et S4 sauf avec `--no-plan-s4`) |
| **Pending – metadata** (en attente) | le locuteur n'est pas dans la table des locuteurs |

- **Feuille SELECTION** (aussi `outputs/intonasphere_selection.csv`) : la décision et sa raison pour chaque énoncé, avec `COMPLETE_CASE_SET` (les trois questions retenues) et `RQ4_SET` (S4 et au moins une question retenus).
- **Feuilles TOKEN_FLOW** et **TOKEN_FLOW_BY_SITE** : combien d'énoncés sont retenus, signalés, exclus ou en attente, par phrase et par site.
- **Vos décisions** vont dans `outputs/manual_overrides.csv` (colonnes `TOKEN_ID, CHECKED, MANUAL_DECISION, MANUAL_NOTE`). Il est créé vide une fois et n'est jamais écrasé. `MANUAL_DECISION` peut être `Include`, `Exclude` ou, par exemple, `Not available` pour un S4 qui n'existe pas ; il remplace la décision automatique.
- **Après avoir modifié ce fichier**, mettez les décisions à jour sans refaire aucune mesure :

```bash
python -m modules.selection --results outputs/intonasphere_results.xlsx
```

Le contrôle du groupe de mots final lit le tier des mots du TextGrid : il ne voit donc que les hésitations transcrites. Les TextGrids produits par WebMAUS à partir du texte PFC contiennent le texte, et non ce que le lecteur a dit ; `TRANSCRIPT_SOURCE` indique de quel type est chaque énoncé.

## Les commandes séparées fonctionnent toujours

| Commande | Rôle |
|---|---|
| `python -m modules.final_domain_visualizer --folder X --out Y` | Graphiques du domaine final seulement (voir `README_final_domain_visualizer.fr.md`) |
| `python -m modules.ftobi_annotator --folder X --out Y [--align none]` | F_ToBI seulement (voir `README_ftobi.fr.md`) |
| `python -m modules.auto_align --folder X --out X` | TextGrids WebMAUS seulement, enregistrés à côté des WAV |
| `python -m modules.validate_ftobi --auto Y --checked Y` | Accord entre les propositions F_ToBI et les corrections faites dans Praat |

## Windows

La chaîne fonctionne sous Windows 10/11 comme sous macOS et Linux. Elle est testée automatiquement sur les trois (voir l'onglet *Actions* sur GitHub). Seule change la façon de taper les commandes :

| | macOS / Linux | Windows (PowerShell ou invite de commandes) |
|---|---|---|
| Commande Python | `python3` | `python` (ou `py`) |
| Installation | `python3 install.py` | `python install.py` |
| Chemins | `~/Desktop/pfc_all` | `~/Desktop/pfc_all` fonctionne aussi, ou `C:\Users\votrenom\Desktop\pfc_all` |
| Chemins avec espaces | `"~/Mes données/pfc_all"` | `"C:\Users\votrenom\Mes données\pfc_all"` (toujours entre guillemets) |
| Plusieurs lignes | terminer la ligne par `\` | PowerShell : terminer par `` ` `` (accent grave) ; invite de commandes : tout sur une ligne |

Exemple (PowerShell, une ligne) :

```
cd C:\Users\votrenom\IntonasphereAI\pipeline
python -m modules.run_all --folder "~/Desktop/pfc_all" --out "~/Desktop/pfc_results" --align pfc --speakers metadata/pfc_speaker_table_corrected.xlsx
```

Remarques :
- **Installer Python :** depuis python.org ou Anaconda. Avec l'installateur de python.org, cochez **« Add python.exe to PATH »**.
- **Fichiers ouverts dans Excel :** fermez `intonasphere_results.xlsx` (et les CSV) avant de relancer. Windows verrouille les fichiers ouverts ; la chaîne s'arrête dès le début en les nommant, si bien qu'une longue analyse n'est jamais perdue à la fin.
- **Fichiers CSV :** ils sont enregistrés en UTF-8 avec une marque d'ordre des octets, pour qu'Excel sous Windows affiche correctement les accents et les symboles de l'API.
- **Scripts Praat :** ils fonctionnent de la même façon dans Praat pour Windows. Dans les formulaires, vous pouvez coller les chemins avec `\` ou `/`.

## Vérifier les résultats dans Praat

- **F_ToBI :** lancez `praat/check_ftobi_fr.praat` sur `outputs/ftobi`, corrigez chaque fichier et enregistrez-le sous `*_checked.TextGrid`. Lancez ensuite `validate_ftobi`.
- **Indices du domaine final :** ouvrez `x.wav` avec `outputs/final_domain/x_cues.TextGrid`. Le tier CUES marque chaque point mesuré avec son temps et sa valeur.
