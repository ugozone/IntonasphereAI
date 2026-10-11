"""
IntonaSphere AI - automatic alignment (WAV -> WebMAUS TextGrid)
==============================================================

Gives every WAV file a WebMAUS-style TextGrid (ORT-MAU, KAN-MAU, MAU, MAS ...)
so that the F_ToBI assistant and the final-domain visualizer can run on a bare
recording. Nothing that already exists is replaced:

    input in the folder                    what happens                          provenance written
    -------------------------------------  ------------------------------------  ---------------------------
    x.wav + x.TextGrid                     used as is (the original workflow)    ALIGNMENT_SOURCE=user_textgrid
    x.wav + x.txt                          your text -> WebMAUS -> TextGrid      TEXT_SOURCE=user_txt
    x.wav only, PFC name (...tw1/2/3)      PFC question text -> WebMAUS          TEXT_SOURCE=pfc_texte_lu
    x.wav only, any other recording        speech recognition (faster-whisper)  TEXT_SOURCE=asr (CHECK IT)
                                           -> x.asr.txt -> WebMAUS

Modes (--align):  none = original behaviour, WAVs without a TextGrid are skipped
                  pfc  = automatic only for PFC file names (and any x.txt)
                  any  = also uses speech recognition for other recordings (default)

WebMAUS (BAS Web Services, Schiel 1999; Kisler, Reichel & Schiel 2017)
    1st try  runPipeline, PIPE=G2P_MAUS_PHO2SYL, LANGUAGE=fra-FR, OUTFORMAT=TextGrid
             -> ORT-MAU, KAN-MAU, KAS-MAU, MAU, MAS, TRN (the tiers your files have)
    fallback runMAUSBasic, LANGUAGE=fra-FR -> ORT-MAU, KAN-MAU, MAU; the syllable tier
             (MAS) is then built here from the MAU phones (maximal-onset rule, below)
The language is ALWAYS sent as French (fra-FR), which prevents the German-model
alignment found in 64aab1tw1. Results are cached: a TextGrid already produced in
the alignment folder is reused, so a second run makes no new requests.

Terms: the BAS services are free for academic, non-profit research; a sound file
is uploaded to the BAS server in Munich (kept there for 24 h). Make sure that is
compatible with the PFC data-use conditions.

Speech recognition (only for non-PFC files without a text file) uses faster-whisper,
as transcriber.py in the repository does, with language=fr and NO prompt (a prompt
containing the PFC sentences would push the recognizer to "hear" them). The
transcript is saved as x.asr.txt: correct it, rename it x.txt, and rerun - the
corrected text then takes priority.

Command line (alignment only):
    python -m modules.auto_align --folder data/wavs --out data/aligned [--align any]
"""
from __future__ import annotations

from . import user_path, CSV_ENCODING

import argparse
import re
import shutil
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from scipy.io import wavfile

from .final_domain_visualizer import (Interval, Tier, read_textgrid, write_textgrid, match_textgrid,
                                      PFC_QUESTIONS)

BAS = "https://clarin.phonetik.uni-muenchen.de/BASWebServices/services"
PIPE_URL = f"{BAS}/runPipeline"
BASIC_URL = f"{BAS}/runMAUSBasic"
PFC_NAME = re.compile(r"^(.+?)tw([1-4])$", re.I)


@dataclass
class AlignResult:
    wav: Path
    textgrid: Optional[Path]
    text: str = ""
    text_source: str = ""
    alignment_source: str = ""
    status: str = ""
    message: str = ""
    user_textgrid: Optional[Path] = None      # the user's own TextGrid, kept for comparison under --realign


# ---------------------------------------------------------------------------
# 1. Text for each recording
# ---------------------------------------------------------------------------
def pfc_text(wav: Path) -> Optional[str]:
    m = PFC_NAME.match(re.sub(r"\s+copy$", "", wav.stem, flags=re.I))
    return PFC_QUESTIONS.get(m.group(2)) if m else None


def read_txt(p: Path) -> str:
    raw = p.read_bytes()
    for enc in ("utf-8-sig", "utf-16", "latin-1"):
        try:
            return " ".join(raw.decode(enc).split())
        except UnicodeDecodeError:
            continue
    return ""


def asr_text(wav: Path, model_size: str = "small") -> str:
    """French transcription with faster-whisper (no prompt, deterministic decoding)."""
    try:
        from faster_whisper import WhisperModel  # type: ignore
    except Exception as e:  # pragma: no cover
        raise RuntimeError("speech recognition needs faster-whisper (pip install faster-whisper); "
                           "or put the sentence in a .txt file next to the WAV") from e
    model = WhisperModel(model_size, device="cpu", compute_type="int8")
    segs, _ = model.transcribe(str(wav), language="fr", beam_size=10, best_of=5, temperature=0.0,
                               vad_filter=True, condition_on_previous_text=False)
    return " ".join(s.text.strip() for s in segs).strip()


def get_text(wav: Path, mode: str, asr_model: str) -> Tuple[str, str]:
    """Priority: x.txt written by the user > PFC question > speech recognition."""
    for cand in (wav.with_suffix(".txt"), wav.with_suffix(".TXT")):
        if cand.exists():
            return read_txt(cand), "user_txt"
    t = pfc_text(wav)
    if t:
        return t, "pfc_texte_lu"
    if mode != "any":
        return "", ""
    asr_file = wav.with_suffix(".asr.txt")
    if asr_file.exists():
        return read_txt(asr_file), "asr (cached)"
    t = asr_text(wav, asr_model)
    asr_file.write_text(t + "\n", encoding="utf-8")
    return t, "asr"


# ---------------------------------------------------------------------------
# 2. WebMAUS
# ---------------------------------------------------------------------------
def mono16(wav: Path, tmp_dir: Path) -> Path:
    """BAS needs mono 16-bit PCM; convert only when necessary."""
    sr, x = wavfile.read(str(wav))
    if x.ndim == 1 and x.dtype == np.int16:
        return wav
    if x.ndim > 1:
        x = x.mean(axis=1)
    if x.dtype.kind == "f":
        x = np.clip(x, -1, 1) * 32767
    elif x.dtype == np.int32:
        x = x / 65536.0
    elif x.dtype == np.uint8:
        x = (x.astype(float) - 128) * 256
    tmp_dir.mkdir(parents=True, exist_ok=True)
    out = tmp_dir / wav.name
    wavfile.write(str(out), sr, x.astype(np.int16))
    return out


def _parse_bas_xml(text: str) -> Dict[str, str]:
    try:
        root = ET.fromstring(text)
        return {child.tag: (child.text or "").strip() for child in root}
    except ET.ParseError:
        m = re.search(r"<downloadLink>(.*?)</downloadLink>", text, re.S)
        s = re.search(r"<success>(.*?)</success>", text, re.S)
        return {"downloadLink": m.group(1).strip() if m else "", "success": s.group(1).strip() if s else "false",
                "output": text[:500]}


def _post(url: str, wav: Path, text: str, params: Dict[str, str], timeout: int) -> Dict[str, str]:
    import requests
    with open(wav, "rb") as fs:
        files = {"SIGNAL": (wav.name, fs, "audio/wav"),
                 "TEXT": (wav.stem + ".txt", text.encode("utf-8"), "text/plain")}
        r = requests.post(url, data=params, files=files, timeout=timeout)
    r.raise_for_status()
    return _parse_bas_xml(r.text)


def _download(link: str, dest: Path, timeout: int) -> None:
    import requests
    r = requests.get(link, timeout=timeout)
    r.raise_for_status()
    dest.write_bytes(r.content)


def webmaus(wav: Path, text: str, dest: Path, language: str = "fra-FR", timeout: int = 300,
            retries: int = 2) -> str:
    """Align one file. Returns the alignment source; raises RuntimeError if both services fail."""
    errors = []
    tmp = dest.parent / "_tmp_mono16"
    sig = mono16(wav, tmp)
    attempts = [
        ("webmaus_pipeline_G2P_MAUS_PHO2SYL", PIPE_URL,
         {"LANGUAGE": language, "PIPE": "G2P_MAUS_PHO2SYL", "OUTFORMAT": "TextGrid"}),
        ("webmaus_basic+local_syllables", BASIC_URL,
         {"LANGUAGE": language}),                       # documented call; returns a TextGrid
    ]
    for name, url, params in attempts:
        for k in range(retries):
            try:
                res = _post(url, sig, text, params, timeout)
                if res.get("success", "").lower() == "true" and res.get("downloadLink"):
                    _download(res["downloadLink"], dest, timeout)
                    tg = read_textgrid(dest)             # must be a readable TextGrid
                    if tg.get("MAS") is None:
                        add_syllable_tier(dest)
                        name = name if "local" in name else name + "+local_syllables"
                    if sig != wav:
                        shutil.rmtree(tmp, ignore_errors=True)
                    return name
                errors.append(f"{name}: success={res.get('success')} {res.get('output', '')[:200]} {res.get('warnings', '')[:200]}")
                break                                   # a clean refusal will not change on retry
            except Exception as e:                      # network / HTTP error -> retry, then next service
                errors.append(f"{name}: {type(e).__name__}: {e}")
                time.sleep(2 * (k + 1))
    if sig != wav:
        shutil.rmtree(tmp, ignore_errors=True)
    raise RuntimeError(" | ".join(errors))


# ---------------------------------------------------------------------------
# 3. Syllable tier from MAU phones (used only when WebMAUS returns no MAS tier)
# ---------------------------------------------------------------------------
V = {"i", "e", "E", "a", "A", "O", "o", "u", "y", "2", "9", "@", "e~", "a~", "o~", "9~",
     "ɛ", "ɑ", "ɔ", "ø", "œ", "ə", "ɛ̃", "ɑ̃", "ɔ̃", "œ̃"}
GLIDES = {"j", "w", "H", "ɥ"}
LIQUIDS = {"l", "R", "r", "ʁ"}
OBSTRUENTS = {"p", "b", "t", "d", "k", "g", "ɡ", "f", "v"}


def _valid_onset(cs: List[str]) -> bool:
    """French onsets: C, C+glide, obstruent+liquid (not tl/dl), obstruent+liquid+glide."""
    if len(cs) <= 1:
        return True
    if len(cs) == 2:
        a, b = cs
        return b in GLIDES or (a in OBSTRUENTS and b in LIQUIDS and not (a in {"t", "d"} and b == "l"))
    if len(cs) == 3:
        return _valid_onset(cs[:2]) and cs[0] in OBSTRUENTS and cs[1] in LIQUIDS and cs[2] in GLIDES
    return False


def syllabify(phones: List[Interval], word_ends: Optional[List[float]] = None) -> List[Interval]:
    """Maximal-onset syllabification of MAU phones inside each word (word boundaries
    are kept, as WebMAUS PHO2SYL does with wsync=yes) and each pause-free stretch.
    Labels are the SAMPA phones separated by spaces, like WebMAUS MAS."""
    word_ends = sorted(word_ends or [])
    out: List[Interval] = []
    stretch: List[Interval] = []

    def flush():
        if not stretch:
            return
        nuc = [i for i, p in enumerate(stretch) if p.label in V]
        if not nuc:
            out.append(Interval(stretch[0].start, stretch[-1].end, " ".join(p.label for p in stretch)))
            stretch.clear(); return
        bounds = [0]
        for a, b in zip(nuc[:-1], nuc[1:]):
            cons = list(range(a + 1, b))
            k = len(cons)
            while k > 0 and not _valid_onset([stretch[i].label for i in cons[len(cons) - k:]]):
                k -= 1
            bounds.append(b - k)
        bounds.append(len(stretch))
        for s, e in zip(bounds[:-1], bounds[1:]):
            seg = stretch[s:e]
            out.append(Interval(seg[0].start, seg[-1].end, " ".join(p.label for p in seg)))
        stretch.clear()

    for p in phones:
        lab = p.label.strip()
        if stretch and any(abs(p.start - e) < 0.003 for e in word_ends):
            flush()                                     # word boundary
        if not lab or lab.startswith("<"):
            flush()
            out.append(Interval(p.start, p.end, lab))
        else:
            stretch.append(Interval(p.start, p.end, lab))
    flush()
    return out


def add_syllable_tier(tg_path: Path) -> None:
    tg = read_textgrid(tg_path)
    mau = tg.get("MAU")
    if mau is None or tg.get("MAS") is not None:
        return
    ort = tg.get("ORT-MAU")
    ends = [iv.end for iv in ort.intervals if iv.label.strip()] if ort is not None else []
    tg.tiers.append(Tier("MAS", "interval", syllabify(mau.intervals, ends)))
    write_textgrid(tg, tg_path)


# ---------------------------------------------------------------------------
# 4. Folder
# ---------------------------------------------------------------------------
def _log_dir(d: Path) -> Path:
    """The alignment log goes to the output side, never into the data folder."""
    d.mkdir(parents=True, exist_ok=True)
    return d


def ensure_alignments(folder: Path, align_dir: Path, mode: str = "any", language: str = "fra-FR",
                      asr_model: str = "small", log=print, realign: bool = False) -> List[AlignResult]:
    """Return one AlignResult per WAV. Existing TextGrids are used unchanged, unless realign=True:
    then EVERY file is aligned again with WebMAUS (from the sound + its text), so the whole set is
    aligned by one documented procedure; the user's TextGrid is only recorded for comparison."""
    if realign and mode == "none":
        raise ValueError("--realign needs WebMAUS: use --align pfc (or any), not --align none")
    folder, align_dir = Path(folder), Path(align_dir)
    wavs = sorted(p for p in folder.iterdir() if p.suffix.lower() == ".wav" and not p.name.startswith("."))
    user_tgs = [p for p in folder.iterdir() if p.suffix.lower() == ".textgrid" and not p.name.startswith(".")
                and not p.stem.endswith(("_ftobi", "_checked", "_cues"))]
    results: List[AlignResult] = []
    for w in wavs:
        tg = match_textgrid(w, user_tgs)
        if tg is not None and not realign:
            results.append(AlignResult(w, tg, alignment_source="user_textgrid", status="ok", user_textgrid=tg))
            continue
        cached = align_dir / f"{w.stem}.TextGrid"
        if cached.exists():
            results.append(AlignResult(w, cached, alignment_source="webmaus (cached)", status="ok", user_textgrid=tg))
            continue
        if mode == "none":
            results.append(AlignResult(w, None, status="skipped", message="no TextGrid (alignment off)"))
            continue
        try:
            text, src = get_text(w, mode, asr_model)
        except RuntimeError as e:
            results.append(AlignResult(w, None, status="failed", message=str(e), user_textgrid=tg))
            continue
        if not text:
            results.append(AlignResult(w, None, status="skipped", user_textgrid=tg,
                                       message="no TextGrid, no .txt and not a PFC file name (use --align any for speech recognition)"))
            continue
        align_dir.mkdir(parents=True, exist_ok=True)
        (align_dir / f"{w.stem}.txt").write_text(text + "\n", encoding="utf-8")
        log(f"  WebMAUS ({language}) <- {w.name}  [text: {src}] {text[:70]}")
        try:
            how = webmaus(w, text, cached, language)
            results.append(AlignResult(w, cached, text, src, how, "ok",
                                       "CHECK the .asr.txt transcript" if src.startswith("asr") else "", tg))
        except Exception as e:
            if cached.exists():
                cached.unlink()
            results.append(AlignResult(w, None, text, src, "", "failed", f"WebMAUS failed: {e}", tg))
    pd.DataFrame([{"AUDIO_FILE": r.wav.name, "TEXTGRID": r.textgrid.name if r.textgrid else "",
                   "TEXTGRID_FOLDER": str(r.textgrid.parent) if r.textgrid else "", "TEXT_SOURCE": r.text_source,
                   "ALIGNMENT_SOURCE": r.alignment_source, "STATUS": r.status, "MESSAGE": r.message,
                   "TEXT": r.text, "USER_TEXTGRID": str(r.user_textgrid) if r.user_textgrid else ""}
                  for r in results]).to_csv(
        _log_dir(align_dir) / "alignment_log.csv", index=False, encoding=CSV_ENCODING)
    return results


def main():
    ap = argparse.ArgumentParser(description="Give every WAV a WebMAUS TextGrid (existing TextGrids are kept)")
    ap.add_argument("--folder", required=True)
    ap.add_argument("--out", default=None, help="alignment folder (default: <folder>/aligned)")
    ap.add_argument("--align", choices=["none", "pfc", "any"], default="any")
    ap.add_argument("--language", default="fra-FR")
    ap.add_argument("--asr-model", default="small")
    ap.add_argument("--realign", action="store_true", help="align every WAV with WebMAUS, ignoring existing TextGrids")
    a = ap.parse_args()
    out = user_path(a.out) if a.out else user_path(a.folder) / "aligned"
    res = ensure_alignments(user_path(a.folder), out, a.align, a.language, a.asr_model, realign=a.realign)
    for r in res:
        print(f"{r.wav.name:28s} {r.status:8s} {r.alignment_source or '':38s} {r.text_source:14s} {r.message}")


if __name__ == "__main__":
    main()
