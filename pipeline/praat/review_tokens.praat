# review_tokens.praat  —  IntonaSphere AI
# Opens, one at a time, the tokens listed by  python3 -m modules.review_list  (review_list.tsv):
# the recording with the TextGrid the run used, zoomed to the end of the sentence, with the
# pitch range set to 50-500 Hz so that low and creaky endings are visible.
# For each token, choose a decision in the small window and click "Save & next":
#   Include / Exclude            -> written to manual_overrides.csv (CHECKED = yes)
#   TextGrid corrected           -> the TextGrid you edited is saved in place (a copy of the
#                                   original is kept in review_backups/); the next run_all
#                                   re-measures the token
#   F0 only with a lower floor   -> noted in manual_overrides.csv; the token stays excluded for now
#   Not sure                     -> nothing is written; the token is listed again next time
# Tokens that already have CHECKED = yes in manual_overrides.csv are skipped, so you can stop
# at any time and continue later. Afterwards, in Terminal:
#   python3 -m modules.selection --results <results folder>/intonasphere_results.xlsx
# (or run_all again if you corrected a TextGrid).

form Review tokens
    sentence Review_list /path/to/outputs/review_list.tsv
    sentence Overrides_file /path/to/outputs/manual_overrides.csv
    boolean Skip_tokens_already_checked 1
endform

if not fileReadable (review_list$)
    exitScript: "Cannot read the review list:", newline$, review_list$, newline$,
    ... "Make it in Terminal with:  python3 -m modules.review_list --results <results folder>/intonasphere_results.xlsx --folder <recordings folder>"
endif
nocheck Text writing preferences: "UTF-8"
if not fileReadable (overrides_file$)
    writeFileLine: overrides_file$, "TOKEN_ID,CHECKED,MANUAL_DECISION,MANUAL_NOTE"
endif

# backups go next to the results, never into the recordings folder
cut = max (rindex (review_list$, "/"), rindex (review_list$, "\"))
backup_folder$ = left$ (review_list$, cut) + "review_backups"
createFolder: backup_folder$

table = Read Table from tab-separated file: review_list$
n = Get number of rows
decided = 0
corrected = 0
stop = 0
for i to n
    if not stop
        selectObject: table
        token$ = Get value: i, "TOKEN_ID"
        task = Get value: i, "TASK"
        wav$ = Get value: i, "AUDIO_PATH"
        tg$ = Get value: i, "TEXTGRID_PATH"
        z0 = Get value: i, "ZOOM_START"
        z1 = Get value: i, "ZOOM_END"
        what$ = Get value: i, "WHAT_TO_DO"
        why$ = Get value: i, "WHY_LISTED"
        already = 0
        if skip_tokens_already_checked
            text$ = readFile$ (overrides_file$)
            if index (text$, newline$ + token$ + ",yes") > 0
                already = 1
            endif
        endif
        if already
            appendInfoLine: token$, ": already checked, skipped"
        elsif not fileReadable (wav$) or not fileReadable (tg$)
            appendInfoLine: token$, ": recording or TextGrid not found, skipped (", wav$, " | ", tg$, ")"
        else
            sound = Read from file: wav$
            original = Read from file: tg$
            Rename: "original"
            textgrid = Read from file: tg$
            tgname$ = selected$ ("TextGrid")
            selectObject: sound, textgrid
            View & Edit
            editor: "TextGrid " + tgname$
                # Praat 6.4 and later, then earlier versions; whichever exists is used
                nocheck Pitch settings: 50, 500, "Hertz", "raw autocorrelation", "automatic"
                nocheck Pitch settings: 50, 500, "Hertz", "autocorrelation", "automatic"
                if z1 > z0
                    nocheck Zoom: z0, z1
                endif
            endeditor

            beginPause: "Token " + string$ (i) + " / " + string$ (n) + ":  " + token$
                comment: "Check " + string$ (task) + ".  Why listed: " + why$
                rest$ = what$
                while rest$ <> ""
                    p = index (rest$, ". ")
                    if p = 0
                        comment: rest$
                        rest$ = ""
                    else
                        comment: left$ (rest$, p)
                        rest$ = mid$ (rest$, p + 2, length (rest$))
                    endif
                endwhile
                comment: "If the pitch line is not 50-500 Hz: Pitch > Pitch settings..., range 50 to 500."
                optionMenu: "Decision", 1
                    option: "Include"
                    option: "Exclude"
                    option: "TextGrid corrected (save it; the next run re-measures)"
                    option: "F0 only with a lower floor (keep excluded for now)"
                    option: "Not sure: decide later"
                sentence: "Note", ""
            clicked = endPause: "Stop", "Skip", "Save & next", 3

            if clicked = 1
                stop = 1
            elsif clicked = 3 and decision < 5
                note$ = replace$ (note$, ",", ";", 0)
                dec$ = ""
                if decision = 1
                    dec$ = "Include"
                elsif decision = 2
                    dec$ = "Exclude"
                elsif decision = 3
                    note$ = "TextGrid corrected in review. " + note$
                    base$ = right$ (tg$, length (tg$) - max (rindex (tg$, "/"), rindex (tg$, "\")))
                    backup$ = backup_folder$ + "/" + base$
                    if not fileReadable (backup$)
                        selectObject: original
                        Save as text file: backup$
                    endif
                    selectObject: textgrid
                    Save as text file: tg$
                    corrected += 1
                elsif decision = 4
                    note$ = "F0 visible only with a lower pitch floor. " + note$
                endif
                @appendDecision: token$ + ",yes," + dec$ + "," + note$
                decided += 1
            endif
            removeObject: sound, textgrid, original
        endif
    endif
endfor
removeObject: table

appendInfoLine: newline$, "Decisions written: ", decided, "   TextGrids corrected: ", corrected
appendInfoLine: "Decisions file: ", overrides_file$
if corrected > 0
    appendInfoLine: "You corrected TextGrids: run run_all again (same --out folder) to re-measure them."
else
    appendInfoLine: "Now, in Terminal:  python3 -m modules.selection --results <results folder>/intonasphere_results.xlsx"
endif

procedure appendDecision: .line$
    .text$ = readFile$ (overrides_file$)
    if length (.text$) > 0 and right$ (.text$, 1) <> newline$
        appendFile: overrides_file$, newline$
    endif
    appendFileLine: overrides_file$, .line$
endproc
