# draw_ftobi.praat  -  IntonaSphere AI
#
# Draws the F_ToBI figure in Praat's Picture window: Praat's own F0 track (same pitch range
# as the tool) above the tiers tones, words, breaks, AP, ip, IP and syllables, with a line
# from every tone down through the F0 panel. Saves <file>_ftobi_praat.png (300 dpi).
#
# Use it on the proposals (x_ftobi.TextGrid) or, after checking, on your corrected files
# (x_checked.TextGrid): set "TextGrid suffix" to _checked. Leave "Only this file" empty
# to draw every file.

form Draw the F_ToBI figure in Praat
    sentence Audio_folder /path/to/test_data
    sentence Results_folder /path/to/outputs_selftest/run/ftobi
    word TextGrid_suffix _ftobi
    sentence Only_this_file_(empty_=_all_files)
endform

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
            appendInfoLine: "No ", tgfile$, " - skipped"
        endif
    endif
endfor
removeObject: table
appendInfoLine: "Drew ", drawn, " figure(s): ", results_folder$, "/*", textGrid_suffix$, "_praat.png"

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
