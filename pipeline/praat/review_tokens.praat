# review_tokens.praat  —  IntonaSphere AI
# Opens, one at a time, the tokens listed by  python3 -m modules.review_list  (review_list.tsv):
# the recording with the TextGrid the run used, zoomed to the end of the sentence, with the
# pitch range set to 50-500 Hz so that low and creaky endings are visible.
# For each token, choose a decision in the small window and click "Save & next":
#   Include                      -> used for tune choice and for the F0 measures
#   Tune only                    -> the ending is low or creaky but you can label the nuclear
#                                   configuration (usually L%): used for tune choice only
#   Exclude                      -> not used (the ending cannot be labelled, or the sentence is wrong)
#     (these three are written to manual_overrides.csv with CHECKED = yes)
#   TextGrid corrected           -> the TextGrid you edited is saved in place (a copy of the
#                                   original is kept in review_backups/); the next run_all
#                                   re-measures the token
#   Cut the noise at the end     -> for a file that goes on after the sentence (breath, room noise):
#                                   first drag the end boundary of the last word to where the voice
#                                   stops; the script then cuts the recording AND the TextGrid
#                                   0.05 s after that boundary. Copies of the original recording and
#                                   TextGrid are kept in review_backups/; the next run_all re-measures
#                                   it, and it comes back in the review list only if it still needs a look
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
                    option: "Tune only (ending can be labelled; not measured)"
                    option: "Exclude"
                    option: "TextGrid corrected (save it; the next run re-measures)"
                    option: "Cut the noise after the last word (recording and TextGrid)"
                    option: "Not sure: decide later"
                sentence: "Note", ""
            clicked = endPause: "Stop", "Skip", "Save & next", 3

            if clicked = 1
                stop = 1
            elsif clicked = 3 and decision = 5
                @cutAfterLastWord
                if cut_ok
                    note$ = replace$ (note$, ",", ";", 0)
                    note$ = "Noise after the sentence cut at " + fixed$ (cut_at, 3) + " s in review. " + note$
                    # CHECKED = no: after run_all re-measures it, the token is listed again only if it still needs a look
                    @appendDecision: token$ + ",no,," + note$
                    decided += 1
                    corrected += 1
                endif
            elsif clicked = 3 and decision < 6
                note$ = replace$ (note$, ",", ";", 0)
                dec$ = ""
                if decision = 1
                    dec$ = "Include"
                elsif decision = 2
                    dec$ = "Tune only"
                elsif decision = 3
                    dec$ = "Exclude"
                elsif decision = 4
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
                endif
                @appendDecision: token$ + ",yes," + dec$ + "," + note$
                decided += 1
            endif
            removeObject: sound, textgrid, original
        endif
    endif
endfor
removeObject: table

appendInfoLine: newline$, "Decisions written: ", decided, "   TextGrids corrected or files cut: ", corrected
appendInfoLine: "Decisions file: ", overrides_file$
if corrected > 0
    appendInfoLine: "You corrected TextGrids: run run_all again (same --out folder) to re-measure them."
else
    appendInfoLine: "Now, in Terminal:  python3 -m modules.selection --results <results folder>/intonasphere_results.xlsx"
endif

procedure backupOnce: .object, .path$, .kind$
    .base$ = right$ (.path$, length (.path$) - max (rindex (.path$, "/"), rindex (.path$, "")))
    .backup$ = backup_folder$ + "/" + .base$
    if not fileReadable (.backup$)
        selectObject: .object
        if .kind$ = "wav"
            Save as WAV file: .backup$
        else
            Save as text file: .backup$
        endif
    endif
endproc

procedure cutAfterLastWord
    # the word tier: ORT-MAU (WebMAUS) or a tier called words/ORT/mots, else tier 1
    cut_ok = 0
    selectObject: textgrid
    .ntiers = Get number of tiers
    .tier = 1
    for .k to .ntiers
        .name$ = Get tier name: .k
        .isint = Is interval tier: .k
        if .isint and (.name$ = "ORT-MAU" or .name$ = "ORT" or .name$ = "words" or .name$ = "mots")
            .tier = .k
        endif
    endfor
    .n = Get number of intervals: .tier
    .i = .n
    .lab$ = Get label of interval: .tier, .i
    while .i > 1 and (.lab$ = "" or .lab$ = "<p:>" or .lab$ = "_" or .lab$ = "#")
        .i -= 1
        .lab$ = Get label of interval: .tier, .i
    endwhile
    .wordEnd = Get end time of interval: .tier, .i
    .total = Get end time
    cut_at = .wordEnd + 0.05
    if cut_at > .total - 0.02
        beginPause: "Nothing to cut"
            comment: "The last word already ends at the end of the file (" + fixed$ (.wordEnd, 3) + " s)."
            comment: "First drag the end boundary of the last word to where the voice stops,"
            comment: "then choose this option again. The token is listed again next time."
        .clicked = endPause: "OK", 1
    else
        @backupOnce: sound, wav$, "wav"
        @backupOnce: original, tg$, "TextGrid"
        selectObject: sound
        .cutSound = Extract part: 0, cut_at, "rectangular", 1, "no"
        Save as WAV file: wav$
        selectObject: textgrid
        .cutGrid = Extract part: 0, cut_at, "no"
        Save as text file: tg$
        removeObject: .cutSound, .cutGrid
        appendInfoLine: token$, ": cut at ", fixed$ (cut_at, 3), " s (was ", fixed$ (.total, 3), " s)"
        cut_ok = 1
    endif
endproc

procedure appendDecision: .line$
    .text$ = readFile$ (overrides_file$)
    if length (.text$) > 0 and right$ (.text$, 1) <> newline$
        appendFile: overrides_file$, newline$
    endif
    appendFileLine: overrides_file$, .line$
endproc
