#!/usr/bin/env python3
"""Анализ карты перевода: объёмы, уникальность, шум, топ-повторы."""
import collections
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.abspath(os.path.join(HERE, "..", "translation_map"))


def load(name):
    return [json.loads(l) for l in open(os.path.join(WORK, name), encoding="utf-8")]


def main():
    recs = load("scripts.jsonl")
    trec = load("tables.jsonl")
    print("scripts", len(recs), "tables", len(trec))

    by = collections.Counter(r["file"].split(os.sep)[1] for r in recs)
    print("scripts by dir:", dict(by))

    scena = [r for r in recs if r["file"].startswith("script" + os.sep + "scena")]
    print("scena strings:", len(scena))
    for r in sorted(scena, key=lambda r: -len(r["jp_text"]))[:5]:
        print("  LEN", len(r["jp_text"]), r["file"], r["id"].split(":")[1], repr(r["jp_text"][:80]))

    u = set(r["jp_text"] for r in recs)
    ut = set(r["jp_text"] for r in trec)
    print("unique script:", len(u), "unique table:", len(ut), "unique total:", len(u | ut))
    print("len<=1 script recs:", sum(1 for r in recs if len(r["jp_text"]) <= 1))

    c = collections.Counter(r["jp_text"] for r in recs + trec if len(r["jp_text"]) >= 4)
    print("top duplicated:", c.most_common(5))
    print("candidates over 200 chars:", sum(1 for r in recs + trec if len(r["jp_text"]) > 200))


if __name__ == "__main__":
    main()
