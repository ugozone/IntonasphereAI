# Vérifier les valeurs acoustiques et dessiner les graphiques dans Praat

[English](PRAAT_VERIFICATION.md) | **Français**

Tous les scripts sont dans le dossier `praat/`. Chaque script existe en deux versions qui font exactement la même chose : `x.praat` (formulaires et messages en anglais) et `x_fr.praat` (en français). Lancez-les depuis Praat avec **Praat → Open Praat script… → Run → Run**.
Quand le formulaire demande un dossier, donnez son chemin complet : faites glisser le dossier du Finder dans le Terminal et copiez le texte qui apparaît (sous Windows : clic droit sur le dossier → *Copier en tant que chemin d'accès*).
Si Praat demande l'autorisation d'enregistrer un fichier, acceptez.

| Script | Rôle | Résultat |
|---|---|---|
| `verify_final_domain_fr.praat` | Remesure dans Praat chaque valeur de la syllabe finale, avec la même syllabe, la même plage de F0 et les mêmes définitions que l'outil, et compare chaque valeur à celle de l'outil | `praat_verification.csv` + un résumé dans la fenêtre Info |
| `draw_final_domain_fr.praat` | Dessine dans Praat le graphique du domaine final (oscillogramme, spectrogramme + F0, tiers, zoom sur la syllabe finale, valeurs) | `x_final_domain_praat.png` |
| `draw_ftobi_fr.praat` | Dessine dans Praat le graphique F_ToBI (F0 + tons, mots, ruptures, AP, ip, IP, syllabes) | `x_ftobi_praat.png` (ou `x_checked_praat.png`) |
| `check_ftobi_fr.praat` | Permet de corriger les propositions F_ToBI un fichier à la fois | `x_checked.TextGrid` |

Remplissez les formulaires ainsi :
- Dossier audio : le dossier des WAV, p. ex. `test_data`.
- Dossier des résultats : `outputs_selftest/run/final_domain` pour les deux premiers scripts, et `outputs_selftest/run/ftobi` pour les scripts F_ToBI.

Le fichier `intonasphere_measure.include` doit rester dans le même dossier que les scripts (les versions anglaise et française l'utilisent toutes les deux). Les fichiers produits ont les mêmes noms et les mêmes colonnes avec les deux versions.

## Vérifier une valeur à la main dans l'éditeur de Praat (sans script)
1. Ouvrez ensemble `x.wav` et `final_domain/x_cues.TextGrid`, puis cliquez sur **View & Edit**.
2. Choisissez **Pitch → Pitch settings…** et entrez la plage donnée par `PITCH_FLOOR_HZ` et `PITCH_CEILING_HZ` dans le classeur.
3. Cliquez sur l'intervalle **FINAL-DOMAIN**. Son début, sa fin et sa durée s'affichent au-dessus de l'oscillogramme : comparez-les à `FINAL_SYLLABLE_START`, `FINAL_SYLLABLE_END` et `FINAL_SYLLABLE_DURATION`.
4. L'intervalle étant sélectionné :
   - **Pitch → Get maximum pitch** (F10) doit donner `F0_PEAK_HZ`.
   - **Intensity → Get intensity** (F11) doit donner `FINAL_INTENSITY_MEAN_DB`.
5. Cliquez sur chaque point du tier **CUES** (début, pic, fin), puis **Pitch → Get pitch** (F5). La valeur doit correspondre au nombre écrit sur le point. Le début et la fin sont des médianes de trois trames : un simple clic peut donc différer de 1 à 2 Hz.
6. Regardez la courbe de F0 sur la syllabe. La montée, la descente ou le plateau est-il celui qu'indique l'outil ? Y a-t-il des sauts d'octave ?

(Les menus de Praat sont nommés ici en anglais ; si votre Praat est réglé dans une autre langue, les commandes sont au même endroit.)

**Petits écarts :** ils sont normaux quand on vérifie à la main, parce qu'un clic tombe entre deux trames. Avec le script, les écarts doivent être proches de 0. Un grand écart signifie que la courbe de F0 diffère, par exemple à cause d'un saut d'octave ou d'une autre plage de F0. Examinez ce fichier.
