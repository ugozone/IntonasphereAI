"""
IntonaSphere AI - cut a long recording (audio or video) into one clip per phrase
================================================================================

Turns a film, interview or reading into a folder the analysis pipeline can use
directly: one WAV per phrase + a .txt with the same name holding its words.

    python -m modules.segment_media --media film.mp4 --srt film.srt --out ~/Desktop/film_clips
    python -m modules.run_all --folder ~/Desktop/film_clips --out ~/Desktop/film_results --measure both

Where the phrase times come from (pick ONE; checked in this order):

    --segments x.csv     your own list: columns start, end, text (+ optional id, label)
    --srt x.srt          subtitles, e.g. the .srt IntonaSphere exports
    --textgrid x.TextGrid  a Praat TextGrid (e.g. a PFC transcription): every labelled interval
                         of the chosen tier (--tier) becomes a clip
    --transcript x.docx  an IntonaSphere transcript with lines like "[12.34s - 15.67s] text"
                         (.docx or .txt)
    --text x.txt         plain text only (no times): faster-whisper finds every word's time,
                         then each of YOUR sentences is matched to those words
    (none of these)      faster-whisper transcribes the recording and the clips follow its
                         sentences (check the .txt files: speech recognition makes mistakes)

What it writes in --out:

    001_ah-bon.wav, 001_ah-bon.txt, ...   one clip + its text per phrase (mono WAV)
    segments.csv                          id, times in the ORIGINAL recording, text, clip,
                                          source of the times, QC notes
    <media>.TextGrid                      one tier "phrases" over the whole recording:
                                          open it in Praat with the original audio
    <media>.wav                           the audio track of a video (only for video input)

Safeguards (from problems met on film audio):
  - padding never reaches into the next or previous phrase: it stops halfway through
    the gap, so a clip cannot start with the end of someone else's line;
  - the same text repeated 3+ times in a row, or a long segment with almost no words, is
    a speech-recognition loop over music: flagged and left out (--keep-suspect keeps it);
  - a segment holding several sentences is split at . ? ! when word times are known
    (--text or speech recognition); from subtitles it is kept whole and flagged.

Needs ffmpeg (already in packages.txt) to read video, MP3 and M4A. Speech recognition
(--text, or no times at all) needs faster-whisper: pip install faster-whisper.
"""
from __future__ import annotations

from . import user_path, CSV_ENCODING

import argparse
import difflib
import re
import shutil
import subprocess
import tempfile
import unicodedata
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np
import pandas as pd
from scipy.io import wavfile

from .final_domain_visualizer import Interval, Tier, TextGrid, write_textgrid, read_textgrid

SENTENCE_END = re.compile(r"[.?!…]+[\"»”)]*$")
SPLIT_MODES = ("sentences", "segments")


@dataclass
class Word:
    text: str
    start: float
    end: float


@dataclass
class Segment:
    start: float
    end: float
    text: str
    source: str
    words: List[Word] = field(default_factory=list)
    label: str = ""
    seg_id: str = ""
    notes: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# 1. Audio
# ---------------------------------------------------------------------------
def load_audio(media: Path, work_dir: Path) -> Tuple[np.ndarray, int, Optional[Path]]:
    """Mono audio as float32 in [-1, 1]. WAV is read directly; anything else (video, MP3,
    M4A ...) goes through ffmpeg. Returns (samples, rate, extracted_wav or None)."""
    extracted = None
    path = media
    if media.suffix.lower() != ".wav":
        if shutil.which("ffmpeg") is None:
            raise RuntimeError(f"{media.name}: reading {media.suffix} files needs ffmpeg "
                               "(macOS: brew install ffmpeg)")
        extracted = work_dir / (media.stem + ".wav")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(media), "-vn", "-ac", "1",
                        "-c:a", "pcm_s16le", str(extracted)], check=True)
        path = extracted
    sr, x = wavfile.read(str(path))
    if x.dtype.kind == "i":
        x = x.astype(np.float32) / float(np.iinfo(x.dtype).max)
    elif x.dtype.kind == "u":
        x = (x.astype(np.float32) - 128.0) / 128.0
    else:
        x = x.astype(np.float32)
    if x.ndim == 2:
        x = x.mean(axis=1)
    return x, int(sr), extracted


def write_clip(x: np.ndarray, sr: int, start: float, end: float, dest: Path) -> None:
    a, b = max(0, int(round(start * sr))), min(len(x), int(round(end * sr)))
    clip = np.clip(x[a:b], -1.0, 1.0)
    wavfile.write(str(dest), sr, (clip * 32767).astype(np.int16))


# ---------------------------------------------------------------------------
# 2. Reading the phrase times
# ---------------------------------------------------------------------------
def _srt_time(t: str) -> float:
    h, m, rest = t.strip().replace(".", ",").split(":")
    s, ms = rest.split(",")
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000.0


def read_srt(path: Path) -> List[Segment]:
    segs, block = [], []
    for line in path.read_text(encoding="utf-8-sig", errors="replace").splitlines() + [""]:
        if line.strip():
            block.append(line.strip())
            continue
        times = next((b for b in block if "-->" in b), None)
        if times:
            a, b = times.split("-->")
            text = " ".join(l for l in block[block.index(times) + 1:]).strip()
            if text:
                segs.append(Segment(_srt_time(a), _srt_time(b), text, "srt"))
        block = []
    return segs


STAMP = re.compile(r"\[\s*([\d.]+)\s*s?\s*-\s*([\d.]+)\s*s?\s*\]\s*(.+)")


def _docx_lines(path: Path) -> List[str]:
    """Paragraph texts of a .docx without python-docx (one paragraph per line)."""
    with zipfile.ZipFile(path) as z:
        xml = z.read("word/document.xml").decode("utf-8", errors="replace")
    out = []
    for para in re.findall(r"<w:p[ >].*?</w:p>", xml, flags=re.S):
        txt = "".join(re.findall(r"<w:t[^>]*>(.*?)</w:t>", para, flags=re.S))
        out.append(re.sub(r"&amp;", "&", re.sub(r"&lt;", "<", re.sub(r"&gt;", ">", txt))))
    return out


def read_stamped_transcript(path: Path) -> List[Segment]:
    lines = _docx_lines(path) if path.suffix.lower() == ".docx" else \
        path.read_text(encoding="utf-8-sig", errors="replace").splitlines()
    segs = []
    for line in lines:
        m = STAMP.search(line)
        if m:
            segs.append(Segment(float(m.group(1)), float(m.group(2)), m.group(3).strip(), "transcript"))
    if not segs:
        raise ValueError(f"{path.name}: no lines like '[12.34s - 15.67s] text' found. "
                         "Use --text for a transcript without times.")
    return segs


def read_segments_csv(path: Path) -> List[Segment]:
    df = pd.read_csv(path) if path.suffix.lower() == ".csv" else pd.read_excel(path)
    cols = {c.lower().strip(): c for c in df.columns}
    for need in ("start", "end", "text"):
        if need not in cols:
            raise ValueError(f"{path.name}: needs columns start, end, text (found {list(df.columns)})")
    segs = []
    for _, r in df.iterrows():
        s = Segment(float(r[cols["start"]]), float(r[cols["end"]]), str(r[cols["text"]]).strip(), "csv")
        if "id" in cols and pd.notna(r[cols["id"]]):
            s.seg_id = str(r[cols["id"]]).strip()
        if "label" in cols and pd.notna(r[cols["label"]]):
            s.label = str(r[cols["label"]]).strip()
        segs.append(s)
    return segs


PAUSE_LABELS = {"", "#", "_", "<p:>", "<p>", "sil", "sp", "pause", "(.)", "..."}


def read_textgrid_segments(path: Path, tier: Optional[str] = None) -> List[Segment]:
    """Every labelled interval of one tier = one phrase. Without --tier: the interval tier with
    the most labelled (non-pause) intervals that contain at least two words."""
    tg = read_textgrid(path)
    tiers = [t for t in tg.tiers if t.kind == "interval"]
    if not tiers:
        raise ValueError(f"{path.name}: no interval tier")
    if tier:
        chosen = next((t for t in tiers if t.name == tier), None)
        if chosen is None:
            raise ValueError(f"{path.name}: no tier named {tier!r} (tiers: {[t.name for t in tiers]})")
    else:
        def score(t):
            labs = [iv.label.strip() for iv in t.intervals if iv.label.strip().lower() not in PAUSE_LABELS]
            return sum(1 for l in labs if len(l.split()) >= 2)
        chosen = max(tiers, key=score)
    segs = [Segment(iv.start, iv.end, iv.label.strip(), f"textgrid:{chosen.name}")
            for iv in chosen.intervals if iv.label.strip().lower() not in PAUSE_LABELS]
    if not segs:
        raise ValueError(f"{path.name}: tier {chosen.name!r} has no labelled intervals")
    print(f"  TextGrid tier used: {chosen.name!r} ({len(segs)} labelled intervals)")
    return segs


# ---------------------------------------------------------------------------
# 3. Speech recognition with word times (only for --text, or no times at all)
# ---------------------------------------------------------------------------
def whisper_words(wav: Path, model_size: str, language: str) -> List[Segment]:
    try:
        from faster_whisper import WhisperModel  # type: ignore
    except Exception as e:  # pragma: no cover
        raise RuntimeError("finding word times needs faster-whisper (pip install faster-whisper), "
                           "or give the times with --srt, --transcript or --segments") from e
    model = WhisperModel(model_size, device="cpu", compute_type="int8")
    gen, _ = model.transcribe(str(wav), language=language, beam_size=5, temperature=0.0, vad_filter=True,
                              condition_on_previous_text=False, word_timestamps=True)
    segs = []
    for s in gen:
        words = [Word(w.word.strip(), float(w.start), float(w.end)) for w in (s.words or []) if w.word.strip()]
        segs.append(Segment(float(s.start), float(s.end), s.text.strip(), "asr", words))
    return segs


def _norm(tok: str) -> str:
    t = unicodedata.normalize("NFD", tok.lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.sub(r"[^\w]", "", t)


def split_sentences_text(text: str) -> List[str]:
    """Your text -> sentences: one per line if it has several lines, else split at . ? !"""
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    if len(lines) > 1:
        return lines
    return [s.strip() for s in re.split(r"(?<=[.?!…])\s+", text.strip()) if s.strip()]


def align_text_to_words(sentences: List[str], words: List[Word]) -> List[Segment]:
    """Match each of YOUR sentences to the recognised words (difflib on normalised tokens).
    A sentence's start = its first matched word's start, end = its last matched word's end."""
    w_norm = [_norm(w.text) for w in words]
    s_tokens: List[Tuple[int, str]] = []
    for i, s in enumerate(sentences):
        s_tokens += [(i, _norm(t)) for t in s.split() if _norm(t)]
    sm = difflib.SequenceMatcher(a=[t for _, t in s_tokens], b=w_norm, autojunk=False)
    hit: dict = {}
    for blk in sm.get_matching_blocks():
        for k in range(blk.size):
            hit[blk.a + k] = blk.b + k
    per_sent = []
    for i in range(len(sentences)):
        idx = [j for j, (si, _) in enumerate(s_tokens) if si == i]
        per_sent.append((idx, [hit[j] for j in idx if j in hit]))
    out = []
    for i, s in enumerate(sentences):
        idx, matched = per_sent[i]
        if not matched:
            out.append(Segment(np.nan, np.nan, s, "text+asr", notes=["NOT FOUND in the recording: cut it by hand"]))
            continue
        a, b = min(matched), max(matched)
        # an unmatched first / last word (misheard, e.g. "Chère dame" heard as "Madame") still belongs to this
        # sentence: extend over the recognised words up to the neighbouring sentences' matched words
        prev_end = next((max(m) for _, m in reversed(per_sent[:i]) if m), -1)
        next_start = next((min(m) for _, m in per_sent[i + 1:] if m), len(words))
        if idx and idx[0] not in hit:
            a = max(prev_end + 1, a - (sum(1 for j in idx if j < min(k for k in idx if k in hit))))
        if idx and idx[-1] not in hit:
            b = min(next_start - 1, b + (sum(1 for j in idx if j > max(k for k in idx if k in hit))))
        seg = Segment(words[a].start, words[b].end, s, "text+asr", words[a:b + 1])
        share = len(matched) / max(len(idx), 1)
        if share < 0.6:
            seg.notes.append(f"only {share:.0%} of the words matched the recording: check the boundaries")
        out.append(seg)
    return out


# ---------------------------------------------------------------------------
# 4. Sentence splitting, loops, padding
# ---------------------------------------------------------------------------
def split_by_sentence(segs: List[Segment]) -> List[Segment]:
    out = []
    for s in segs:
        if not s.words:
            n = len(split_sentences_text(s.text))
            if n > 1:
                s.notes.append(f"holds {n} sentences; no word times to split it (cut by hand, or use --text)")
            out.append(s)
            continue
        cur: List[Word] = []
        for w in s.words:
            cur.append(w)
            if SENTENCE_END.search(w.text):
                out.append(Segment(cur[0].start, cur[-1].end, " ".join(x.text for x in cur), s.source, cur))
                cur = []
        if cur:
            out.append(Segment(cur[0].start, cur[-1].end, " ".join(x.text for x in cur), s.source, cur))
    return out


def flag_suspect(segs: List[Segment], repeat_min: int = 3, min_chars_per_s: float = 2.0) -> None:
    norm = [_norm(s.text.replace(" ", "")) for s in segs]
    i = 0
    while i < len(segs):
        j = i
        while j + 1 < len(segs) and norm[j + 1] == norm[i] and norm[i]:
            j += 1
        if j - i + 1 >= repeat_min:
            for k in range(i, j + 1):
                segs[k].notes.append(f"SUSPECT: same text {j - i + 1}x in a row (speech-recognition loop?)")
        i = j + 1
    for s in segs:
        d = s.end - s.start
        if d > 4 and len(s.text) / d < min_chars_per_s:
            s.notes.append(f"SUSPECT: {d:.1f} s for {len(s.text)} characters (music or noise?)")


def padded_bounds(segs: List[Segment], pad: float, total: float) -> List[Tuple[float, float]]:
    """Padding that stops halfway through the gap to the neighbouring phrase (never into it)."""
    out = []
    for k, s in enumerate(segs):
        lo = s.start - pad
        hi = s.end + pad
        if k > 0:
            lo = max(lo, (segs[k - 1].end + s.start) / 2 if segs[k - 1].end <= s.start else s.start)
        if k + 1 < len(segs):
            nxt = segs[k + 1]
            hi = min(hi, (s.end + nxt.start) / 2 if s.end <= nxt.start else s.end)
        out.append((max(0.0, lo), min(total, hi)))
    return out


def slug(text: str, n: int = 4) -> str:
    t = unicodedata.normalize("NFD", text.lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    words = re.findall(r"[a-z0-9]+", t)[:n]
    return "-".join(words) or "phrase"


# ---------------------------------------------------------------------------
# 5. Run
# ---------------------------------------------------------------------------
def run(media: Path, out: Path, srt: Optional[Path] = None, transcript: Optional[Path] = None,
        segments: Optional[Path] = None, text: Optional[Path] = None, split: str = "sentences",
        pad: float = 0.15, min_dur: float = 0.25, keep_suspect: bool = False,
        match: Optional[str] = None, asr_model: str = "small", language: str = "fr",
        textgrid: Optional[Path] = None, tier: Optional[str] = None, prefix: str = "") -> pd.DataFrame:
    if split not in SPLIT_MODES:
        raise ValueError(f"--split must be one of {SPLIT_MODES}")
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        x, sr, extracted = load_audio(media, Path(tmp))
        if extracted is not None:                   # keep the audio track of a video for Praat
            shutil.copy(extracted, out / extracted.name)
        audio_for_asr = extracted or media
        total = len(x) / sr

        if segments:
            segs, how = read_segments_csv(segments), f"your list ({segments.name})"
        elif textgrid:
            segs, how = read_textgrid_segments(textgrid, tier), f"TextGrid ({textgrid.name})"
        elif srt:
            segs, how = read_srt(srt), f"subtitles ({srt.name})"
        elif transcript:
            segs, how = read_stamped_transcript(transcript), f"timestamped transcript ({transcript.name})"
        elif text:
            words = [w for s in whisper_words(audio_for_asr, asr_model, language) for w in s.words]
            sents = split_sentences_text(text.read_text(encoding="utf-8-sig", errors="replace"))
            segs, how = align_text_to_words(sents, words), f"your text ({text.name}) matched to word times"
        else:
            segs, how = whisper_words(audio_for_asr, asr_model, language), "speech recognition (CHECK the texts)"

    if split == "sentences":
        segs = split_by_sentence(segs)
    segs = sorted([s for s in segs if s.start == s.start], key=lambda s: s.start) + \
        [s for s in segs if s.start != s.start]            # NaN (not found) last
    timed = [s for s in segs if s.start == s.start]
    flag_suspect(timed)
    bounds = padded_bounds(timed, pad, total)

    rows, tg_ivs, n = [], [], 0
    for s, (lo, hi) in zip(timed, bounds):
        suspect = any(nt.startswith("SUSPECT") for nt in s.notes)
        if (match and not re.search(match, s.text, flags=re.I)) or (suspect and not keep_suspect):
            rows.append({"ID": "", "START_S": round(s.start, 3), "END_S": round(s.end, 3), "TEXT": s.text,
                         "CLIP": "", "STATUS": "skipped (suspect)" if suspect else "skipped (--match)",
                         "SOURCE": s.source, "NOTES": "; ".join(s.notes)})
            continue
        if s.end - s.start < min_dur:
            s.notes.append(f"shorter than {min_dur} s")
        n += 1
        sid = s.seg_id or f"{n:03d}"
        name = f"{prefix}{sid}_{slug(s.label or s.text)}"
        write_clip(x, sr, lo, hi, out / f"{name}.wav")
        (out / f"{name}.txt").write_text(s.text + "\n", encoding="utf-8")
        rows.append({"ID": sid, "START_S": round(s.start, 3), "END_S": round(s.end, 3),
                     "DURATION_S": round(s.end - s.start, 3), "CLIP_START_S": round(lo, 3),
                     "CLIP_END_S": round(hi, 3), "TEXT": s.text, "CLIP": f"{name}.wav", "STATUS": "written",
                     "SOURCE": s.source, "NOTES": "; ".join(s.notes)})
        tg_ivs.append(Interval(s.start, s.end, f"{sid}: {s.text}"))
    for s in segs:
        if s.start != s.start:
            rows.append({"ID": "", "TEXT": s.text, "STATUS": "not found", "SOURCE": s.source,
                         "NOTES": "; ".join(s.notes)})

    filled, cur = [], 0.0
    for iv in sorted(tg_ivs, key=lambda i: i.start):
        st = max(iv.start, cur)
        if st > cur:
            filled.append(Interval(cur, st, ""))
        if iv.end > st:
            filled.append(Interval(st, iv.end, iv.label))
            cur = iv.end
    if cur < total:
        filled.append(Interval(cur, total, ""))
    write_textgrid(TextGrid(0.0, total, [Tier("phrases", "interval", filled)]), out / f"{media.stem}.TextGrid")

    df = pd.DataFrame(rows)
    if "ID" in df:
        df["ID"] = df["ID"].fillna("").astype(str)
    df.to_csv(out / "segments.csv", index=False, encoding=CSV_ENCODING)
    n_skip = int(df.STATUS.astype(str).str.startswith("skipped").sum()) if len(df) else 0
    n_flag = int(((df.STATUS == "written") & (df.NOTES.astype(str) != "")).sum()) if len(df) else 0
    print(f"{media.name}: phrase times from {how}")
    print(f"  {n} clips written to {out}  |  {n_skip} skipped  |  {n_flag} with a note to check (segments.csv)")
    print(f"  next: python -m modules.run_all --folder \"{out}\" --out \"{out}_results\" --measure both")
    return df


def main():
    ap = argparse.ArgumentParser(description="Cut a long recording (audio or video) into one WAV + .txt per phrase")
    ap.add_argument("--media", required=True, help="audio or video file (wav, mp3, m4a, mp4, mov ...)")
    ap.add_argument("--out", required=True, help="folder for the clips (created if needed)")
    src = ap.add_mutually_exclusive_group()
    src.add_argument("--segments", help="CSV/XLSX with columns start, end, text (+ optional id, label)")
    src.add_argument("--textgrid", help="Praat TextGrid: each labelled interval of --tier becomes a clip (e.g. PFC)")
    src.add_argument("--srt", help="subtitle file with the phrase times (e.g. IntonaSphere's .srt)")
    src.add_argument("--transcript", help="IntonaSphere transcript (.docx/.txt) with '[12.34s - 15.67s] text' lines")
    src.add_argument("--text", help="plain text, no times: word times come from faster-whisper")
    ap.add_argument("--split", choices=SPLIT_MODES, default="sentences",
                    help="sentences (default) = one clip per sentence where word times allow; segments = as given")
    ap.add_argument("--pad", type=float, default=0.15, help="seconds of context kept around each phrase (default 0.15)")
    ap.add_argument("--min-dur", type=float, default=0.25, help="flag phrases shorter than this (s)")
    ap.add_argument("--match", help="only phrases whose text matches this pattern, e.g. '\\?' for questions")
    ap.add_argument("--keep-suspect", action="store_true", help="also write phrases flagged as recognition loops")
    ap.add_argument("--tier", help="TextGrid tier to cut by (default: the tier with the most multi-word intervals)")
    ap.add_argument("--prefix", default="", help="added before every clip name, e.g. the speaker code '11aab1_' "
                                                 "(keeps clips from several recordings apart in one folder)")
    ap.add_argument("--asr-model", default="small")
    ap.add_argument("--language", default="fr")
    a = ap.parse_args()
    run(user_path(a.media), user_path(a.out), user_path(a.srt), user_path(a.transcript),
        user_path(a.segments), user_path(a.text), a.split, a.pad, a.min_dur, a.keep_suspect,
        a.match, a.asr_model, a.language, user_path(a.textgrid), a.tier, a.prefix)


if __name__ == "__main__":
    main()
