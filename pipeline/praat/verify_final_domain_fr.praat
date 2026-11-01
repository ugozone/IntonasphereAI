# verify_final_domain_fr.praat  -  IntonaSphere AI (version française de verify_final_domain.praat)
#
# Remesure dans Praat chaque valeur de la syllabe finale écrite par IntonaSphere, avec la MÊME
# syllabe finale, la MÊME plage de F0 et les MÊMES définitions, et place la valeur de Praat à côté
# de celle de l'outil :
#
#   début / fin de F0 : médiane des 3 premières / dernières trames voisées de la syllabe
#   pic de F0         : trame voisée la plus haute de la syllabe
#   pente             : droite des moindres carrés sur les trames voisées, en demi-tons par seconde
#   intensité         : intensité moyenne sur la syllabe (« Get mean » de Praat, énergie)
#   contour           : montée si pente >= +seuil, descente si <= -seuil, sinon plateau
#
# F0 : « To Pitch... » est la méthode d'autocorrélation standard de Praat, réglages par défaut,
# celle qu'IntonaSphere appelle via Parselmouth.
#
# Résultat : praat_verification.csv dans le dossier des résultats (outil | Praat | différence) et
# un résumé dans la fenêtre Info. Des différences proches de 0 = les nombres de l'outil sont ceux de Praat.

include intonasphere_measure.include

form Vérifier dans Praat les valeurs du domaine final d'IntonaSphere
    sentence Dossier_audio /chemin/vers/test_data
    sentence Dossier_des_resultats /chemin/vers/outputs_selftest/run/final_domain
    real Seuil_de_pente_(demi-tons/s) 1.5
endform
audio_folder$ = dossier_audio$
results_folder$ = dossier_des_resultats$
slope_threshold = seuil_de_pente

table = Read Table from comma-separated file: results_folder$ + "/final_domain_praat_check.csv"
n = Get number of rows
out = Create Table with column names: "verification", n, "AUDIO_FILE START END DUR ONSET_TOOL ONSET_PRAAT ONSET_DIFF PEAK_TOOL PEAK_PRAAT PEAK_DIFF OFFSET_TOOL OFFSET_PRAAT OFFSET_DIFF SLOPE_TOOL SLOPE_PRAAT SLOPE_DIFF INT_TOOL INT_PRAAT INT_DIFF CONTOUR_TOOL CONTOUR_PRAAT CONTOUR_SAME"
maxdiff_hz = 0
maxdiff_slope = 0
maxdiff_db = 0
same = 0
for i to n
    selectObject: table
    file$ = Get value: i, "AUDIO_FILE"
    floor = Get value: i, "PITCH_FLOOR_HZ"
    ceiling = Get value: i, "PITCH_CEILING_HZ"
    t1 = Get value: i, "FINAL_SYLLABLE_START"
    t2 = Get value: i, "FINAL_SYLLABLE_END"
    on_tool = Get value: i, "F0_ONSET_HZ"
    pk_tool = Get value: i, "F0_PEAK_HZ"
    off_tool = Get value: i, "F0_OFFSET_HZ"
    sl_tool = Get value: i, "FINAL_SLOPE_ST"
    int_tool = Get value: i, "FINAL_INTENSITY_MEAN_DB"
    cls_tool$ = Get value: i, "CONTOUR_CLASS"

    snd = Read from file: audio_folder$ + "/" + file$
    pitch = To Pitch: 0.01, floor, ceiling
    @fdMeasure: pitch, t1, t2
    @fdClass: fdMeasure.slope, slope_threshold
    selectObject: snd
    intensity = To Intensity: max (floor, 50), 0.01, "yes"
    int_p = Get mean: t1, t2, "energy"

    selectObject: out
    Set string value: i, "AUDIO_FILE", file$
    Set numeric value: i, "START", t1
    Set numeric value: i, "END", t2
    Set numeric value: i, "DUR", t2 - t1
    Set numeric value: i, "ONSET_TOOL", on_tool
    Set numeric value: i, "ONSET_PRAAT", fdMeasure.onset
    Set numeric value: i, "ONSET_DIFF", fdMeasure.onset - on_tool
    Set numeric value: i, "PEAK_TOOL", pk_tool
    Set numeric value: i, "PEAK_PRAAT", fdMeasure.peak
    Set numeric value: i, "PEAK_DIFF", fdMeasure.peak - pk_tool
    Set numeric value: i, "OFFSET_TOOL", off_tool
    Set numeric value: i, "OFFSET_PRAAT", fdMeasure.offset
    Set numeric value: i, "OFFSET_DIFF", fdMeasure.offset - off_tool
    Set numeric value: i, "SLOPE_TOOL", sl_tool
    Set numeric value: i, "SLOPE_PRAAT", fdMeasure.slope
    Set numeric value: i, "SLOPE_DIFF", fdMeasure.slope - sl_tool
    Set numeric value: i, "INT_TOOL", int_tool
    Set numeric value: i, "INT_PRAAT", int_p
    Set numeric value: i, "INT_DIFF", int_p - int_tool
    Set string value: i, "CONTOUR_TOOL", cls_tool$
    Set string value: i, "CONTOUR_PRAAT", fdClass.class$
    if fdClass.class$ = cls_tool$
        Set string value: i, "CONTOUR_SAME", "yes"
        same = same + 1
    else
        Set string value: i, "CONTOUR_SAME", "NO"
    endif
    maxdiff_hz = max (maxdiff_hz, abs (fdMeasure.onset - on_tool), abs (fdMeasure.peak - pk_tool), abs (fdMeasure.offset - off_tool))
    maxdiff_slope = max (maxdiff_slope, abs (fdMeasure.slope - sl_tool))
    maxdiff_db = max (maxdiff_db, abs (int_p - int_tool))
    removeObject: snd, pitch, intensity
endfor

selectObject: out
Save as comma-separated file: results_folder$ + "/praat_verification.csv"
writeInfoLine: "Valeurs du domaine final d'IntonaSphere remesurées dans Praat (", n, " fichiers)"
appendInfoLine: "Plus grande différence de F0 (début, pic, fin) : ", fixed$ (maxdiff_hz, 3), " Hz"
appendInfoLine: "Plus grande différence de pente : ", fixed$ (maxdiff_slope, 3), " ST/s"
appendInfoLine: "Plus grande différence d'intensité : ", fixed$ (maxdiff_db, 3), " dB"
appendInfoLine: "Même classe de contour : ", same, " / ", n
appendInfoLine: "Détails : ", results_folder$, "/praat_verification.csv"
removeObject: table
