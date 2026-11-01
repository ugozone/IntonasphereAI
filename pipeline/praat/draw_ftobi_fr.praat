# draw_ftobi_fr.praat  -  IntonaSphere AI (version française de draw_ftobi.praat)
#
# Dessine la figure F_ToBI dans la fenêtre Picture de Praat : la courbe de F0 de Praat (même plage
# que l'outil) au-dessus des tiers tones, words, breaks, AP, ip, IP et syllables, avec une ligne
# de chaque ton vers la courbe de F0. Enregistre <fichier>_ftobi_praat.png (300 dpi).
#
# À utiliser sur les propositions (x_ftobi.TextGrid) ou, après vérification, sur vos fichiers
# corrigés (x_checked.TextGrid) : mettez « Suffixe du TextGrid » à _checked. Laissez
# « Seulement ce fichier » vide pour tout dessiner.

form Dessiner la figure F_ToBI dans Praat
    sentence Dossier_audio /chemin/vers/test_data
    sentence Dossier_des_resultats /chemin/vers/outputs_selftest/run/ftobi
    word Suffixe_du_TextGrid _ftobi
    sentence Seulement_ce_fichier_(vide_=_tous_les_fichiers)
endform
audio_folder$ = dossier_audio$
results_folder$ = dossier_des_resultats$
textGrid_suffix$ = suffixe_du_TextGrid$
only_this_file$ = seulement_ce_fichier$

table = Read Table from comma-separated file: results_folder$ + "/ftobi_praat_ranges.csv"
n = Get number of rows
drawn = 0
for i to n
    selectObject: table
    file$ = Get value: i, "AUDIO_FILE"
    if only_this_file$ = "" or only_this_file$ = file$
        floor = Get value: i, "PITCH_FLOOR_HZ"
        ceiling = Get value: i, "PITCH_CEILING_HZ"
        nuclear$ = Get value: i, "NUCLEAR"
        stem$ = file$ - ".wav"
        stem$ = stem$ - ".WAV"
        tgfile$ = results_folder$ + "/" + stem$ + textGrid_suffix$ + ".TextGrid"
        if fileReadable (tgfile$)
            @drawOne
            drawn = drawn + 1
        else
            appendInfoLine: "Pas de ", tgfile$, " - ignoré"
        endif
    endif
endfor
removeObject: table
appendInfoLine: drawn, " figure(s) dessinée(s) : ", results_folder$, "/*", textGrid_suffix$, "_praat.png"

procedure drawOne
    snd = Read from file: audio_folder$ + "/" + file$
    dur = Get total duration
    pitch = To Pitch: 0.01, floor, ceiling
    tg = Read from file: tgfile$
    ntiers = Get number of tiers
    for k from 0 to ntiers - 1
        tier = ntiers - k
        name$ = Get tier name: tier
        if index (" tones words breaks AP ip IP syllables ", " " + name$ + " ") = 0
            nleft = Get number of tiers
            if nleft > 1
                Remove tier: tier
            endif
        endif
    endfor
    # tone points (tier 1 after the clean-up, if it is the tones tier)
    tonetier = 0
    ntiers = Get number of tiers
    for k to ntiers
        name$ = Get tier name: k
        if name$ = "tones"
            tonetier = k
        endif
    endfor

    Erase all
    Font size: 10
    Line width: 1
    Colour: "Black"
    Select outer viewport: 0, 11, 0, 0.6
    Axes: 0, 1, 0, 1
    Font size: 14
    Text: 0.02, "left", 0.55, "half", "##" + replace$ (stem$, "_", " ", 0) + "##   F0 (Praat) and F_ToBI tiers   nuclear: " + replace$ (nuclear$, "%", "", 0)
    Font size: 10

    # F0 panel
    Select outer viewport: 0, 11, 0.5, 4.0
    selectObject: pitch
    Colour: "Blue"
    Speckle: 0, 0, floor, ceiling, "no"
    Colour: "Black"
    Draw inner box
    Marks left every: 1, 50, "yes", "yes", "no"
    Text left: "yes", "F0 (Hz)"
    if tonetier > 0
        selectObject: tg
        np = Get number of points: tonetier
        Axes: 0, dur, 0, 1
        for p to np
            selectObject: tg
            t = Get time of point: tonetier, p
            lab$ = Get label of point: tonetier, p
            if left$ (lab$, 1) = "H"
                Colour: "Red"
            else
                Colour: "Blue"
            endif
            if index (lab$, "?") > 0
                Dotted line
            else
                Solid line
            endif
            Draw line: t, 0, t, 1
        endfor
        Solid line
        Colour: "Black"
    endif

    # tiers
    Select outer viewport: 0, 11, 3.8, 8.6
    selectObject: tg
    Draw: 0, 0, "yes", "no", "yes"

    Select outer viewport: 0, 11, 0, 8.6
    Save as 300-dpi PNG file: results_folder$ + "/" + stem$ + textGrid_suffix$ + "_praat.png"
    removeObject: snd, pitch, tg
endproc
