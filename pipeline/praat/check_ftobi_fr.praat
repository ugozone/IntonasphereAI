# check_ftobi_fr.praat  —  IntonaSphere AI (version française de check_ftobi.praat)
# Ouvre une à une chaque proposition F_ToBI automatique avec son son, pour qu'un annotateur
# formé la corrige. Les corrections sont enregistrées sous <stem>_checked.TextGrid à côté de
# la proposition ; la proposition elle-même n'est jamais écrasée. Les fichiers déjà vérifiés
# sont sautés : on peut arrêter le script et le reprendre.
#
# Dans chaque fenêtre d'édition
#   1. Réglez Pitch > Pitch settings sur la plage indiquée dans la fenêtre de pause
#      (la plage adaptée au locuteur utilisée par l'outil), pour voir la même courbe de F0.
#   2. tones  : déplacez, renommez ou supprimez des points ; ajoutez ceux qui manquent
#               (étiquettes F_ToBI : aL Hi L H* L* H+!H* H- L- H% L% !H%).
#   3. breaks : un point après chaque mot, valeur 0-4 (ajoutez "p" pour une hésitation).
#   4. AP / ip / IP : déplacez ou supprimez des frontières pour que les syntagmes suivent vos breaks.
#   5. Retirez le "?" de chaque étiquette vérifiée et acceptée.
#      (syllables, phones, evidence, nuc-edge et misc sont là pour aider ; ils ne sont pas évalués.)
#   6. Cliquez sur « Enregistrer et suivant ».
# Ensuite :  python -m modules.validate_ftobi --auto <dossier> --checked <dossier>

form Vérifier les propositions F_ToBI
    sentence Dossier_des_propositions /chemin/vers/outputs/ftobi
    sentence Dossier_audio /chemin/vers/wav_et_textgrids
    word Initiales_annotateur XX
endform
proposals_folder$ = dossier_des_propositions$
audio_folder$ = dossier_audio$
annotator_initials$ = initiales_annotateur$


table = Read Table from comma-separated file: proposals_folder$ + "/ftobi_praat_ranges.csv"
list = Create Strings as file list: "list", proposals_folder$ + "/*_ftobi.TextGrid"
n = Get number of strings
done = 0
for i to n
    selectObject: list
    tgname$ = Get string: i
    stem$ = tgname$ - "_ftobi.TextGrid"
    checked$ = proposals_folder$ + "/" + stem$ + "_checked.TextGrid"
    if not fileReadable (checked$)
        selectObject: table
        row = Search column: "AUDIO_FILE", stem$ + ".wav"
        floor = 75
        ceiling = 500
        nuclear$ = "?"
        if row > 0
            floor = Get value: row, "PITCH_FLOOR_HZ"
            ceiling = Get value: row, "PITCH_CEILING_HZ"
            nuclear$ = Get value: row, "NUCLEAR"
        endif
        snd = Read from file: audio_folder$ + "/" + stem$ + ".wav"
        tg = Read from file: proposals_folder$ + "/" + tgname$
        selectObject: snd, tg
        View & Edit
        beginPause: "Vérification F_ToBI " + string$ (i) + " / " + string$ (n) + ": " + stem$
            comment: "Plage de F0 utilisée par l'outil : " + fixed$ (floor, 0) + " - " + fixed$ (ceiling, 0) + " Hz"
            comment: "Configuration nucléaire proposée : " + nuclear$
            comment: "Corrigez tones, breaks, AP / ip / IP ; supprimez le '?' quand vous acceptez une étiquette."
        clicked = endPause: "Enregistrer et suivant", "Passer", "Arrêter", 1
        if clicked = 1
            selectObject: tg
            Save as text file: checked$
            appendFileLine: proposals_folder$ + "/checking_log.txt", stem$ + tab$ + annotator_initials$ + tab$ + date$ ()
            done = done + 1
        endif
        removeObject: snd, tg
        if clicked = 3
            removeObject: list, table
            exitScript: "Arrêt après " + string$ (done) + " fichier(s). Relancez le script pour reprendre."
        endif
    endif
endfor
removeObject: list, table
writeInfoLine: done, " fichier(s) vérifié(s). Corrections enregistrées sous *_checked.TextGrid dans ", proposals_folder$
