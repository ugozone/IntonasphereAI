# draw_final_domain.praat  -  IntonaSphere AI
#
# Draws the final-domain figure in Praat's Picture window, measured by Praat itself:
#   waveform | spectrogram + F0 | tiers (words, syllables, FINAL-DOMAIN, CUES)
#   zoom on the final syllable with onset, peak, offset and the fitted line | table of values
# and saves it as <file>_final_domain_praat.png (300 dpi) in the results folder.
#
# It reads the final syllable and the pitch range from IntonaSphere's output
# (final_domain_praat_check.csv and x_cues.TextGrid), so the Praat figure and the Python
# figure can be compared side by side. Leave "Only this file" empty to draw every file.

include intonasphere_measure.include

form Draw the final-domain figure in Praat
    sentence Audio_folder /path/to/test_data
    sentence Results_folder /path/to/outputs_selftest/run/final_domain
    sentence Only_this_file_(empty_=_all_files)
    real Slope_threshold_(ST/s) 1.5
    real Maximum_spectrogram_frequency_(Hz) 5000
endform

table = Read Table from comma-separated file: results_folder$ + "/final_domain_praat_check.csv"
n = Get number of rows
drawn = 0
for i to n
    selectObject: table
    file$ = Get value: i, "AUDIO_FILE"
    if only_this_file$ = "" or only_this_file$ = file$
        floor = Get value: i, "PITCH_FLOOR_HZ"
        ceiling = Get value: i, "PITCH_CEILING_HZ"
        t1 = Get value: i, "FINAL_SYLLABLE_START"
        t2 = Get value: i, "FINAL_SYLLABLE_END"
        stem$ = file$ - ".wav"
        stem$ = stem$ - ".WAV"
        @drawOne
        drawn = drawn + 1
    endif
endfor
removeObject: table
writeInfoLine: "Drew ", drawn, " figure(s): ", results_folder$, "/*_final_domain_praat.png"

procedure drawOne
    snd = Read from file: audio_folder$ + "/" + file$
    dur = Get total duration
    pitch = To Pitch: 0.01, floor, ceiling
    selectObject: snd
    spectrogram = To Spectrogram: 0.005, maximum_spectrogram_frequency, 0.002, 20, "Gaussian"
    tg = Read from file: results_folder$ + "/" + stem$ + "_cues.TextGrid"
    # keep only the tiers worth showing
    ntiers = Get number of tiers
    for k from 0 to ntiers - 1
        tier = ntiers - k
        name$ = Get tier name: tier
        if index (" ORT-MAU MAS words word syllabe syllable UTT-AUTO SYL-AUTO FINAL-DOMAIN FINAL-PHONES CONTOUR CUES ", " " + name$ + " ") = 0
            nleft = Get number of tiers
            if nleft > 1
                Remove tier: tier
            endif
        endif
    endfor
    @fdMeasure: pitch, t1, t2
    @fdClass: fdMeasure.slope, slope_threshold
    selectObject: snd
    intensity = To Intensity: max (floor, 50), 0.01, "yes"
    int_p = Get mean: t1, t2, "energy"

    Erase all
    Font size: 10
    Line width: 1
    Colour: "Black"
    # title
    Select outer viewport: 0, 11, 0, 0.6
    Axes: 0, 1, 0, 1
    Font size: 14
    Text: 0.02, "left", 0.55, "half", "##" + replace$ (stem$, "_", " ", 0) + "##   final-syllable domain (measured in Praat)"
    Font size: 10

    # 1. waveform
    Select outer viewport: 0, 7.6, 0.5, 1.7
    selectObject: snd
    Draw: 0, 0, 0, 0, "no", "Curve"
    Axes: 0, dur, 0, 1
    Colour: "{0.85, 0.5, 0.1}"
    Line width: 2
    Draw line: t1, 0, t1, 1
    Draw line: t2, 0, t2, 1
    Line width: 1
    Colour: "Black"

    # 2. spectrogram + F0
    Select outer viewport: 0, 7.6, 1.5, 4.6
    selectObject: spectrogram
    Paint: 0, 0, 0, 0, 100, "yes", 50, 6, 0, "no"
    Draw inner box
    Marks left every: 1, 1000, "yes", "yes", "no"
    Text left: "yes", "Frequency (Hz)"
    selectObject: pitch
    Colour: "Blue"
    Speckle: 0, 0, floor, ceiling, "no"
    Marks right every: 1, 50, "yes", "yes", "no"
    Text right: "yes", "F0 (Hz)"
    Axes: 0, dur, 0, 1
    Colour: "{0.85, 0.5, 0.1}"
    Line width: 2
    Draw line: t1, 0, t1, 1
    Draw line: t2, 0, t2, 1
    Line width: 1
    Colour: "Black"

    # 3. tiers
    Select outer viewport: 0, 7.6, 4.4, 7.4
    selectObject: tg
    Draw: 0, 0, "yes", "no", "yes"
    Axes: 0, dur, 0, 1
    Colour: "{0.85, 0.5, 0.1}"
    Line width: 2
    Draw line: t1, 0, t1, 1
    Draw line: t2, 0, t2, 1
    Line width: 1
    Colour: "Black"

    # 4. zoom on the final syllable
    z1 = max (0, t1 - 0.12)
    z2 = min (dur, t2 + 0.05)
    Select outer viewport: 7.9, 11, 0.5, 4.2
    selectObject: pitch
    zlo = Get minimum: z1, z2, "Hertz", "None"
    zhi = Get maximum: z1, z2, "Hertz", "None"
    if zlo = undefined
        zlo = floor
        zhi = ceiling
    endif
    zlo = zlo - 15
    zhi = zhi + 25
    Colour: "Blue"
    Speckle: z1, z2, zlo, zhi, "yes"
    Text left: "yes", "F0 (Hz)"
    Text top: "no", "##Final-syllable domain"
    Axes: z1, z2, zlo, zhi
    Colour: "{0.85, 0.5, 0.1}"
    Line width: 2
    Draw line: t1, zlo, t1, zhi
    Draw line: t2, zlo, t2, zhi
    Line width: 1
    if fdMeasure.nv >= 3
        # fitted line (least squares in semitones), drawn in Hz over the voiced span
        Colour: "Red"
        Line width: 2
        ta = fdMeasure.tv [1]
        tb = fdMeasure.tv [fdMeasure.nv]
        nseg = 20
        for s to nseg
            xa = ta + (s - 1) * (tb - ta) / nseg
            xb = ta + s * (tb - ta) / nseg
            ya = 100 * 2 ^ ((fdMeasure.intercept + fdMeasure.slope * xa) / 12)
            yb = 100 * 2 ^ ((fdMeasure.intercept + fdMeasure.slope * xb) / 12)
            Draw line: xa, ya, xb, yb
        endfor
        Line width: 1
        Colour: "Black"
        Draw circle (mm): fdMeasure.onsetTime, fdMeasure.onset, 1.5
        Draw circle (mm): fdMeasure.offsetTime, fdMeasure.offset, 1.5
        Text: fdMeasure.onsetTime, "right", fdMeasure.onset, "bottom", "onset " + fixed$ (fdMeasure.onset, 0) + " Hz "
        Text: fdMeasure.offsetTime, "left", fdMeasure.offset, "bottom", " offset " + fixed$ (fdMeasure.offset, 0) + " Hz"
    endif
    Colour: "Black"

    # 5. values
    Select outer viewport: 7.9, 11, 4.4, 7.4
    Axes: 0, 1, 0, 11
    lines$ [1] = "Final syllable: " + fixed$ (t1, 3) + " - " + fixed$ (t2, 3) + " s"
    lines$ [2] = "Duration: " + fixed$ ((t2 - t1) * 1000, 0) + " ms"
    lines$ [3] = "F0 onset: " + fixed$ (fdMeasure.onset, 0) + " Hz at " + fixed$ (fdMeasure.onsetTime, 3) + " s"
    lines$ [4] = "F0 peak: " + fixed$ (fdMeasure.peak, 0) + " Hz at " + fixed$ (fdMeasure.peakTime, 3) + " s"
    lines$ [5] = "F0 offset: " + fixed$ (fdMeasure.offset, 0) + " Hz at " + fixed$ (fdMeasure.offsetTime, 3) + " s"
    lines$ [6] = "Change onset to offset: " + fixed$ (fdMeasure.change, 1) + " ST"
    lines$ [7] = "Fitted slope: " + fixed$ (fdMeasure.slope, 1) + " ST/s"
    lines$ [8] = "Intensity: " + fixed$ (int_p, 1) + " dB"
    lines$ [9] = "Contour: " + fdClass.class$ + "  (threshold " + fixed$ (slope_threshold, 1) + " ST/s)"
    lines$ [10] = "Pitch range: " + fixed$ (floor, 0) + " - " + fixed$ (ceiling, 0) + " Hz"
    for k to 10
        Text: 0, "left", 11 - k, "half", lines$ [k]
    endfor

    Select outer viewport: 0, 11, 0, 7.5
    Save as 300-dpi PNG file: results_folder$ + "/" + stem$ + "_final_domain_praat.png"
    removeObject: snd, pitch, spectrogram, tg, intensity
endproc
