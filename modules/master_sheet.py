"""
IntonaSphere AI — PFC Q1–Q3 master sheet and token-selection rule.

Builds one analysis-ready sheet from the token-level extraction output:
  * merges speaker metadata (site, country, region, age, age group, sex) from the
    'combined speaker table' sheet of the template workbook;
  * adds planned rows for speakers/questions that have no measurements yet;
  * flags quality-control problems (failed extraction, missing alignment, mis-cut
    extraction window, missing final-region measures, filename in transcript);
  * applies the pre-registered token-selection rule, which is anchored on the final
    word group of each question (where the nuclear configuration is realized);
  * merges manual decisions from an overrides CSV, which re-runs never overwrite.

It is called automatically at the end of token_level_praat_extractor.process_token_level_workbook()
and can also be run on its own:

  python -m modules.master_sheet --acoustics PFC_token_level_praat_filled.csv \
      --speakers PFC_template.xlsx --out outputs/PFC_Q1_Q2_Q3_master.xlsx \
      [--overrides outputs/manual_overrides.csv] [--flow outputs/token_flow.csv]

Overrides CSV columns: TOKEN_ID, PITCH_TRACK_CHECKED (yes/no),
MANUAL_DECISION (Include/Exclude; blank keeps the automatic decision), MANUAL_NOTE.
"""
import argparse, re, unicodedata
import numpy as np
import pandas as pd

# ----------------------------------------------------------------- configuration
SPEAKER_SHEET = 'combined speaker table'
QUESTIONS = {
    # id: (question type, official target text, final word group used by the rule)
    'Q1': ('YN_inversion', 'Le Premier Ministre ira-t-il à Beaulieu ?', 'à beaulieu'),
    'Q2': ('Wh_quest_ce_qui', 'Qu’est-ce qui a donc valu à Beaulieu ce grand honneur ?', 'grand honneur'),
    'Q3': ('Wh_comment_infinitive', 'Comment, en plus, éviter les manifestations qui ont eu tendance '
           'à se multiplier lors des visites officielles ?', 'visites officielles'),
}
SITE_FIXES = {'senegal': 'Sénégal', 'RCA Bangui': 'Bangui'}
SPEAKER_ALIASES = {}          # e.g. {'81aac1': '81acc1'} once confirmed
AGE_RULE = 'gt_median'        # Older = age above the sample median ('ge_median' = at or above)
WINDOW_FACTOR = 3.0           # extraction window > 3 x sentence median duration = mis-cut
MIN_SPEECH_RATE = 1.5         # syllables per second; below this = mis-cut window
FILLERS = {'euh', 'heu', 'hum', 'ben', 'bah'}

# ----------------------------------------------------------------- helpers
def norm_words(text):
    """Lower-case, strip accents/punctuation, split hyphens and elisions."""
    if not isinstance(text, str):
        return []
    t = unicodedata.normalize('NFKD', text.lower())
    t = ''.join(c for c in t if not unicodedata.combining(c))
    t = re.sub(r"[’'\-]", ' ', t)
    t = re.sub(r'[^a-z0-9 ]', ' ', t)
    return t.split()

def find_all(words, seq):
    n = len(seq)
    return [i for i in range(len(words) - n + 1) if words[i:i + n] == seq]

def repeated_bigrams(words):
    seen, rep = set(), set()
    for bg in zip(words, words[1:]):
        (rep if bg in seen else seen).add(bg)
    return rep

def assess_transcript(text, qid, speaker_code):
    """Return (technical_flags, disfluency_flags, final_group_ok, note)."""
    tech, dis = [], []
    words = norm_words(text)
    if not words:
        return ['no_transcript_alignment'], [], None, 'No transcript'
    # filename or speaker code pasted into the transcript
    code_pat = re.compile(r'^[0-9a-z]{2}a[a-z]{2,3}\d(tw\d?)?$')
    stray = [w for w in words if code_pat.match(w) and re.search(r'\d', w)]
    if stray:
        tech.append('filename_in_transcript')
        words = [w for w in words if w not in stray]
    final = norm_words(QUESTIONS[qid][2])
    k = len(final)
    occurrences = find_all(words, final)
    complete = words[-k:] == final
    tail = words[-(k + 3):]                       # final word group plus three words before it
    rep_in_tail = any(bg in repeated_bigrams(words) for bg in zip(tail, tail[1:]))
    filler_in_tail = any(w in FILLERS for w in tail)
    final_ok = complete and len(occurrences) == 1 and not rep_in_tail and not filler_in_tail
    if not complete:
        dis.append('sentence_incomplete_or_final_group_missing')
    if len(occurrences) > 1:
        dis.append('final_group_repeated')
    if rep_in_tail or filler_in_tail:
        dis.append('repair_in_final_group')
    # disfluency elsewhere (does not lead to exclusion)
    if final_ok and (any(w in FILLERS for w in words) or repeated_bigrams(words)):
        dis.append('mid_sentence_disfluency')
    return tech, dis, final_ok, ''

# ----------------------------------------------------------------- build
def _read_table(path):
    path = str(path)
    return pd.read_excel(path) if path.lower().endswith(('xlsx', 'xls')) else pd.read_csv(path)

def has_speaker_table(workbook_path):
    try:
        return SPEAKER_SHEET in pd.ExcelFile(workbook_path).sheet_names
    except Exception:
        return False

def build(acoustics, speakers_path, overrides_path=None):
    """acoustics: token-level DataFrame or path to CSV/XLSX; speakers_path: workbook with the speaker sheet."""
    ac = acoustics.copy() if isinstance(acoustics, pd.DataFrame) else _read_table(acoustics)
    ac = ac[ac['TOKEN_ID'].notna() & ac['SPEAKER_ID'].notna()]
    ac = ac.drop_duplicates('TOKEN_ID', keep='last')
    sp = pd.read_excel(speakers_path, sheet_name=SPEAKER_SHEET)
    sp.columns = [c.strip() for c in sp.columns]
    sp['code'] = sp['Speaker code'].astype(str).str.strip()
    sp['Site'] = sp['Site'].astype(str).str.strip().replace(SITE_FIXES)
    sp['Sex'] = sp['Sex'].astype(str).str.strip().str.upper()
    sp['Age'] = pd.to_numeric(sp['Age'], errors='coerce')
    med = sp['Age'].median()
    older = sp['Age'] > med if AGE_RULE == 'gt_median' else sp['Age'] >= med
    sp['AGE_GROUP'] = np.where(older, 'Older', 'Younger')
    status_cols = [c for c in sp.columns if c.lower().startswith(('data status', 'webmaus'))]
    sp['STATUS'] = sp[status_cols].astype(str).apply(lambda r: '; '.join(x for x in r if x != 'nan'), axis=1)
    meta = sp.set_index('code')

    ac['code'] = ac['SPEAKER_ID'].astype(str).str.replace(r'tw\d?$', '', regex=True).replace(SPEAKER_ALIASES)
    # planned rows for speakers/questions without measurements
    have = set(zip(ac['code'], ac['SENTENCE_ID']))
    missing = [{'TOKEN_ID': f'{c}tw_{q}', 'SPEAKER_ID': f'{c}tw', 'SENTENCE_ID': q, 'code': c}
               for c in meta.index for q in QUESTIONS if (c, q) not in have]
    df = pd.concat([ac, pd.DataFrame(missing)], ignore_index=True)

    df['SITE_ID'] = df['code'].map(meta['Site']);  df['COUNTRY'] = df['code'].map(meta['Country'])
    df['CONTINENT'] = df['code'].map(meta['Region']); df['REGION_GROUP'] = df['CONTINENT']
    df['AGE'] = df['code'].map(meta['Age']);  df['AGE_GROUP'] = df['code'].map(meta['AGE_GROUP'])
    df['SEX'] = df['code'].map(meta['Sex']);  df['GENDER_LABEL'] = df['SEX'].map({'F': 'Female', 'M': 'Male'})
    df['QUESTION_TYPE'] = df['SENTENCE_ID'].map({q: v[0] for q, v in QUESTIONS.items()})
    df['TARGET_TEXT'] = df['SENTENCE_ID'].map({q: v[1] for q, v in QUESTIONS.items()})
    df['SPEAKER_DATA_STATUS'] = df['code'].map(meta['STATUS'])

    med_dur = df.groupby('SENTENCE_ID')['TOTAL_DURATION'].transform('median')
    qc, dec, why = [], [], []
    for i, r in df.iterrows():
        flags = []
        if r['code'] not in meta.index:
            flags.append('speaker_not_in_speaker_table')
        if r['SENTENCE_ID'] not in QUESTIONS:
            flags.append('unknown_sentence_id')
            qc.append(';'.join(flags)); dec.append('Pending – metadata')
            why.append('SENTENCE_ID is not Q1, Q2 or Q3'); continue
        status = r.get('PRAAT_STATUS')
        if pd.isna(r.get('F0_MEAN_ST')) and isinstance(status, str) and status not in ('', 'completed'):
            flags.append('extraction_failed')
            qc.append(';'.join(flags)); dec.append('Repair, then reassess')
            why.append('Extraction failed: ' + str(r.get('PRAAT_ERROR') or status)); continue
        if pd.isna(r.get('F0_MEAN_ST')):
            flags.append('no_acoustic_data')
            qc.append(';'.join(flags)); dec.append('Pending – no data')
            why.append('Not yet extracted/measured; rule applied once processed'); continue
        tech, dis, final_ok, _ = assess_transcript(r.get('SENTENCE_TEXT'), r['SENTENCE_ID'], r['code'])
        if r.get('SYLLABLE_COUNT') == 0 and 'no_transcript_alignment' not in tech:
            tech.append('no_transcript_alignment')
        if pd.isna(r.get('CONTOUR_CLASS')) or pd.isna(r.get('FINAL_SLOPE_ST')):
            tech.append('no_final_region_measure')
        dur, rate = r.get('TOTAL_DURATION'), r.get('SPEECH_RATE_SYLL_PER_SEC')
        if (pd.notna(dur) and dur > WINDOW_FACTOR * med_dur[i]) or (pd.notna(rate) and rate < MIN_SPEECH_RATE):
            tech.append('extraction_window_too_long')
        flags += tech + dis
        qc.append(';'.join(flags))
        if final_ok is False and 'no_transcript_alignment' not in tech:
            dec.append('Exclude'); why.append('Final word group affected: ' + ', '.join(d for d in dis if d != 'mid_sentence_disfluency'))
        elif tech:
            dec.append('Repair, then reassess'); why.append('Technical problem: ' + ', '.join(tech))
        elif 'speaker_not_in_speaker_table' in flags:
            dec.append('Pending – metadata'); why.append('Speaker code not in speaker table; confirm or add alias')
        elif 'mid_sentence_disfluency' in dis:
            dec.append('Include'); why.append('Disfluency before the final word group only; nuclear region intact')
        else:
            dec.append('Include'); why.append('Meets all criteria')
    df['QC_FLAGS'] = qc
    df['QC_OK'] = np.where(df['QC_FLAGS'] == '', 'yes', 'no')
    df['AUTO_DECISION'] = dec
    df['AUTO_REASON'] = why

    # manual overrides (never overwritten by re-runs)
    df['PITCH_TRACK_CHECKED'] = 'no'; df['MANUAL_DECISION'] = ''; df['MANUAL_NOTE'] = ''
    if overrides_path:
        ov = pd.read_csv(overrides_path, dtype=str).fillna('').set_index('TOKEN_ID')
        for col in ('PITCH_TRACK_CHECKED', 'MANUAL_DECISION', 'MANUAL_NOTE'):
            if col in ov.columns:
                m = df['TOKEN_ID'].map(ov[col])
                df[col] = np.where(m.notna() & (m != ''), m, df[col])
    df['SELECTION_DECISION'] = np.where(df['MANUAL_DECISION'] != '', df['MANUAL_DECISION'], df['AUTO_DECISION'])
    inc = df['SELECTION_DECISION'].eq('Include')
    n_inc = df[inc].groupby('SPEAKER_ID').size()
    df['COMPLETE_CASE_SET'] = df['SPEAKER_ID'].map(lambda s: 'yes' if n_inc.get(s, 0) == len(QUESTIONS) else 'no')

    df = df.sort_values(['CONTINENT', 'SITE_ID', 'SPEAKER_ID', 'SENTENCE_ID'], na_position='last')
    front = ['TOKEN_ID', 'SPEAKER_ID', 'SITE_ID', 'COUNTRY', 'CONTINENT', 'REGION_GROUP', 'AGE', 'AGE_GROUP',
             'SEX', 'GENDER_LABEL', 'SENTENCE_ID', 'QUESTION_TYPE', 'TARGET_TEXT', 'SENTENCE_TEXT']
    back = ['SPEAKER_DATA_STATUS', 'QC_FLAGS', 'QC_OK', 'AUTO_DECISION', 'AUTO_REASON',
            'PITCH_TRACK_CHECKED', 'MANUAL_DECISION', 'MANUAL_NOTE', 'SELECTION_DECISION', 'COMPLETE_CASE_SET']
    middle = [c for c in df.columns if c not in front + back + ['code']]
    return df[front + middle + back]

def token_flow(df):
    rows = [('Planned tokens (speakers x questions)', len(df[df['SITE_ID'].notna()]))]
    for d in ['Pending – no data', 'Pending – metadata', 'Repair, then reassess', 'Exclude', 'Include']:
        rows.append((d, int((df['SELECTION_DECISION'] == d).sum())))
    inc = df['SELECTION_DECISION'] == 'Include'
    rows += [('Speakers with >= 1 included token', df[inc]['SPEAKER_ID'].nunique()),
             ('Speakers in complete-case set', df[df['COMPLETE_CASE_SET'] == 'yes']['SPEAKER_ID'].nunique()),
             ('Included tokens with pitch track checked', int((inc & (df['PITCH_TRACK_CHECKED'] == 'yes')).sum()))]
    return pd.DataFrame(rows, columns=['Step', 'N'])

def write_xlsx(df, path):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    from openpyxl.utils import get_column_letter
    wb = Workbook(); ws = wb.active; ws.title = 'PFC_tokens'
    ws.append(list(df.columns))
    for row in df.itertuples(index=False):
        ws.append([None if isinstance(v, float) and np.isnan(v) else v for v in row])
    for c in ws[1]:
        c.font = Font(bold=True, color='FFFFFF'); c.fill = PatternFill('solid', start_color='1F3864')
        c.alignment = Alignment(wrap_text=True, vertical='center')
    ws.row_dimensions[1].height = 32
    ci = {n: i + 1 for i, n in enumerate(df.columns)}
    colors = {'Include': 'E2EFDA', 'Exclude': 'F8CBAD', 'Repair, then reassess': 'FFF2CC',
              'Pending – no data': 'D9D9D9', 'Pending – metadata': 'D9D9D9'}
    for r in range(2, ws.max_row + 1):
        d = ws.cell(r, ci['SELECTION_DECISION']).value
        if d in colors:
            ws.cell(r, ci['SELECTION_DECISION']).fill = PatternFill('solid', start_color=colors[d])
        if ws.cell(r, ci['QC_OK']).value == 'no':
            ws.cell(r, ci['QC_FLAGS']).fill = PatternFill('solid', start_color='FCE4D6')
    wide = {'TARGET_TEXT': 40, 'SENTENCE_TEXT': 40, 'QC_FLAGS': 34, 'AUTO_REASON': 50, 'MANUAL_NOTE': 30,
            'SPEAKER_DATA_STATUS': 28, 'COUNTRY': 22, 'SELECTION_DECISION': 22, 'AUTO_DECISION': 22}
    for n, i in ci.items():
        ws.column_dimensions[get_column_letter(i)].width = wide.get(n, 13)
    ws.freeze_panes = 'C2'; ws.auto_filter.ref = ws.dimensions
    wb.save(path)

def build_and_save(acoustics, speakers_path, out_xlsx, overrides_path=None, flow_csv=None):
    """Build the master sheet, write it (and the token-flow table), and return (master, flow)."""
    from pathlib import Path
    out_xlsx = Path(out_xlsx)
    out_xlsx.parent.mkdir(parents=True, exist_ok=True)
    if overrides_path is None:
        default = out_xlsx.with_name('manual_overrides.csv')
        if not default.exists():
            default.write_text('TOKEN_ID,PITCH_TRACK_CHECKED,MANUAL_DECISION,MANUAL_NOTE\n', encoding='utf-8')
        overrides_path = default
    master = build(acoustics, speakers_path, overrides_path)
    write_xlsx(master, str(out_xlsx))
    flow = token_flow(master)
    flow.to_csv(flow_csv or out_xlsx.with_name(out_xlsx.stem + '_token_flow.csv'), index=False)
    return master, flow

if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--acoustics', required=True); ap.add_argument('--speakers', required=True)
    ap.add_argument('--out', required=True); ap.add_argument('--overrides'); ap.add_argument('--flow')
    a = ap.parse_args()
    master, flow = build_and_save(a.acoustics, a.speakers, a.out, a.overrides, a.flow)
    print(flow.to_string(index=False))
