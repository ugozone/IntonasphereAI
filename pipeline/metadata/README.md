# Speaker metadata

`run_all --speakers` and `check_folder --speakers` read a speaker table (one row per speaker, with a
`Speaker code` column, plus sex, age, region, etc.) to fill the demographic columns of the dataset.

The PFC speaker table used for the LSA 2027 study (`pfc_speaker_table_corrected.xlsx`) is corpus
metadata and is **not** included in this repository (spreadsheets are excluded by `.gitignore`).
Keep your copy in this folder on your own computer. Without a table, everything else is still
computed and the demographic columns stay empty.
