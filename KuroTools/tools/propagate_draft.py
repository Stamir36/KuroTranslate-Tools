# -*- coding: utf-8 -*-
"""Разнести принятую правку по всем копиям той же японской строки.

Одна и та же реплика лежит в карте десятками копий (движок вставляет
библиотечные строки во все .dat, а сцены имеют по 2–4 ветки). Правка по
номеру строки чинит одну копию; этот инструмент находит остальные, у которых
японский текст тот же **и** перевод всё ещё старый, и готовит для них такой же
черновик по номерам строк.

    python tools/propagate_draft.py tools/drafts/rv/*.ok.json \\
        --kind script --out tools/drafts/rv/prop_script.json

Дальше как обычно: `validate_draft.py` → `apply_ru.py --skip-unknown`.
"""
import argparse
import collections
import glob
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
MAP_FILES = {"table": "tables.jsonl", "script": "scripts.jsonl"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("drafts", nargs="+")
    ap.add_argument("--kind", default="script", choices=["script", "table"])
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    path = os.path.join(ROOT, "translation_map", MAP_FILES[a.kind])
    rows = [json.loads(l) for l in io.open(path, encoding="utf-8") if l.strip()]

    paths = []
    for pat in a.drafts:
        paths.extend(sorted(glob.glob(pat)) or [pat])

    fixes = {}          # jp -> (was, ru)
    for p in paths:
        doc = json.load(io.open(p, encoding="utf-8"))
        for fname, slots in (doc.get("files") or {}).items():
            if fname.split("/", 1)[0] != a.kind:
                continue
            for idx, item in slots.items():
                if not item.get("jp"):
                    continue
                old = fixes.get(item["jp"])
                if old and old != (item.get("was"), item["ru"]):
                    print("  расхождение по %r — оставляю первое" % item["jp"][:40])
                    continue
                fixes[item["jp"]] = (item.get("was"), item["ru"])

    out = collections.defaultdict(dict)
    stats = collections.Counter()
    for r in rows:
        pair = fixes.get(r["jp_text"])
        if not pair:
            continue
        was, new = pair
        cur = r.get("ru_text") or ""
        if cur != was:
            if cur and cur != new:
                stats["тот же японский, другой перевод — оставлен"] += 1
            continue
        fname, idx = r["id"].rsplit(":", 1)
        out[fname][idx] = {"jp": r["jp_text"], "was": cur, "ru": new}
        stats["копий к правке"] += 1

    n = sum(len(v) for v in out.values())
    with io.open(a.out, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps({"scene": "prop_" + a.kind, "files": dict(out)},
                            ensure_ascii=False, indent=1))
    print("правил-образцов: %d, копий найдено: %d" % (len(fixes), n))
    for k, v in stats.most_common():
        print("  %-44s %d" % (k, v))
    print("черновик: %s" % os.path.relpath(a.out, ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
