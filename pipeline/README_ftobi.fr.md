# IntonaSphere AI : assistant F_ToBI

[English](README_ftobi.md) | **Français**

`modules/ftobi_annotator.py` prend le WAV de chaque question et son TextGrid WebMAUS. Il **propose** une annotation F_ToBI complète sous forme de tiers Praat : tons, indices de rupture, AP / ip / IP, syllabes et phones en API. Un annotateur formé vérifie ensuite la proposition dans Praat.

`modules/validate_ftobi.py` mesure ce que l'annotateur a dû corriger, et c'est ce chiffre de validation que l'on rapporte dans l'article. L'outil ne remplace jamais l'annotateur. Il produit un premier jet vérifiable, ce qui rend l'annotation de 129 occurrences faisable et reproductible.

## Le lancer

```bash
python3 install.py             # installe tout, en français (choix 2)
python -m modules.ftobi_annotator --folder data/wav_et_textgrids --out outputs/ftobi --lang fr
```

Installation à la main : `pip install numpy scipy pandas matplotlib openpyxl praat-parselmouth requests`, plus `pip install faster-whisper` seulement pour les enregistrements non PFC sans `.txt`.

Le dossier contient les WAV et, si vous les avez, leurs TextGrids WebMAUS ou leurs fichiers texte (voir ci-dessous). Chaque seuil peut être modifié en ligne de commande, par exemple `--dur-ratio 1.5`. Les valeurs utilisées sont enregistrées dans la feuille PARAMETERS de `ftobi_annotations.xlsx`. `--lang` ne change que la langue des messages : les étiquettes F_ToBI, les noms de tiers et de colonnes sont identiques en anglais et en français.

### Ce que le dossier peut contenir : trois points d'entrée

| Vous fournissez | Ce que fait l'outil | Noté dans `ftobi_tokens.csv` |
|---|---|---|
| `x.wav` + `x.TextGrid` | Utilise votre TextGrid WebMAUS tel quel. C'est le parcours d'origine, et le fichier n'est jamais écrasé. | `ALIGNMENT_SOURCE = user_textgrid` |
| `x.wav` + `x.txt` | Envoie votre phrase et l'audio à WebMAUS (français), puis enregistre le TextGrid | `TEXT_SOURCE = user_txt` |
| `x.wav` seul, nom PFC (`…tw1/2/3`) | Tire le texte de la question du nom de fichier (Q1/Q2/Q3) et l'envoie à WebMAUS | `TEXT_SOURCE = pfc_texte_lu` |
| `x.wav` seul, tout autre enregistrement | Le transcrit avec faster-whisper (français) et écrit `x.asr.txt`, puis l'envoie à WebMAUS | `TEXT_SOURCE = asr`. **Vérifiez cette transcription.** |

L'option `--align` règle jusqu'où va l'outil :

- `--align none` rétablit le comportement d'origine : un WAV sans TextGrid est ignoré.
- `--align pfc` n'aligne automatiquement que les noms de fichiers PFC et les fichiers qui ont un `.txt`.
- `--align any` est la valeur par défaut.

Les nouveaux TextGrids vont dans `<out>/aligned/`, avec `alignment_log.csv`, et sont réutilisés lors des analyses suivantes.

**À propos de la transcription.** Pour corriger une transcription, modifiez `x.asr.txt`, enregistrez-le sous `x.txt`, supprimez `<out>/aligned/x.TextGrid` et relancez. Votre texte a alors la priorité.

**À propos de WebMAUS.** L'outil demande toujours le français (`fra-FR`). Il appelle la chaîne BAS `G2P_MAUS_PHO2SYL`, qui donne les mêmes tiers que vos fichiers, y compris le tier des syllabes MAS.

- Si cet appel échoue, l'outil utilise `runMAUSBasic` et construit lui-même le tier MAS : les phones sont regroupés en syllabes à l'intérieur de chaque mot, selon les règles d'attaque du français. Sur vos 9 fichiers WebMAUS d'origine, ce tier reconstruit concordait avec celui de WebMAUS pour 110 syllabes sur 110.
- Le service demande une connexion internet et est gratuit pour la recherche académique et non lucrative.
- L'audio est envoyé au serveur BAS de Munich, qui le conserve 24 heures. Vérifiez que c'est compatible avec les conditions d'utilisation des données PFC.

Pour ne produire que les TextGrids, sans F_ToBI, par exemple pour le visualiseur du domaine final :

```bash
python -m modules.auto_align --folder data/wavs --out data/wavs      # TextGrids enregistrés à côté des WAV
```

| Résultat | Contenu |
|---|---|
| `<nom>_ftobi.TextGrid` | La proposition (tiers ci-dessous) |
| `<nom>_ftobi.png` | Courbe de F0 avec les tons, les ruptures et les syntagmes |
| `ftobi_tokens.csv` | Une ligne par énoncé : configuration nucléaire, phrasé, tons, nombre d'étiquettes incertaines, avertissements |
| `ftobi_syllables.csv` | Une ligne par syllabe : chaque indice et chaque décision |
| `ftobi_annotations.xlsx` | Les deux tableaux et les paramètres |
| `ftobi_praat_ranges.csv` | La plage de F0 utilisée pour chaque fichier (lue par le script Praat) |

## Tiers du TextGrid

| Tier | Type | Contenu |
|---|---|---|
| tones | points | Tons F_ToBI : aL, Hi, L, H\*, L\*, H+!H\*, H-, L-, H%, L%, !H% |
| words | intervalles | Mots orthographiques (ORT-MAU) |
| breaks | points | Indice de rupture après chaque mot : 0–4, avec `p` pour une pause d'hésitation |
| AP / ip / IP | intervalles | Syntagmes accentuels, intermédiaires et intonatifs |
| syllables | intervalles | Syllabes en API (MAS, converties du SAMPA) |
| phones | intervalles | Phones en API (MAU) |
| evidence | points | Indices mesurés sur chaque syllabe susceptible de clore un AP, p. ex. `D1.92 H+3.3 R1.4 P0ms [DH]` |
| nuc-edge | points | Test de Beyssade et al. (2007), décrit ci-dessous |
| misc | intervalles | Avertissements : syllabes sans voyelle, SAMPA non français, transcription ≠ forme attendue |

Les noms de tiers restent en anglais dans les deux langues.

**Une étiquette terminée par `?` est une proposition peu sûre**, parce que son indice se trouve à moins de 15 % du seuil. C'est la convention ToBI pour les étiquettes incertaines, et ce sont les étiquettes à vérifier en premier.

## Les règles et leur source

| Étape | Règle | Source |
|---|---|---|
| Mots accentuables | L'accent final tombe sur la dernière syllabe pleine (sans schwa) d'un mot lexical. Les clitiques et autres mots grammaticaux ne le portent jamais. Un adjectif prénominal directement suivi de son nom (*Premier ministre*, *grand honneur*) ne clôt pas un AP. | Delais-Roussarie et al. 2015, §3.1.2.1 |
| Frontière d'AP (2) | Un candidat devient un AP quand sa syllabe finale est proéminente, c'est-à-dire : durée de la rime ≥ 1,61 × la moyenne des 3 syllabes précédentes et des 3 suivantes, F0 ≥ 1,43 demi-ton au-dessus d'elles, montée ≥ 2,07 demi-tons sur la rime, ou pause suivante ≥ 100 ms. | Avanzi et al. 2011, seuils de la parole lue |
| Frontière d'ip (3) | Une frontière d'AP avec un allongement plus fort (≥ 2,0) ou une pause. Une pause seule reçoit `3?`, car elle peut être une hésitation de lecture. | Delais-Roussarie et al. 2015, §3.1.2.1 ; Michelas & D'Imperio 2012 |
| Frontière d'IP (4) | La fin de l'énoncé, ou une pause ≥ 300 ms après une syllabe allongée (marquée `4?`) | Delais-Roussarie et al. 2015, §3.1.2.1 |
| Ruptures 0 / 1 | 0 après un clitique, 1 entre les mots à l'intérieur d'un AP | Delais-Roussarie et al. 2015, §3.1.3 |
| Tons de l'AP | L'AP suit le schéma (aL)(Hi)(L)H\*. L'accent final est H\* quand la syllabe monte ou est un pic local, et L\* sinon, ce qui n'est pas contrastif avant le noyau. Hi est un pic précoce sur une des premières syllabes, ou sur un mot qu- ou *est-ce que*, situé ≥ 1,5 demi-ton au-dessus du bas initial de l'AP et ≥ 1 demi-ton au-dessus de ce qui suit. aL est le bas initial de l'AP avant le premier H. Un bord d'ip est H- s'il est haut ou montant et L- s'il est bas ou descendant. | Delais-Roussarie et al. 2015, ex. (3), §3.1.2.2, §3.3.4.1 |
| Configuration nucléaire | L'accent et le ton de frontière tombent sur la même syllabe finale, par encombrement tonal. T\* est lu au début de la voyelle finale, par rapport à la pénultième et à la plage du locuteur. T% est lu d'après le mouvement sur la rime : ≥ +1,5 demi-ton donne H%, ≤ −1,5 demi-ton donne L%, et un mouvement plat prend le niveau de T\*. Une pénultième basse avant H\* donne le L initial de (L)H\*. Une pénultième haute et allongée suivie d'une finale plus basse donne H+!H\* !H%. | Delais-Roussarie et al. 2015, tableau 3.6 |
| Ton syntagmatique au bord gauche | Les interrogatives ancrent H- (avec un noyau descendant L\*) ou L- (avec un noyau montant H\*) au bord gauche du domaine nucléaire. Ce bord est l'expression qu- ou le verbe inversé, comme H- sur [til] de *ira-t-il*. | Beyssade, Delais-Roussarie & Marandin 2007, ex. (12)–(21) |

Avant le calcul de toute étiquette, les trames où la F0 saute de plus de 4 demi-tons en 10 ms sont retirées. Une vraie F0 ne peut pas varier aussi vite : ce sont des erreurs d'octave ou du bruit de fricative, et leur nombre est indiqué pour chaque occurrence. Toutes les valeurs de F0 sont en demi-tons par rapport à la médiane du locuteur dans l'énoncé.

## Transcription phonétique

WebMAUS écrit en SAMPA, qui est converti en API. Chaque mot est ensuite comparé à sa forme canonique attendue dans les questions PFC (`PFC_LEXICON`). La variation régulière est tolérée : o/ɔ, e/ɛ, ø/œ, schwa présent ou absent, et le glissement i~ij. Sur les échantillons, la vérification a trouvé trois problèmes :

- **`Qu'est-ce` → /kts/** dans tous les fichiers. L'étape graphème-phonème de WebMAUS transcrit mal ce mot : sa syllabe n'a pas de voyelle et sa F0 est lue sur toute la syllabe. Corrigez la forme KAN, ou l'orthographe du mot envoyée à WebMAUS, avant l'analyse complète.
- **64aab1tw1 contient du SAMPA allemand** (`I`, `aU`, `?`, `e:`). Ce fichier a presque certainement été aligné avec le modèle allemand : relancez-le avec **fra-FR**.
- Des étiquettes modifiées à la main comme `n\oeR` (un symbole Praat sans espace) et `mɑ̃nifɛstasjɔ̃`.

## Vérifier dans Praat, puis mesurer l'accord

1. Dans Praat, choisissez Open Praat script, ouvrez `praat/check_ftobi_fr.praat` (ou `check_ftobi.praat` en anglais) et lancez-le. Donnez-lui le dossier des résultats, le dossier audio et vos initiales.
2. Chaque fichier s'ouvre dans l'éditeur. Réglez **Pitch > Pitch settings** sur la plage affichée dans la fenêtre. Corrigez ensuite `tones`, `breaks` et `AP / ip / IP`, et supprimez le `?` de chaque étiquette que vous acceptez. Cliquez sur **Enregistrer et suivant**. Le fichier corrigé est enregistré sous `<nom>_checked.TextGrid` ; la proposition n'est jamais écrasée, et le script reprend là où vous vous êtes arrêté.
3. Mesurez l'accord :

```bash
python -m modules.validate_ftobi --auto outputs/ftobi --checked outputs/ftobi --out outputs/ftobi_validation
```

Le script rapporte ce qui suit, écrit dans `ftobi_validation.xlsx` :

- l'accord sur les indices de rupture, le κ de Cohen et le κ pondéré linéairement, avec une matrice de confusion ;
- la précision, le rappel et le F1 pour les frontières d'AP, d'ip et d'IP ;
- la détection des tons et le κ des étiquettes, par catégorie ;
- l'accord sur la configuration nucléaire ;
- l'accord pour les étiquettes sûres et pour les étiquettes `?`.

Si le signal `?` fonctionne, la plupart des corrections portent sur des étiquettes `?`.

Pour comparer les temps des frontières avec une ancienne annotation manuelle qui a des tiers de points AP et IP :

```bash
python -m modules.validate_ftobi --boundaries-only outputs/ftobi/64aab1tw2_ftobi.TextGrid 64aab1tw2m.TextGrid --tol 0.10
```

### Protocole pour l'article

Utilisez le même échantillon stratifié de 36 occurrences (graine 2027) que pour la validation acoustique. Deux annotateurs formés à F_ToBI corrigent chacun les propositions de façon indépendante, sans voir le travail de l'autre.

Rapportez :

- outil contre annotateur A, et outil contre annotateur B : ce qui a été corrigé ;
- annotateur A contre annotateur B sur leurs fichiers corrigés : le plafond humain.

À titre de comparaison, l'accord inter-annotateurs humain en ToBI est en général d'environ κ 0,6–0,8 pour les indices de rupture et les accents. Avanzi et al. (2011) rapportent κ = 0,67 entre experts pour la proéminence en français, et κ = 0,70 (pondéré linéairement) pour leur outil automatique face aux experts.

L'outil est acceptable quand son accord avec les annotateurs approche l'accord entre eux. Aucun accord qui ne vient pas de corrections humaines ne doit être rapporté.

## Limites

- Les règles portent sur de la parole lue alignée par WebMAUS. Les erreurs d'alignement, comme les syllabes sans voyelle, se répercutent. Ces cas sont signalés dans `misc`.
- Sans Parselmouth, un détecteur intégré inspiré de Praat est utilisé. Installez `praat-parselmouth` pour que la F0 soit celle de Praat.
- Les accents bitonaux (H+!H\*, H+H\*) et !H% sont rares et ne sont proposés qu'avec `?`.
- Les seuils viennent de la littérature et n'ont pas été ajustés sur ces données. Ne les ajustez que sur des fichiers corrigés par des annotateurs, et seulement sur des fichiers hors de l'échantillon de validation.

## Références

- Avanzi, M., Lacheret-Dujour, A., Obin, N. & Victorri, B. (2011). Toward a continuous modeling of French prosodic structure: Using acoustic features to predict prominence location and prominence degree. *Proceedings of Interspeech 2011*, Florence.
- Beyssade, C., Delais-Roussarie, E. & Marandin, J.-M. (2007). The prosody of interrogatives in French. *Nouveaux Cahiers de Linguistique Française* 28, 163–175.
- Delais-Roussarie, E., Post, B., Avanzi, M., Buthke, C., Di Cristo, A., Feldhausen, I., Jun, S.-A., Martin, P., Meisenburg, T., Rialland, A., Sichel-Bazin, R. & Yoo, H.-Y. (2015). Intonational phonology of French: Developing a ToBI system for French. In S. Frota & P. Prieto (eds.), *Intonation in Romance*, 63–100. Oxford University Press.
- Jun, S.-A. & Fougeron, C. (2002). Realizations of accentual phrase in French intonation. *Probus* 14, 147–172.
- Michelas, A. & D'Imperio, M. (2012). When syntax meets prosody: Tonal and duration variability in French accentual phrases. *Journal of Phonetics* 40, 816–829.
- Rosenberg, A. (2010). AuToBI: A tool for automatic ToBI annotation. *Proceedings of Interspeech 2010*, Makuhari.
- Kisler, T., Reichel, U. & Schiel, F. (2017). Multilingual processing of speech via web services. *Computer Speech & Language* 45, 326–347.
- Schiel, F. (1999). Automatic phonetic transcription of non-prompted speech. *Proceedings of ICPhS 1999*, 607–610. (WebMAUS)
