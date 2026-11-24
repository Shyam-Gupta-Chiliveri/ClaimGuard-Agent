"""Retrieval index over the project PDFs, methodology notes and data source cards.

Pure-Python BM25 (no external service, runs on a small VM). German and English text is
normalised (umlauts folded, light suffix stripping) so "Unfälle" matches "unfall".

Build:  python -m rag.index          (writes data/rag/index.json)
Query:  from rag.index import Retriever; Retriever.load().search("Regionalklasse")
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
from collections import Counter
from pathlib import Path

import pandas as pd

from core.paths import MARTS, RAG_DIR, REPORTS, ROOT

PDF_DIR = Path(os.environ.get("PDF_DIR", ROOT.parent / "PDFs"))
NOTES = ROOT / "rag" / "notes"
CHUNK, OVERLAP = 900, 150
K1, B = 1.4, 0.75

STOP = set("""
a an and are as at be by for from has have in is it its of on or that the to was were will with this these those
der die das und ist im in den dem des ein eine einer eines zu mit von auf fur für als auch an bei oder nicht sich sind
wird werden nach aus am um wie bis
""".split())
FOLD = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"})
SUFFIXES = ("ungen", "ung", "en", "er", "es", "ing", "ed", "s", "e", "n")


def tokens(text: str) -> list[str]:
    out = []
    for t in re.findall(r"[a-z0-9]+", text.lower().translate(FOLD)):
        if t in STOP or len(t) < 2:
            continue
        for suf in SUFFIXES:
            if len(t) > len(suf) + 3 and t.endswith(suf):
                t = t[: -len(suf)]
                break
        out.append(t)
    return out


def split(text: str) -> list[str]:
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{2,}", "\n", text).strip()
    if len(text) <= CHUNK:
        return [text] if text else []
    parts, start = [], 0
    while start < len(text):
        end = min(start + CHUNK, len(text))
        cut = text.rfind(". ", start + CHUNK // 2, end)
        end = cut + 1 if cut != -1 and end < len(text) else end
        parts.append(text[start:end].strip())
        if end >= len(text):
            break
        start = max(end - OVERLAP, start + 1)
    return parts


def prose_ratio(text: str) -> float:
    letters = sum(ch.isalpha() for ch in text)
    digits = sum(ch.isdigit() for ch in text)
    return letters / max(letters + digits, 1)


def pdf_docs() -> list[dict]:
    from pypdf import PdfReader

    docs, seen_files, seen_chunks = [], set(), set()
    for path in sorted(PDF_DIR.glob("*.pdf"), reverse=True):
        reader = PdfReader(path)
        pages = [(i + 1, p.extract_text() or "") for i, p in enumerate(reader.pages)]
        digest = hashlib.sha1("".join(t for _, t in pages).encode()).hexdigest()
        if digest in seen_files:
            continue
        seen_files.add(digest)
        line_pages = Counter(line.strip() for _, t in pages for line in set(t.splitlines()) if line.strip())
        boilerplate = {line for line, n in line_pages.items() if len(pages) > 4 and n > len(pages) / 2}
        is_table_report = path.name.startswith("fz1_")
        for page, text in pages:
            text = "\n".join(line for line in text.splitlines() if line.strip() not in boilerplate)
            if len(text.strip()) < 120 or (is_table_report and prose_ratio(text) < 0.85):
                continue
            for chunk in split(text):
                key = re.sub(r"[\d\s]+", "", chunk.lower())[:400]
                if key in seen_chunks:
                    continue
                seen_chunks.add(key)
                docs.append({"source": path.name, "kind": "pdf", "locator": f"page {page}", "text": chunk})
    return docs


def note_docs() -> list[dict]:
    docs = []
    paths = sorted(NOTES.glob("*.md")) + sorted(REPORTS.glob("*.md"))
    for path in paths:
        section = path.stem
        for block in re.split(r"\n(?=#{1,3} )", path.read_text(encoding="utf-8")):
            heading = block.splitlines()[0].lstrip("# ").strip() if block.strip() else section
            if len(block.strip()) < 160:
                continue
            for chunk in split(block):
                docs.append({"source": path.name, "kind": "note", "locator": heading, "text": chunk})
    return docs


def data_cards() -> list[dict]:
    fraud = pd.read_csv(MARTS / "fraud_landscape.csv", dtype=str)
    docs = []
    for (src, year, geo), g in fraud.groupby(["source_dataset", "year", "geo_name"]):
        lines = [f"{r.measure.replace('_', ' ')} ({r.breakdown.replace('_', ' ')}): {r.value} {r.unit.replace('_', ' ')}"
                 for r in g.itertuples()]
        note = g.source_note.dropna().iloc[0] if g.source_note.notna().any() else ""
        text = f"{src} {geo} {year}. " + "; ".join(lines) + f". Source: {note}"
        for chunk in split(text):
            docs.append({"source": f"{src}.csv", "kind": "data", "locator": f"{geo} {year}", "text": chunk})
    rules = pd.read_csv(MARTS / "fraud_rules.csv")
    for r in rules.itertuples():
        docs.append({"source": "fraud_red_flag_rules.csv", "kind": "data", "locator": r.rule_id,
                     "text": f"{r.rule_id} {r.indicator} ({r.points} points). Applies when: {r.applies_when}. "
                             f"Basis: {r.published_basis}. Source: {r.source}."})
    return docs


class Retriever:
    def __init__(self, docs: list[dict]):
        self.docs = docs
        self.tf = [Counter(tokens(d["text"] + " " + d["locator"])) for d in docs]
        self.len = [sum(c.values()) for c in self.tf]
        self.avg = sum(self.len) / max(len(self.len), 1)
        df = Counter(t for c in self.tf for t in c)
        n = len(docs)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    @classmethod
    def load(cls) -> Retriever:
        return cls(json.loads((RAG_DIR / "index.json").read_text(encoding="utf-8"))["docs"])

    def search(self, query: str, k: int = 5, kind: str | None = None) -> list[dict]:
        q = tokens(query)
        scored = []
        for i, tf in enumerate(self.tf):
            if kind and self.docs[i]["kind"] != kind:
                continue
            s = 0.0
            for t in q:
                f = tf.get(t)
                if f:
                    s += self.idf[t] * f * (K1 + 1) / (f + K1 * (1 - B + B * self.len[i] / self.avg))
            if s > 0:
                scored.append((s, i))
        scored.sort(reverse=True)
        return [{**self.docs[i], "score": round(s, 3), "id": i} for s, i in scored[:k]]


def build() -> dict:
    docs = note_docs() + data_cards()
    if PDF_DIR.exists():
        docs += pdf_docs()
    RAG_DIR.mkdir(parents=True, exist_ok=True)
    (RAG_DIR / "index.json").write_text(json.dumps({"docs": docs}, ensure_ascii=False), encoding="utf-8")
    kinds = Counter(d["kind"] for d in docs)
    sources = Counter(d["source"] for d in docs)
    print(f"{len(docs)} chunks {dict(kinds)} from {len(sources)} sources")
    return {"chunks": len(docs), "kinds": dict(kinds)}


if __name__ == "__main__":
    build()
