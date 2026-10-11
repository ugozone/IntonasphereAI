"""
IntonaSphere AI - F_ToBI assistant
==================================

Proposes an F_ToBI annotation (Delais-Roussarie et al. 2015) for every utterance
that has a WAV file and a WebMAUS TextGrid, and writes it as Praat tiers that a
trained annotator checks and corrects. Nothing here is a black box: every label
comes from a written rule applied to measured cues, every rule threshold is a
parameter, and the measured evidence is written next to the label (EVIDENCE tier
and CSV) so the annotator can see why the label was proposed.

What it produces, per utterance
-------------------------------
<stem>_ftobi.TextGrid with, in this order:
    tones      point    F_ToBI tones: aL, Hi, L, H*, L*, H+!H*, H-, L-, H%, L%, !H%
    words      interval orthographic words (WebMAUS ORT-MAU)
    breaks     point    break index after every word: 0 1 2 3 4 (+ "p" hesitation, "?" uncertain)
    AP         interval Accentual Phrases
    ip         interval Intermediate Phrases
    IP         interval Intonational Phrases
    syllables  interval syllables in IPA (WebMAUS MAS, converted from SAMPA)
    phones     interval phones in IPA (WebMAUS MAU, converted from SAMPA)
    evidence   point    measured cues at each syllable that could close an AP
    nuc-edge   point    test of Beyssade, Delais-Roussarie & Marandin (2007)
    misc       interval QC warnings (alignment / transcription problems)
<stem>_ftobi.png        F0 contour with the tones, breaks and phrases drawn on it
ftobi_tokens.csv/.xlsx  one row per utterance (nuclear configuration, counts, flags)
ftobi_syllables.csv     one row per syllable (every cue and every decision)

A label ending in "?" is a low-confidence proposal (its cue is within the
uncertainty margin of the threshold): check those first. This follows the
ToBI convention of "?" for uncertain labels.

The rules (all thresholds are arguments of FToBIConfig)
-------------------------------------------------------
1. Accentable words. French has no lexical stress; the obligatory final accent
   falls on the last full (non-schwa) syllable of a content word: nouns, verbs,
   adjectives, adverbs, tonic pronouns, polysyllabic prepositions/auxiliaries.
   Clitics and other function words cannot bear it (Delais-Roussarie et al.
   2015, 3.1.2.1). Each content word therefore closes a CANDIDATE AP; a
   prenominal adjective directly followed by its noun does not.
2. AP boundary (break 2). A candidate becomes an AP boundary when its final
   syllable is acoustically prominent: relative duration, relative F0 height,
   or rise on the vowel above threshold, or a following silent pause. Duration
   and height are relative to the 3 preceding and 3 following syllables, as in
   Avanzi et al. (2011), whose read-speech thresholds are the defaults
   (duration 1.61, height 1.43 ST, rise 2.07 ST).
3. ip boundary (break 3): an AP boundary with stronger lengthening than an AP
   (Delais-Roussarie et al. 2015, 3.1.2.1; Michelas & D'Imperio 2012) or with a
   silent pause. IP boundary (break 4): end of utterance, or a long silent pause
   with a lengthened syllable.
4. Break 0 after a clitic or other function word, 1 between words inside an AP
   (Delais-Roussarie et al. 2015, 3.1.3). "p" marks a pause after a word that
   cannot close an AP (a hesitation, ToBI convention).
5. AP tones, pattern (aL)(Hi)(L)H* (Delais-Roussarie et al. 2015, ex. 3):
   - final accent on the AP's last full syllable: H* when that syllable rises or
     is a local F0 peak, otherwise L* (non-contrastive outside the nucleus);
   - Hi: an early F0 peak on one of the first syllables of the AP (or on a
     wh-word / est-ce que), clearly higher than what follows it;
   - aL: AP-initial low before a later H target;
   - ip edge: H- if the edge is high/rising, L- if it is low/falling.
6. Nuclear configuration (last AP of the IP). In French the nuclear accent and
   the IP boundary tone fall on the same final syllable, so T* is read from the
   start of the final vowel (relative to the penultimate syllable and to the
   speaker's range in that utterance) and T% from the movement across it:
   rise -> H%, fall -> L%, level -> same level as T*. A low penultimate before
   H* gives the leading L of (L)H*. A lengthened high penultimate followed by a
   lower final gives H+!H*. The result is one of Table 3.6's configurations:
   L*L%, L*H%, (L)H*H%, (L)H*L%, H+!H* !H%.
7. Beyssade et al. (2007) predict that interrogatives anchor a phrasal tone at
   the LEFT edge of the nuclear domain, on the wh-word, est-ce que or the
   inverted verb (e.g. H- on [til] in "ira-t-il"): H- with a falling nuclear
   contour, L- with a rising one. The nuc-edge tier and NUC_EDGE_* columns test
   that prediction on every token: a linguistic result, not just a label.

Phonetic transcription: WebMAUS writes French SAMPA. It is converted to IPA
and checked against the expected canonical form of each word in the PFC texte
lu questions; mismatches and non-French SAMPA symbols (a sign that the WebMAUS
language parameter was not French) are written to the misc tier.

Command line
------------
    python -m modules.ftobi_annotator --folder data/wav_and_textgrids --out outputs/ftobi

Then check in Praat (see check_ftobi.praat and README_ftobi.md) and measure
agreement with modules/validate_ftobi.py.
"""
from __future__ import annotations

from . import user_path, CSV_ENCODING

import argparse
import re
import unicodedata
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import gridspec

from .final_domain_visualizer import (
    HAVE_PARSELMOUTH, Interval, Point, Tier, TextGrid, read_textgrid, write_textgrid,
    load_wav, adaptive_pitch, match_textgrid, PFC_QUESTIONS, sentence_id,
)

_PAUSES = {"", "<p:>", "<p>", "sil", "silence", "pause", "#", "<usb>", "<nib>", "_"}


def _is_pause(label: str) -> bool:
    """WebMAUS pause / non-speech labels. Unlike the visualizer's check, a bare 'p' is
    NOT a pause here: at phone level it is the consonant /p/."""
    c = (label or "").strip().lower()
    return c in _PAUSES or c.startswith("<p")

# ---------------------------------------------------------------------------
# Parameters
# ---------------------------------------------------------------------------
@dataclass
class FToBIConfig:
    # prominence thresholds (Avanzi et al. 2011, read speech)
    dur_ratio: float = 1.61        # syllable duration / mean of 3 preceding + 3 following
    height_st: float = 1.43        # syllable F0 - mean of neighbours (ST)
    rise_st: float = 2.07          # rise within the vowel (ST)
    pause_s: float = 0.10          # silent pause after the syllable (s)
    # phrasing
    ip_dur_ratio: float = 2.00     # stronger lengthening -> ip
    IP_pause_s: float = 0.30       # long pause + lengthening -> IP
    # tones
    move_st: float = 1.50          # rise / fall across the final syllable for H% / L%
    level_st: float = 1.00         # step between penultimate and final syllable for T*
    hi_st: float = 1.50            # Hi: early peak above AP-initial low ...
    hi_drop_st: float = 1.00       # ... and above the following syllable
    lead_L_st: float = 1.50        # penultimate low before H* -> (L)H*
    aL_st: float = 1.50            # AP-initial low below the AP's first H
    edge_st: float = 2.00          # Beyssade test: anchor vs nuclear level
    margin: float = 0.15           # within 15 % of a threshold -> "?"


# ---------------------------------------------------------------------------
# Lexicon
# ---------------------------------------------------------------------------
FUNCTION_WORDS = set("""
le la les l un une des de du d à au aux ce cet cette ces se sa son ses mon ma mes ton ta tes
notre nos votre vos leur leurs je j tu il elle on nous vous ils elles me m te t lui y en ne n
qui que qu et ou mais ni car si s a ont est sont ai as avons avez ont par pour sur sous dans
avec sans chez entre vers lors qu'est-ce est-ce
""".split())
PRENOMINAL_ADJ = set("""premier première grand grande petit petite bon bonne beau belle nouveau nouvelle
vieux vieille jeune gros grosse long longue haut haute mauvais même autre seul seule dernier dernière
prochain prochaine""".split())
WH_WORDS = set("""qui que quoi où quand comment pourquoi combien quel quelle quels quelles lequel
laquelle lesquels lesquelles qu'est-ce est-ce""".split())
INVERSION = re.compile(r"-(t-)?(il|elle|on|ils|elles|vous|nous|tu|je)$")

# Expected canonical IPA for the PFC texte lu questions (schwas optional)
PFC_LEXICON = {
    "le": "lə", "premier": "pʁəmje", "ministre": "ministʁ", "ira-t-il": "iʁatil", "à": "a",
    "beaulieu": "boljø", "qu'est-ce": "kɛs", "qui": "ki", "a": "a", "donc": "dɔ̃k", "valu": "valy",
    "ce": "sə", "grand": "ɡʁɑ̃", "honneur": "ɔnœʁ", "comment": "kɔmɑ̃", "en": "ɑ̃", "plus": "plys",
    "éviter": "evite", "les": "le", "manifestations": "manifɛstasjɔ̃", "ont": "ɔ̃", "eu": "y",
    "tendance": "tɑ̃dɑ̃s", "se": "sə", "multiplier": "myltiplije", "lors": "lɔʁ", "des": "de",
    "visites": "vizit", "officielles": "ɔfisjɛl",
    "village": "vilaʒ", "de": "də", "est": "ɛ", "émoi": "emwa",
}

# French SAMPA (WebMAUS 'fra-FR') -> IPA; Praat backslash codes; German SAMPA flagged
SAMPA_FR = {
    "i": "i", "e": "e", "E": "ɛ", "a": "a", "A": "ɑ", "O": "ɔ", "o": "o", "u": "u", "y": "y",
    "2": "ø", "9": "œ", "@": "ə", "e~": "ɛ̃", "a~": "ɑ̃", "o~": "ɔ̃", "9~": "œ̃",
    "j": "j", "w": "w", "H": "ɥ", "p": "p", "b": "b", "t": "t", "d": "d", "k": "k", "g": "ɡ",
    "f": "f", "v": "v", "s": "s", "z": "z", "S": "ʃ", "Z": "ʒ", "m": "m", "n": "n", "J": "ɲ",
    "N": "ŋ", "l": "l", "R": "ʁ", "r": "ʁ", "x": "x",
    "\\o/": "ø", "\\oe": "œ", "\\oe/": "œ", "\\ae": "æ", "\\ep": "ɛ", "\\ct": "ɔ", "\\sw": "ə",
}
SAMPA_NON_FR = {"I": "ɪ", "aU": "aʊ", "aI": "aɪ", "OY": "ɔʏ", "?": "ʔ", "e:": "eː", "i:": "iː",
                "a:": "aː", "o:": "oː", "u:": "uː", "y:": "yː", "2:": "øː", "E:": "ɛː", "OE": "œ",
                "U": "ʊ", "Y": "ʏ", "6": "ɐ", "C": "ç", "Q": "ɒ", "V": "ʌ", "{": "æ", "T": "θ", "D": "ð"}
IPA_VOWELS = set("ieɛaɑɔouyøœəɪʊʏɐæʌɒ")


def norm_word(w: str) -> str:
    w = unicodedata.normalize("NFC", w.strip().lower()).replace("’", "'")
    return re.sub(r"[.,;:!?«»\"()]", "", w)


def sampa_to_ipa(label: str) -> Tuple[str, List[str]]:
    """Convert a space-separated SAMPA string (or one symbol) to IPA.
    Returns (ipa, list of symbols that are not French SAMPA)."""
    out, foreign = [], []
    for sym in label.split():
        if sym in SAMPA_FR:
            out.append(SAMPA_FR[sym])
        elif sym in SAMPA_NON_FR:
            out.append(SAMPA_NON_FR[sym]); foreign.append(sym)
        elif any(ch in IPA_VOWELS or ord(ch) > 127 for ch in sym):
            out.append(sym)                       # already IPA (hand-edited tiers)
        elif _is_pause(sym):
            continue
        else:
            out.append(sym); foreign.append(sym)
    return "".join(out), foreign


def has_vowel(ipa: str) -> bool:
    return any(ch in IPA_VOWELS for ch in unicodedata.normalize("NFD", ipa))


def full_vowel(ipa: str) -> bool:
    s = unicodedata.normalize("NFD", ipa).replace("ə", "")
    return any(ch in IPA_VOWELS for ch in s)


def strip_schwa(s: str) -> str:
    return s.replace("ə", "").replace("ː", "")


_LOOSE = str.maketrans({"ɔ": "o", "ɛ": "e", "œ": "ø", "ɑ": "a", "ʀ": "ʁ", "r": "ʁ", "ɡ": "g"})


def same_word_form(got: str, exp: str) -> bool:
    """Canonical-form check that tolerates regular variation: mid-vowel height
    (o/ɔ, e/ɛ, ø/œ), a/ɑ, schwa realised or not (or as e/ø/œ), and i~ij / y~yɥ glides."""
    g = unicodedata.normalize("NFC", got.replace("ː", "")).translate(_LOOSE)
    e = unicodedata.normalize("NFC", exp).translate(_LOOSE)
    g = g.replace("ij", "i").replace("j", "i")
    e = e.replace("ij", "i").replace("j", "i")
    pat = "".join("[əeø]?" if ch == "ə" else re.escape(ch) for ch in e)
    return re.fullmatch(pat, g.replace("ə", "")) is not None or re.fullmatch(pat, g) is not None


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------
@dataclass
class Syl:
    start: float
    end: float
    ipa: str
    word: int = -1
    v_start: float = np.nan
    v_end: float = np.nan
    # cues
    dur: float = np.nan
    dur_ratio: float = np.nan
    f0_mean: float = np.nan
    f0_start: float = np.nan
    f0_end: float = np.nan
    f0_max: float = np.nan
    f0_min: float = np.nan
    t_max: float = np.nan
    t_min: float = np.nan
    rise: float = 0.0
    fall: float = 0.0
    height: float = np.nan
    pause_after: float = 0.0
    prominence: float = 0.0
    prominent: bool = False
    cue_hits: str = ""


@dataclass
class Word:
    start: float
    end: float
    text: str
    syls: List[int]
    content: bool = False
    candidate: bool = False
    accent_syl: int = -1
    brk: str = ""
    expected_ipa: str = ""
    kan_ipa: str = ""


def tier_exact(tg: TextGrid, names: List[str]) -> Optional[Tier]:
    for n in names:
        for t in tg.tiers:
            if t.name == n and t.kind == "interval":
                return t
    for n in names:
        t = tg.get(n)
        if t is not None and t.kind == "interval":
            return t
    return None


# ---------------------------------------------------------------------------
# Building words and syllables from the WebMAUS TextGrid
# ---------------------------------------------------------------------------
def build_units(tg: TextGrid, stem: str, misc: List[Interval]) -> Tuple[List[Word], List[Syl], List[Interval]]:
    wt = tier_exact(tg, ["ORT-MAU", "words", "word", "ORT", "mots"])
    st_ = tier_exact(tg, ["MAS", "syllabe", "syllable", "sylable", "syllables"])
    pt = tier_exact(tg, ["MAU", "phones", "phone"])
    kt = tier_exact(tg, ["KAN-MAU"])
    if wt is None or st_ is None:
        raise ValueError("TextGrid needs a word tier (ORT-MAU) and a syllable tier (MAS)")
    key = re.sub(r"[^a-z0-9]", "", stem.lower())
    words = [iv for iv in wt.intervals if iv.label.strip() and not _is_pause(iv.label)
             and re.sub(r"[^a-z0-9]", "", iv.label.lower()) != key]
    phones: List[Interval] = []
    if pt is not None:
        for iv in pt.intervals:
            if iv.label.strip() and not _is_pause(iv.label):
                ipa, foreign = sampa_to_ipa(iv.label)
                phones.append(Interval(iv.start, iv.end, ipa))
                if foreign:
                    misc.append(Interval(iv.start, iv.end, f"non-French SAMPA '{iv.label}'"))
    raw = []
    for iv in st_.intervals:
        if not iv.label.strip() or _is_pause(iv.label):
            continue
        ipa, foreign = sampa_to_ipa(iv.label)
        if foreign and pt is None:
            misc.append(Interval(iv.start, iv.end, f"non-French SAMPA in '{iv.label}'"))
        raw.append(Syl(iv.start, iv.end, ipa))

    def overlap(a0, a1, b0, b1):
        return max(0.0, min(a1, b1) - max(a0, b0))
    for s in raw:
        ov = [overlap(s.start, s.end, w.start, w.end) for w in words]
        s.word = int(np.argmax(ov)) if ov and max(ov) > 0 else int(np.argmin([abs((w.start + w.end) / 2 - (s.start + s.end) / 2) for w in words]))
    # merge vowel-less syllables into a neighbour of the same word
    syls: List[Syl] = []
    for s in raw:
        if not has_vowel(s.ipa) and syls and syls[-1].word == s.word:
            syls[-1] = Syl(syls[-1].start, s.end, syls[-1].ipa + "." + s.ipa, s.word)
            continue
        syls.append(s)
    i = 0
    while i < len(syls) - 1:                       # word-initial vowel-less syllable -> next
        if not has_vowel(syls[i].ipa) and syls[i + 1].word == syls[i].word:
            syls[i + 1] = Syl(syls[i].start, syls[i + 1].end, syls[i].ipa + "." + syls[i + 1].ipa, syls[i].word)
            del syls[i]
            continue
        i += 1
    for s in syls:
        if not has_vowel(s.ipa):
            misc.append(Interval(s.start, s.end, f"syllable without vowel '{s.ipa}': check alignment"))
        s.ipa = s.ipa.replace(".", "")
        vow = [p for p in phones if p.start >= s.start - 1e-6 and p.end <= s.end + 1e-6 and has_vowel(p.label)]
        if vow:
            s.v_start, s.v_end = vow[0].start, vow[-1].end
        else:
            s.v_start, s.v_end = s.start, s.end
    W: List[Word] = []
    for k, w in enumerate(words):
        idx = [j for j, s in enumerate(syls) if s.word == k]
        W.append(Word(w.start, w.end, w.label.strip(), idx))
    # canonical transcription check (KAN-MAU against the expected PFC form)
    if kt is not None:
        for w in W:
            kan = [iv for iv in kt.intervals if abs(iv.start - w.start) < 0.005 and abs(iv.end - w.end) < 0.005]
            if kan:
                w.kan_ipa = sampa_to_ipa(kan[0].label)[0]
    for w in W:
        exp = PFC_LEXICON.get(norm_word(w.text))
        if exp:
            w.expected_ipa = exp
            got = w.kan_ipa or "".join(syls[j].ipa for j in w.syls)
            if got and not same_word_form(got, exp) and not (norm_word(w.text) == "plus" and same_word_form(got, "ply")):
                misc.append(Interval(w.start, w.end, f"transcription '{got}' ≠ expected /{exp}/"))
    return W, syls, phones


def classify_words(W: List[Word], syls: List[Syl]) -> None:
    for i, w in enumerate(W):
        n = norm_word(w.text)
        parts = n.split("-")
        w.content = not (n in FUNCTION_WORDS or (n in WH_WORDS and n not in {"comment", "pourquoi", "combien", "quand", "où", "quoi"}))
        full = [j for j in w.syls if full_vowel(syls[j].ipa)]
        w.accent_syl = (full or w.syls or [-1])[-1]
        if not w.syls:
            w.content = False
    for i, w in enumerate(W):
        nxt = W[i + 1] if i + 1 < len(W) else None
        w.candidate = w.content and not (norm_word(w.text) in PRENOMINAL_ADJ and nxt is not None and nxt.content)
    if W:
        W[-1].candidate = True


# ---------------------------------------------------------------------------
# Cues
# ---------------------------------------------------------------------------
def clean_f0(f0: np.ndarray, ref_hz: float, max_jump_st: float = 4.0, min_piece: int = 8,
             min_run: int = 3) -> Tuple[np.ndarray, int]:
    """Remove pitch-tracking errors before any label is computed. F0 cannot move
    more than ~4 ST in 10 ms, so a voiced run is split wherever two consecutive
    frames differ by more than max_jump_st; pieces shorter than min_piece frames
    (80 ms) that are cut off by such a jump are set to unvoiced (typically octave
    errors or fricative noise), and so are voiced runs shorter than min_run frames.
    Returns the cleaned track and the number of frames removed (reported per token)."""
    st_ = 12 * np.log2(f0 / ref_hz)
    out = st_.copy()
    v = ~np.isnan(st_)
    removed, i, n = 0, 0, len(v)
    while i < n:
        if not v[i]:
            i += 1; continue
        j = i
        while j < n and v[j]:
            j += 1
        if j - i < min_run:
            out[i:j] = np.nan; removed += j - i
        else:
            cuts = [i] + [k for k in range(i + 1, j) if abs(st_[k] - st_[k - 1]) > max_jump_st] + [j]
            if len(cuts) > 2:
                pieces = list(zip(cuts[:-1], cuts[1:]))
                longest = max(pieces, key=lambda p: p[1] - p[0])
                for a, b in pieces:
                    if (a, b) != longest and b - a < min_piece:
                        out[a:b] = np.nan; removed += b - a
        i = j
    return ref_hz * 2 ** (out / 12), removed


def measure_syllables(syls: List[Syl], t_f0, f0, ref_hz: float, pauses: List[Tuple[float, float]], cfg: FToBIConfig):
    stv = 12 * np.log2(np.where(np.isnan(f0), np.nan, f0) / ref_hz)
    for s in syls:
        # rhyme duration (vowel onset -> syllable end): final lengthening affects the rhyme,
        # and onset clusters that WebMAUS attaches to a syllable do not inflate it
        s.dur = s.end - (s.v_start if not np.isnan(s.v_start) else s.start)
        for lo, hi in ((s.v_start, s.v_end), (s.start, s.end)):
            m = (t_f0 >= lo) & (t_f0 <= hi) & ~np.isnan(stv)
            if m.sum() >= 2:
                break
        if m.sum() >= 2:
            tt, ff = t_f0[m], stv[m]
            k = min(3, len(ff))
            s.f0_mean, s.f0_start, s.f0_end = float(np.mean(ff)), float(np.median(ff[:k])), float(np.median(ff[-k:]))
            s.f0_max, s.f0_min = float(ff.max()), float(ff.min())
            s.t_max, s.t_min = float(tt[np.argmax(ff)]), float(tt[np.argmin(ff)])
        # movements, peak, valley and the F0 at the end are read over the RHYME (vowel onset ->
        # syllable end): final rises run into the coda, while F0 perturbations caused by onset
        # consonants (micro-prosody) are left out. Falls back to the whole syllable.
        ms = (t_f0 >= s.v_start) & (t_f0 <= s.end) & ~np.isnan(stv)
        if ms.sum() < 2:
            ms = (t_f0 >= s.start) & (t_f0 <= s.end) & ~np.isnan(stv)
        if ms.sum() >= 2:
            tt, ff = t_f0[ms], stv[ms]
            k = min(3, len(ff))
            s.f0_end = float(np.median(ff[-k:]))
            s.f0_max, s.f0_min = float(ff.max()), float(ff.min())
            s.t_max, s.t_min = float(tt[np.argmax(ff)]), float(tt[np.argmin(ff)])
            run_min = np.minimum.accumulate(ff)
            run_max = np.maximum.accumulate(ff)
            s.rise = float(max(0.0, np.max(ff - run_min)))
            s.fall = float(max(0.0, np.max(run_max - ff)))
    n = len(syls)
    for i, s in enumerate(syls):
        nb = [syls[j] for j in range(max(0, i - 3), min(n, i + 4)) if j != i]
        s.dur_ratio = s.dur / np.mean([x.dur for x in nb]) if nb else np.nan
        hv = [x.f0_mean for x in nb if not np.isnan(x.f0_mean)]
        s.height = s.f0_mean - np.mean(hv) if hv and not np.isnan(s.f0_mean) else np.nan
        nxt_start = syls[i + 1].start if i + 1 < n else None
        s.pause_after = 0.0
        for a, b in pauses:
            if abs(a - s.end) < 0.02 and (nxt_start is None or b <= nxt_start + 0.02):
                s.pause_after = b - a
        if nxt_start is not None and nxt_start - s.end > s.pause_after:
            s.pause_after = nxt_start - s.end
        # Avanzi et al. (2011) prominence: 0-10 per cue, 5 at threshold, 10 at twice the threshold
        def score(v, thr):
            return 0.0 if np.isnan(v) or v <= 0 else float(min(10.0, 5.0 * v / thr))
        sd = score(s.dur_ratio - 1.0, cfg.dur_ratio - 1.0)   # 'dur' is the rhyme duration
        sh = score(s.height, cfg.height_st)
        sr = score(s.rise, cfg.rise_st)
        sp = 10.0 if s.pause_after >= cfg.pause_s else 0.0
        s.prominence = (sd + sh + sr + 0.5 * sp) / 3.5
        hits = []
        if s.dur_ratio >= cfg.dur_ratio: hits.append("D")
        if not np.isnan(s.height) and s.height >= cfg.height_st: hits.append("H")
        if s.rise >= cfg.rise_st: hits.append("R")
        if s.pause_after >= cfg.pause_s: hits.append("P")
        s.cue_hits = "".join(hits)
        s.prominent = bool(hits)


def near(v: float, thr: float, cfg: FToBIConfig) -> bool:
    return not np.isnan(v) and abs(v - thr) <= cfg.margin * abs(thr)


# ---------------------------------------------------------------------------
# Phrasing: break indices, AP / ip / IP
# ---------------------------------------------------------------------------
def assign_breaks(W: List[Word], syls: List[Syl], cfg: FToBIConfig) -> None:
    for i, w in enumerate(W):
        last = syls[w.syls[-1]] if w.syls else None
        acc = syls[w.accent_syl] if w.accent_syl >= 0 else last
        pause = last.pause_after if last else 0.0
        if i == len(W) - 1:
            w.brk = "4"; continue
        if not w.candidate:
            base = "0" if not w.content else "1"
            w.brk = base + ("p" if pause >= cfg.pause_s else "")
            continue
        # cues measured on the accentable (last full) syllable; pause after the word
        d, h, r = acc.dur_ratio, acc.height, acc.rise
        hit = (d >= cfg.dur_ratio) or (not np.isnan(h) and h >= cfg.height_st) or (r >= cfg.rise_st) or pause >= cfg.pause_s
        unsure = near(d, cfg.dur_ratio, cfg) or near(h, cfg.height_st, cfg) or near(r, cfg.rise_st, cfg)
        if not hit:
            w.brk = "1?" if unsure else "1"
            continue
        if pause >= cfg.IP_pause_s and d >= cfg.dur_ratio:
            w.brk = "4?"
        elif pause >= cfg.pause_s or d >= cfg.ip_dur_ratio:
            # ip = stronger lengthening than an AP, or a pause; a pause alone may be a reading
            # hesitation, and lengthening near the threshold is uncertain -> "?"
            only_pause = d < cfg.ip_dur_ratio
            w.brk = "3" + ("?" if only_pause or near(d, cfg.ip_dur_ratio, cfg) else "")
        else:
            strong = [x for x, t in ((d, cfg.dur_ratio), (h, cfg.height_st), (r, cfg.rise_st))
                      if not np.isnan(x) and x >= t and not near(x, t, cfg)]
            w.brk = "2" if strong else "2?"


def bi(w: Word) -> int:
    return int(w.brk[0])


def phrases(W: List[Word], level: int) -> List[Tuple[int, int]]:
    out, s = [], 0
    for i, w in enumerate(W):
        if bi(w) >= level or i == len(W) - 1:
            out.append((s, i)); s = i + 1
    return out


# ---------------------------------------------------------------------------
# Tones
# ---------------------------------------------------------------------------
def utt_range(syls: List[Syl]) -> Tuple[float, float]:
    v = np.array([x for s in syls for x in (s.f0_min, s.f0_max) if not np.isnan(x)])
    return (float(np.percentile(v, 10)), float(np.percentile(v, 90))) if v.size else (0.0, 1.0)


def pos_in_range(v, rng):
    lo, hi = rng
    return (v - lo) / max(hi - lo, 1e-6)


def assign_tones(W: List[Word], syls: List[Syl], cfg: FToBIConfig) -> Tuple[List[Point], Dict]:
    tones: List[Point] = []
    info: Dict = {}
    rng = utt_range(syls)
    aps = phrases(W, 2)
    for a, (i0, i1) in enumerate(aps):
        ap_syls = [j for w in W[i0:i1 + 1] for j in w.syls]
        if not ap_syls:
            continue
        last_w = W[i1]
        acc_i = last_w.accent_syl if last_w.accent_syl >= 0 else ap_syls[-1]
        acc = syls[acc_i]
        is_nuclear = bi(last_w) == 4
        first_H_val, first_H_t = np.nan, np.nan

        # Hi: early peak on the first syllables of the AP's first content word or on a wh-word
        pre = [j for j in ap_syls if j < acc_i]
        early: List[int] = []
        for w in W[i0:i1 + 1]:
            n = norm_word(w.text)
            if n in WH_WORDS or n in {"qu'est-ce", "est-ce"}:
                early += [j for j in w.syls if j < acc_i]
            if w.content:
                early += [j for j in w.syls[:2] if j < acc_i]
                break
        early = sorted(set(early))
        if len(pre) >= 2 and early:
            c = max(early, key=lambda j: -np.inf if np.isnan(syls[j].f0_max) else syls[j].f0_max)
            cs = syls[c]
            start_min = np.nanmin([syls[j].f0_min for j in pre[:2]]) if pre else np.nan
            after = [syls[j] for j in pre if j > c] + [acc]
            after_val = np.nanmin([s.f0_mean for s in after]) if after else np.nan
            if not np.isnan(cs.f0_max) and not np.isnan(after_val) \
                    and cs.f0_max - start_min >= cfg.hi_st and cs.f0_max - after_val >= cfg.hi_drop_st:
                lab = "Hi" + ("?" if near(cs.f0_max - after_val, cfg.hi_drop_st, cfg) else "")
                tones.append(Point(cs.t_max, lab))
                first_H_val, first_H_t = cs.f0_max, cs.t_max

        if not is_nuclear:
            edge = bi(last_w) == 3
            if np.isnan(acc.f0_mean):
                tones.append(Point((acc.start + acc.end) / 2, "X*?"))
                continue
            high = acc.rise >= cfg.level_st or (not np.isnan(acc.height) and acc.height >= 0.5)
            t_lab = "H*" if high else "L*"
            if near(acc.rise, cfg.level_st, cfg) or (not np.isnan(acc.height) and abs(acc.height - 0.5) < 0.3):
                t_lab += "?"
            tones.append(Point(acc.t_max if high else acc.t_min, t_lab))
            if np.isnan(first_H_val) and high:
                first_H_val, first_H_t = acc.f0_max, acc.t_max
            if edge:
                end_high = acc.f0_end - acc.f0_start >= -0.5 and pos_in_range(acc.f0_end, rng) >= 0.4
                tones.append(Point(acc.end - 0.005, "H-" if end_high else "L-"))
        else:
            # nuclear configuration on the final syllable
            prev = [syls[j] for j in range(acc_i - 1, -1, -1) if not np.isnan(syls[j].f0_mean)]
            pen = prev[0] if prev else None
            if np.isnan(acc.f0_start):
                info.update(NUCLEAR="X*?", T_STAR="X*?", T_PCT="X%?")
                tones.append(Point((acc.start + acc.end) / 2, "X*?"))
                continue
            on, off = acc.f0_start, acc.f0_end
            change = off - on
            step = on - pen.f0_mean if pen else 0.0
            p_on = pos_in_range(on, rng)
            if step >= cfg.level_st or (p_on >= 0.6 and step > -cfg.level_st):
                T = "H*"
            elif step <= -cfg.level_st or p_on <= 0.4:
                T = "L*"
            else:
                T = ("H*" if step >= 0 else "L*") + "?"
            if change >= cfg.move_st:
                B = "H%"
            elif change <= -cfg.move_st:
                B = "L%"
            else:
                B = ("H%" if T.startswith("H") else "L%") + "?"
            if near(abs(change), cfg.move_st, cfg) and "?" not in B:
                B += "?"
            lead = ""
            pen_in_ap = pen is not None and syls.index(pen) in ap_syls
            if T.startswith("H") and pen_in_ap and on - pen.f0_min >= cfg.lead_L_st:
                lead = "L"
                tones.append(Point(pen.t_min, "L"))
            # H+!H*: lengthened, high penultimate stepping down to the final
            if pen is not None and pen.dur_ratio >= cfg.dur_ratio and pen.f0_mean - on >= cfg.level_st \
                    and pos_in_range(pen.f0_mean, rng) >= 0.6 and abs(change) < cfg.move_st:
                T, B, lead = "H+!H*?", "!H%?", ""
                tones = [p for p in tones if not (p.label == "L" and abs(p.time - (pen.t_min if pen else 0)) < 1e-6)]
            t_star_time = acc.v_start + 0.25 * (acc.v_end - acc.v_start)
            tones.append(Point(t_star_time, T))
            tones.append(Point(acc.end - 0.005, B))
            info.update(NUCLEAR=f"{lead}{T.rstrip('?')} {B.rstrip('?')}".strip(), T_STAR=T, T_PCT=B,
                        LEADING_L=bool(lead), NUC_ONSET_ST=on, NUC_OFFSET_ST=off, NUC_CHANGE_ST=change,
                        NUC_STEP_FROM_PENULT_ST=step, NUC_ONSET_POS_IN_RANGE=p_on,
                        NUCLEAR_UNCERTAIN="?" in T or "?" in B)
            if np.isnan(first_H_val) and T.startswith("H"):
                first_H_val = on

        # aL: AP-initial low before the AP's first H target
        if len(ap_syls) >= 3 and not np.isnan(first_H_val):
            s0 = syls[ap_syls[0]]
            if not np.isnan(s0.f0_min) and first_H_val - s0.f0_min >= cfg.aL_st and s0.t_min < (first_H_t if not np.isnan(first_H_t) else acc.start):
                tones.append(Point(s0.t_min, "aL"))
    tones.sort(key=lambda p: p.time)
    # keep points at least 1 ms apart (Praat refuses duplicates)
    out: List[Point] = []
    for p in tones:
        if out and p.time - out[-1].time < 0.001:
            p = Point(out[-1].time + 0.001, p.label)
        out.append(p)
    return out, info


# ---------------------------------------------------------------------------
# Beyssade, Delais-Roussarie & Marandin (2007): left-edge phrasal tone
# ---------------------------------------------------------------------------
def nuclear_edge_test(W: List[Word], syls: List[Syl], info: Dict, cfg: FToBIConfig) -> Tuple[List[Point], Dict]:
    anchor = None
    for w in W:
        n = norm_word(w.text)
        if INVERSION.search(n) or n in WH_WORDS or n in {"qu'est-ce", "est-ce"}:
            anchor = w
            break
    if anchor is None or not anchor.syls or "T_STAR" not in info or info.get("T_STAR", "").startswith("X"):
        return [], {"NUC_EDGE_ANCHOR": anchor.text if anchor else "", "NUC_EDGE_TEST": "not applicable"}
    k = W.index(anchor)
    if INVERSION.search(norm_word(anchor.text)):
        cand = [anchor.syls[-1]]                      # e.g. [til] in ira-t-il (their ex. 21)
    else:
        cand = list(anchor.syls)
        if k + 1 < len(W) and norm_word(W[k + 1].text) in {"qui", "que", "qu"}:
            cand += W[k + 1].syls                     # wh-expression "qu'est-ce qui"
    voiced = [j for j in cand if not np.isnan(syls[j].f0_max)]
    a = syls[max(voiced, key=lambda j: syls[j].f0_max)] if voiced else syls[cand[-1]]
    if np.isnan(a.f0_max):
        return [], {"NUC_EDGE_ANCHOR": anchor.text, "NUC_EDGE_TEST": "anchor unvoiced"}
    nuc_level = info["NUC_ONSET_ST"]
    diff = a.f0_max - nuc_level
    # Beyssade et al. (2007), ex. (4): falling = H- L* (T%), non-falling = L- H*/HL*/H+L* (T%)
    falling = info["T_STAR"].startswith("L")
    rising = info["T_STAR"].startswith("H")
    if diff >= cfg.edge_st:
        lab = "H-"
    elif diff <= -cfg.edge_st:
        lab = "L-"
    else:
        lab = "0"
    pred = "H-" if falling else ("L-" if rising else "?")
    met = (lab == pred) if pred != "?" else None
    t = a.t_max if lab != "L-" else a.t_min
    res = {"NUC_EDGE_ANCHOR": anchor.text, "NUC_EDGE_ANCHOR_SYL": a.ipa, "NUC_EDGE_TONE": lab,
           "NUC_EDGE_ANCHOR_MINUS_NUCLEUS_ST": diff, "NUC_EDGE_PREDICTED": pred,
           "NUC_EDGE_TEST": "met" if met else ("not met" if met is False else "no prediction")}
    return [Point(t, f"{lab} (pred {pred}: {res['NUC_EDGE_TEST']})")], res


# ---------------------------------------------------------------------------
# Figure
# ---------------------------------------------------------------------------
H_COL, L_COL, GREY = "#C2511F", "#1F5FAF", "#6B6A63"


def draw(stem, title, t_f0, f0_st, syls, W, tones, aps, ips, IPs, misc, png: Path, note: str):
    fig = plt.figure(figsize=(16, 8.6), dpi=110)
    gs = gridspec.GridSpec(7, 1, height_ratios=[5.2, 0.7, 0.7, 0.7, 0.7, 0.7, 0.7], hspace=0.06)
    ax = fig.add_subplot(gs[0])
    xmax = max(W[-1].end if W else 0, syls[-1].end if syls else 0) + 0.05
    for k, s in enumerate(syls):
        ax.axvspan(s.start, s.end, color="#EEEBE3" if k % 2 else "#F7F5F0", lw=0)
    ax.plot(t_f0, f0_st, ".", ms=3.2, color="#2D3748")
    v = f0_st[~np.isnan(f0_st)]
    lo, hi = (np.percentile(v, 1) - 2, np.percentile(v, 99) + 5) if v.size else (-10, 10)
    ax.set_ylim(lo, hi)
    last_t, lvl = -1.0, 0
    for p in tones:
        lvl = (lvl + 1) % 3 if p.time - last_t < 0.12 else 0
        last_t = p.time
        col = H_COL if p.label.lstrip("(!aL").startswith("H") or p.label.startswith("Hi") or "H" in p.label[:2] else L_COL
        if p.label in ("L", "aL") or p.label.startswith("L"):
            col = L_COL
        unsure = "?" in p.label
        ax.axvline(p.time, color=col, lw=0.8, alpha=0.5, ls=":" if unsure else "-")
        ax.text(p.time, hi - 0.6 - lvl * 0.09 * (hi - lo), p.label, color=col, ha="center", va="top", fontsize=11,
                fontweight="bold", style="italic" if unsure else "normal",
                bbox=dict(boxstyle="round,pad=0.15", fc="white", ec=col if unsure else "none", lw=0.6))
    ax.set_xlim(0, xmax)
    ax.set_ylabel("F0 (ST re speaker median)")
    ax.set_xticks([])
    ax.text(0, 1.10, title, transform=ax.transAxes, fontsize=13, fontweight="bold", color="#14213D", va="bottom")
    ax.text(0, 1.03, note, transform=ax.transAxes, fontsize=8.5, color=GREY, va="bottom")
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)

    def row(i, name, items, kind="interval", bold=False):
        a = fig.add_subplot(gs[i], sharex=ax)
        a.set_yticks([]); a.set_ylim(0, 1)
        a.set_ylabel(name, rotation=0, ha="right", va="center", fontsize=9, color=GREY)
        for sp in ("top", "right", "left"):
            a.spines[sp].set_visible(False)
        if kind == "interval":
            for s, e, lab in items:
                a.axvline(s, color="#B8B3A6", lw=0.8); a.axvline(e, color="#B8B3A6", lw=0.8)
                a.text((s + e) / 2, 0.5, lab, ha="center", va="center", fontsize=9,
                       fontweight="bold" if bold else "normal", clip_on=True)
        else:
            for t, lab in items:
                a.axvline(t, color="#B8B3A6", lw=0.8)
                a.text(t, 0.5, lab, ha="center", va="center", fontsize=10, fontweight="bold",
                       bbox=dict(boxstyle="round,pad=0.1", fc="white", ec="none"))
        if i < 6:
            plt.setp(a.get_xticklabels(), visible=False)
        return a
    row(1, "words", [(w.start, w.end, w.text) for w in W])
    row(2, "breaks", [(w.end, w.brk) for w in W], kind="point")
    row(3, "syllables", [(s.start, s.end, s.ipa) for s in syls])
    row(4, "AP", [(W[a].start, W[b].end, f"AP{k + 1}") for k, (a, b) in enumerate(aps)], bold=True)
    row(5, "ip", [(W[a].start, W[b].end, f"ip{k + 1}") for k, (a, b) in enumerate(ips)], bold=True)
    last = row(6, "IP", [(W[a].start, W[b].end, f"IP{k + 1}") for k, (a, b) in enumerate(IPs)], bold=True)
    last.set_xlabel("Time (s)")
    if misc:
        fig.text(0.01, 0.005, "QC: " + "; ".join(sorted({m.label for m in misc}))[:220], fontsize=8, color="#A33")
    fig.savefig(png, bbox_inches="tight")
    plt.close(fig)


# ---------------------------------------------------------------------------
# One utterance
# ---------------------------------------------------------------------------
def annotate(wav: Path, textgrid: Path, out_dir: Path, cfg: FToBIConfig,
             fixed_range: Optional[Tuple[float, float]] = None, pitch=None) -> Tuple[Dict, pd.DataFrame]:
    stem = wav.stem
    m = re.match(r"^(.+?)tw([1-4])$", stem, flags=re.I)
    qnum = m.group(2) if m else ""
    row: Dict = {"TOKEN_ID": f"{m.group(1)}tw_{sentence_id(qnum)}" if m else stem, "SPEAKER_ID": m.group(1) if m else stem,
                 "SENTENCE_ID": sentence_id(qnum), "AUDIO_FILE": wav.name, "TEXTGRID_IN": textgrid.name,
                 "PITCH_ENGINE": "Praat (Parselmouth)" if HAVE_PARSELMOUTH else "built-in autocorrelation (Praat-style)"}
    x, sr = load_wav(wav)
    dur = len(x) / sr
    t_f0, f0, rng = pitch if pitch is not None else adaptive_pitch(x, sr, fixed=fixed_range)
    f0 = f0.copy()
    voiced = f0[~np.isnan(f0)]
    ref = float(np.median(voiced)) if voiced.size else 100.0
    f0, n_removed = clean_f0(f0, ref)
    row.update(PITCH_FLOOR_HZ=rng[0], PITCH_CEILING_HZ=rng[1], F0_REF_HZ=ref, F0_FRAMES_REMOVED=n_removed)
    tg = read_textgrid(textgrid)
    misc: List[Interval] = []
    W, syls, phones = build_units(tg, stem, misc)
    if not W or not syls:
        raise ValueError("no words or syllables found")
    classify_words(W, syls)
    # silent pauses from MAS / MAU (<p:>) and from empty word intervals
    pauses = []
    for name in ("MAS", "MAU", "ORT-MAU"):
        t = tg.get(name)
        if t is not None and t.kind == "interval":
            pauses += [(iv.start, iv.end) for iv in t.intervals if _is_pause(iv.label) and iv.end - iv.start > 0.02]
    measure_syllables(syls, t_f0, f0, ref, pauses, cfg)
    assign_breaks(W, syls, cfg)
    aps, ips, IPs = phrases(W, 2), phrases(W, 3), phrases(W, 4)
    tones, info = assign_tones(W, syls, cfg)
    edge_pts, edge = nuclear_edge_test(W, syls, info, cfg)
    row.update(info); row.update(edge)

    # evidence points (accentable syllables of content words)
    ev = []
    for w in W:
        if w.content and w.accent_syl >= 0:
            s = syls[w.accent_syl]
            ev.append(Point((s.start + s.end) / 2,
                            f"D{s.dur_ratio:.2f} H{s.height:+.1f} R{s.rise:.1f} P{s.pause_after * 1000:.0f}ms [{s.cue_hits or '-'}]"))
    xmin, xmax = tg.xmin, max(tg.xmax, dur)
    out_tg = TextGrid(xmin, xmax, [
        Tier("tones", "point", points=tones),
        Tier("words", "interval", snap([Interval(w.start, w.end, w.text) for w in W])),
        Tier("breaks", "point", points=[Point(w.end - 0.001, w.brk) for w in W]),
        Tier("AP", "interval", snap([Interval(W[a].start, W[b].end, f"AP{k + 1}") for k, (a, b) in enumerate(aps)])),
        Tier("ip", "interval", snap([Interval(W[a].start, W[b].end, f"ip{k + 1}") for k, (a, b) in enumerate(ips)])),
        Tier("IP", "interval", snap([Interval(W[a].start, W[b].end, f"IP{k + 1}") for k, (a, b) in enumerate(IPs)])),
        Tier("syllables", "interval", snap([Interval(s.start, s.end, s.ipa) for s in syls])),
        Tier("phones", "interval", snap(phones)),
        Tier("evidence", "point", points=ev),
        Tier("nuc-edge", "point", points=edge_pts),
        Tier("misc", "interval", _no_overlap(misc)),
    ])
    out_dir.mkdir(parents=True, exist_ok=True)
    tg_path = out_dir / f"{stem}_ftobi.TextGrid"
    write_textgrid(out_tg, tg_path)
    f0_st = 12 * np.log2(f0 / ref)
    note = (f"Pitch: {row['PITCH_ENGINE']}, range {rng[0]:.0f}–{rng[1]:.0f} Hz · alignment: WebMAUS · "
            f"labels are PROPOSALS to verify in Praat; italic + '?' = low confidence")
    title = f"{row['TOKEN_ID']}  ·  {PFC_QUESTIONS.get(qnum, ' '.join(w.text for w in W))}  ·  nuclear: {info.get('NUCLEAR', '?')}"
    png = out_dir / f"{stem}_ftobi.png"
    draw(stem, title, t_f0, f0_st, syls, W, tones, aps, ips, IPs, misc, png, note)

    row.update(N_WORDS=len(W), N_SYLLABLES=len(syls), N_AP=len(aps), N_ip=len(ips), N_IP=len(IPs),
               N_Hi=sum(p.label.startswith("Hi") for p in tones),
               BREAKS=" ".join(f"{w.text}/{w.brk}" for w in W),
               AP_PHRASING=" ".join("(" + " ".join(w.text for w in W[a:b + 1]) + ")" for a, b in aps),
               TONES=" ".join(p.label for p in tones),
               N_UNCERTAIN=sum("?" in p.label for p in tones) + sum("?" in w.brk for w in W),
               QC_WARNINGS="; ".join(sorted({mm.label for mm in misc})),
               FTOBI_TEXTGRID=tg_path.name, FIGURE_FILE=png.name, STATUS="completed")
    srows = []
    for j, s in enumerate(syls):
        w = W[s.word] if 0 <= s.word < len(W) else None
        srows.append({"TOKEN_ID": row["TOKEN_ID"], "SYL_INDEX": j + 1, "SYLLABLE_IPA": s.ipa,
                      "WORD": w.text if w else "", "CONTENT_WORD": w.content if w else None,
                      "ACCENTABLE": bool(w and w.accent_syl == j), "CANDIDATE_AP_END": bool(w and w.candidate and w.accent_syl == j),
                      "BREAK_AFTER_WORD": w.brk if w and w.syls and w.syls[-1] == j else "",
                      **{k.upper(): v for k, v in asdict(s).items() if k not in ("ipa", "word")}})
    return row, pd.DataFrame(srows)


def snap(ivs: List[Interval], tol: float = 0.002) -> List[Interval]:
    """Close sub-millisecond gaps between WebMAUS intervals (sample rounding), so Praat
    does not show empty slivers between adjacent words or syllables."""
    out: List[Interval] = []
    for iv in sorted(ivs, key=lambda i: i.start):
        if out and 0 < iv.start - out[-1].end < tol:
            mid = (out[-1].end + iv.start) / 2
            out[-1] = Interval(out[-1].start, mid, out[-1].label)
            iv = Interval(mid, iv.end, iv.label)
        out.append(iv)
    return out


def _no_overlap(ivs: List[Interval]) -> List[Interval]:
    out: List[Interval] = []
    for iv in sorted(ivs, key=lambda i: (i.start, i.end)):
        if out and iv.start < out[-1].end:
            if iv.label not in out[-1].label:
                out[-1] = Interval(out[-1].start, max(out[-1].end, iv.end), out[-1].label + " | " + iv.label)
            continue
        out.append(iv)
    return out


# ---------------------------------------------------------------------------
# Batch
# ---------------------------------------------------------------------------
def write_tables(rows: List[Dict], syl_frames: List[pd.DataFrame], cfg: FToBIConfig, out: Path) -> pd.DataFrame:
    """Write ftobi_tokens.csv, ftobi_syllables.csv, ftobi_praat_ranges.csv and ftobi_annotations.xlsx."""
    df = pd.DataFrame(rows)
    first = ["TOKEN_ID", "SPEAKER_ID", "SENTENCE_ID", "STATUS", "NUCLEAR", "T_STAR", "T_PCT", "LEADING_L",
             "NUCLEAR_UNCERTAIN", "AP_PHRASING", "BREAKS", "TONES", "N_AP", "N_ip", "N_IP", "N_Hi",
             "N_UNCERTAIN", "NUC_EDGE_ANCHOR", "NUC_EDGE_TONE", "NUC_EDGE_PREDICTED", "NUC_EDGE_TEST",
             "NUC_EDGE_ANCHOR_MINUS_NUCLEUS_ST", "NUC_ONSET_ST", "NUC_OFFSET_ST", "NUC_CHANGE_ST",
             "NUC_STEP_FROM_PENULT_ST", "NUC_ONSET_POS_IN_RANGE", "QC_WARNINGS", "TEXT_SOURCE",
             "ALIGNMENT_SOURCE", "ALIGNMENT_NOTE"]
    df = df[[c for c in first if c in df.columns] + [c for c in df.columns if c not in first]]
    sdf = pd.concat(syl_frames, ignore_index=True) if syl_frames else pd.DataFrame()
    out.mkdir(parents=True, exist_ok=True)
    df.to_csv(out / "ftobi_tokens.csv", index=False, encoding=CSV_ENCODING)
    sdf.to_csv(out / "ftobi_syllables.csv", index=False, encoding=CSV_ENCODING)
    # small, comma-free table that praat/check_ftobi.praat reads (pitch range + proposal per file)
    if "NUCLEAR" in df.columns:
        df.loc[df.STATUS == "completed", ["AUDIO_FILE", "PITCH_FLOOR_HZ", "PITCH_CEILING_HZ", "NUCLEAR"]] \
            .to_csv(out / "ftobi_praat_ranges.csv", index=False)
    params = pd.DataFrame([{"PARAMETER": k, "VALUE": v} for k, v in asdict(cfg).items()])
    with pd.ExcelWriter(out / "ftobi_annotations.xlsx", engine="openpyxl") as xw:
        df.to_excel(xw, sheet_name="TOKENS", index=False)
        sdf.to_excel(xw, sheet_name="SYLLABLES", index=False)
        params.to_excel(xw, sheet_name="PARAMETERS", index=False)
    return df


def run_folder(folder, out, cfg: Optional[FToBIConfig] = None, fixed_range=None, align: str = "any",
               align_dir=None, language: str = "fra-FR", asr_model: str = "small") -> pd.DataFrame:
    """align = none: original behaviour (WAV + TextGrid required; others skipped)
               pfc : WAVs without a TextGrid are aligned with WebMAUS when there is an x.txt
                     or a PFC file name (the question text is known)
               any : as pfc, plus speech recognition for any other recording"""
    from .auto_align import ensure_alignments
    cfg = cfg or FToBIConfig()
    folder, out = Path(folder), Path(out)
    align_dir = Path(align_dir) if align_dir else out / "aligned"
    print(f"Alignment mode: {align}  (existing TextGrids are always used unchanged)")
    aligned = ensure_alignments(folder, align_dir, align, language, asr_model)
    rows, syl_frames = [], []
    for i, a in enumerate(aligned, 1):
        w, tg = a.wav, a.textgrid
        prov = {"TEXT_SOURCE": a.text_source or ("in TextGrid" if a.alignment_source == "user_textgrid" else ""),
                "ALIGNMENT_SOURCE": a.alignment_source, "ALIGNMENT_NOTE": a.message}
        if tg is None:
            print(f"[{i}/{len(aligned)}] {w.name}: {a.status} - {a.message}")
            rows.append({"AUDIO_FILE": w.name, "STATUS": a.status, "ERROR": a.message, **prov})
            continue
        print(f"[{i}/{len(aligned)}] {w.name}  <- {tg.name}  ({a.alignment_source})")
        try:
            r, s = annotate(w, tg, out, cfg, fixed_range)
            r.update(prov)
            rows.append(r); syl_frames.append(s)
        except Exception as e:
            rows.append({"AUDIO_FILE": w.name, "TEXTGRID_IN": tg.name, "STATUS": "failed", "ERROR": str(e), **prov})
    df = write_tables(rows, syl_frames, cfg, out)
    print(f"\nDone: {len(df)} files -> {out}")
    return df


def main():
    ap = argparse.ArgumentParser(description="IntonaSphere AI F_ToBI assistant")
    ap.add_argument("--folder", required=True,
                    help="Folder with .wav files and, optionally, their WebMAUS .TextGrid or .txt files")
    ap.add_argument("--out", default="outputs/ftobi")
    ap.add_argument("--align", choices=["none", "pfc", "any"], default="any",
                    help="none: WAV + TextGrid required (original behaviour); pfc: align PFC files and "
                         "files with a .txt via WebMAUS; any: also use speech recognition for other files")
    ap.add_argument("--align-dir", default=None, help="where new TextGrids go (default: <out>/aligned)")
    ap.add_argument("--language", default="fra-FR", help="WebMAUS language (default French, fra-FR)")
    ap.add_argument("--asr-model", default="small", help="faster-whisper model for --align any")
    ap.add_argument("--pitch-range", nargs=2, type=float, metavar=("FLOOR", "CEILING"))
    for k, v in asdict(FToBIConfig()).items():
        ap.add_argument(f"--{k.replace('_', '-')}", type=float, default=v)
    a = ap.parse_args()
    cfg = FToBIConfig(**{k: getattr(a, k) for k in asdict(FToBIConfig())})
    run_folder(user_path(a.folder), user_path(a.out), cfg, tuple(a.pitch_range) if a.pitch_range else None,
               align=a.align, align_dir=user_path(a.align_dir), language=a.language, asr_model=a.asr_model)


if __name__ == "__main__":
    main()
