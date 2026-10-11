# check_ftobi.praat  —  IntonaSphere AI
# Opens each automatic F_ToBI proposal with its sound, one at a time, so a trained
# annotator can correct it. Corrections are saved as <stem>_checked.TextGrid next to
# the proposal; the proposal itself is never overwritten. Already-checked files are
# skipped, so the script can be stopped and resumed.
#
# What to do in each editor window
#   1. Set Pitch > Pitch settings to the range shown in the pause window
#      (the speaker-adaptive range the tool used), so you see the same F0 track.
#   2. tones  : move, relabel or delete points; add missing ones (F_ToBI labels:
#               aL Hi L H* L* H+!H* H- L- H% L% !H%).
#   3. breaks : one point after every word, value 0-4 (add "p" for a hesitation).
#   4. AP / ip / IP : move or delete boundaries so the phrases match your breaks.
#   5. Remove the "?" from every label you have checked and accept.
#      (syllables, phones, evidence, nuc-edge and misc are there to help; they are
#      not scored.)
#   6. Click "Save & next".
# Then run:  python -m modules.validate_ftobi --auto <folder> --checked <folder>

form Check F_ToBI proposals
    sentence Proposals_folder /path/to/outputs/ftobi
    sentence Audio_folder /path/to/wav_and_textgrids
    word Annotator_initials XX
endform

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
        beginPause: "F_ToBI check " + string$ (i) + " / " + string$ (n) + ": " + stem$
            comment: "Pitch range used by the tool: " + fixed$ (floor, 0) + " - " + fixed$ (ceiling, 0) + " Hz"
            comment: "Proposed nuclear configuration: " + nuclear$
            comment: "Correct tones, breaks, AP / ip / IP; delete '?' when you accept a label."
        clicked = endPause: "Save & next", "Skip", "Stop", 1
        if clicked = 1
            selectObject: tg
            Save as text file: checked$
            appendFileLine: proposals_folder$ + "/checking_log.txt", stem$ + tab$ + annotator_initials$ + tab$ + date$ ()
            done = done + 1
        endif
        removeObject: snd, tg
        if clicked = 3
            removeObject: list, table
            exitScript: "Stopped after " + string$ (done) + " file(s). Run the script again to resume."
        endif
    endif
endfor
removeObject: list, table
writeInfoLine: "Checked ", done, " file(s). Corrections saved as *_checked.TextGrid in ", proposals_folder$
