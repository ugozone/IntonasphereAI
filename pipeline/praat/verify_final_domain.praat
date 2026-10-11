# verify_final_domain.praat  -  IntonaSphere AI
#
# Re-measures, in Praat itself, every final-syllable value that IntonaSphere wrote,
# using the SAME final syllable, the SAME pitch range and the SAME definitions, and
# puts Praat's value next to the tool's value:
#
#   F0 onset / offset : median of the first / last 3 voiced pitch frames in the syllable
#   F0 peak           : highest voiced pitch frame in the syllable
#   slope             : least-squares line through the voiced frames, semitones per second
#   intensity         : mean intensity over the syllable (Praat "Get mean", energy)
#   contour           : rise if slope >= +threshold, fall if <= -threshold, else plateau
#
# Pitch: "To Pitch..." is Praat's standard autocorrelation method with default settings,
# which is what IntonaSphere calls through Parselmouth.
#
# Output: praat_verification.csv in the results folder (tool | Praat | difference per value)
# and a summary in the Info window. Differences near 0 = the tool's numbers are Praat's numbers.

include intonasphere_measure.include

form Verify IntonaSphere final-domain values in Praat
    sentence Audio_folder /path/to/test_data
    sentence Results_folder /path/to/outputs_selftest/run/final_domain
    real Slope_threshold_(ST/s) 1.5
endform

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
writeInfoLine: "IntonaSphere final-domain values re-measured in Praat (", n, " files)"
appendInfoLine: "Largest F0 difference (onset, peak, offset): ", fixed$ (maxdiff_hz, 3), " Hz"
appendInfoLine: "Largest slope difference: ", fixed$ (maxdiff_slope, 3), " ST/s"
appendInfoLine: "Largest intensity difference: ", fixed$ (maxdiff_db, 3), " dB"
appendInfoLine: "Same contour class: ", same, " / ", n
appendInfoLine: "Details: ", results_folder$, "/praat_verification.csv"
removeObject: table
