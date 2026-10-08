# -*- coding: utf-8 -*-
"""Строгий фильтр черновиков перед применением к карте перевода.

Черновик — это правки по номерам строк:

    {"scene": "w01", "files": {"script/sys_basemenu.dat": {
        "1078": {"jp": "...", "was": "...", "ru": "..."}}}}

Здесь ничего не записывается в карту. Инструмент читает черновик, сверяет
каждую правку с картой и пишет рядом `<черновик>.ok.json` — только те правки,
которые прошли проверки. Остальные перечисляются с причиной.

Проверки (все — «игра не сломается»):

  * слот существует и `jp` совпадает с картой (защита от съехавших номеров);
  * `was` совпадает с текущим переводом (защита от затирания чужой правки);
  * новый перевод не пустой, если старый был не пустой;
  * состав тегов совпадает со старым переводом (порядок может меняться —
    русская фраза строится иначе, но ни один тег не теряется и не рождается);
  * число `\n` (настоящих переносов), литеральных `\\u3000`, `%s`/`%d`
    и угловых скобок не изменилось;
  * полноширинные буквы и цифры не добавлены.

    python tools/validate_draft.py tools/drafts/rv/w01.json
    python tools/validate_draft.py tools/drafts/rv/*.json --quiet
"""
import argparse
import collections
import glob
import io
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
MAP_FILES = {"table": "tables.jsonl", "script": "scripts.jsonl"}

TAG = re.compile(r"<[^<>]{1,120}>")
RUBY_CLOSE = re.compile(r"</R[^<>]*>")
KW = re.compile(r"^<KW\s+(\S+)\s+(\S+)[^<>]*>$")
FMT = re.compile(r"%[0-9.\-+]*[sdiufxX%]")
FULLW = re.compile(r"[\uff10-\uff19\uff21-\uff3a\uff41-\uff5a]")


def norm_tag(t):
    if RUBY_CLOSE.fullmatch(t):
        return "</R>"
    m = KW.match(t)
    if m:
        return "<KW %s %s>" % (m.group(1), m.group(2))
    return t


def tags(text):
    return collections.Counter(norm_tag(t) for t in TAG.findall(text))


def check(old, new, jp):
    """Причины, по которым правку применять нельзя (пусто — можно)."""
    bad = []
    if new == old:
        bad.append("ничего не изменилось")
        return bad
    if not new.strip() and old.strip():
        return ["новый перевод пустой, а старый нет"]
    if tags(old) != tags(new):
        miss = tags(old) - tags(new)
        extra = tags(new) - tags(old)
        bad.append("теги: нет %r, лишние %r"
                   % (dict(list(miss.items())[:2]), dict(list(extra.items())[:2])))
    if tags(jp) != tags(new) and tags(jp) == tags(old):
        bad.append("теги разошлись с японской строкой")
    for name, rx in (("переносов \\n", r"\n"), ("литеральных u3000", r"\\u3000")):
        if len(re.findall(rx, old)) != len(re.findall(rx, new)):
            bad.append("изменилось число %s" % name)
    if len(FMT.findall(old)) != len(FMT.findall(new)):
        bad.append("изменился состав подстановок %s")
    if old.count("<") != new.count("<"):
        bad.append("изменилось число «<»")
    added = FULLW.findall(new)
    if added and not FULLW.findall(old):
        bad.append("добавлены полноширинные буквы/цифры: %r" % "".join(added[:5]))
    return bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("drafts", nargs="+")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--limit", type=int, default=6)
    a = ap.parse_args()

    maps = {}
    for kind, fname in MAP_FILES.items():
        path = os.path.join(ROOT, "translation_map", fname)
        by_id = {}
        with io.open(path, encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    r = json.loads(line)
                    by_id[r["id"]] = r
        maps[kind] = by_id

    paths = []
    for pat in a.drafts:
        paths.extend(sorted(glob.glob(pat)) or [pat])

    for path in paths:
        try:
            doc = json.load(io.open(path, encoding="utf-8"))
        except Exception as exc:                       # noqa: BLE001
            print("%s: НЕ ЧИТАЕТСЯ — %s" % (os.path.basename(path), exc))
            continue
        ok, notes = {}, collections.Counter()
        samples = collections.defaultdict(list)
        n_in = 0
        for fname, slots in (doc.get("files") or {}).items():
            kind = fname.split("/", 1)[0]
            by_id = maps.get(kind)
            if by_id is None:
                notes["неизвестный вид карты"] += 1
                continue
            for idx, item in slots.items():
                n_in += 1
                rid = "%s:%s" % (fname, int(idx))
                r = by_id.get(rid)
                if r is None:
                    notes["нет такого слота"] += 1
                    if len(samples["нет такого слота"]) < a.limit:
                        samples["нет такого слота"].append(rid)
                    continue
                if isinstance(item, str):
                    item = {"ru": item}
                jp, was, new = item.get("jp"), item.get("was"), item.get("ru")
                if jp is not None and jp != r["jp_text"]:
                    notes["японский текст не совпал"] += 1
                    if len(samples["японский текст не совпал"]) < a.limit:
                        samples["японский текст не совпал"].append(rid)
                    continue
                cur = r.get("ru_text") or ""
                if was is not None and cur != was:
                    notes["перевод уже другой (пропущено)"] += 1
                    if len(samples["перевод уже другой (пропущено)"]) < a.limit:
                        samples["перевод уже другой (пропущено)"].append(rid)
                    continue
                bad = check(cur, new or "", r["jp_text"])
                if bad:
                    notes["нарушена разметка/формат: " + bad[0]] += 1
                    if len(samples["нарушена разметка/формат: " + bad[0]]) < a.limit:
                        samples["нарушена разметка/формат: " + bad[0]].append(
                            "%s | было %r -> станет %r"
                            % (rid, cur[:40], (new or "")[:40]))
                    continue
                ok.setdefault(fname, {})[str(int(idx))] = {
                    "jp": r["jp_text"], "was": cur, "ru": new}
        out = os.path.splitext(path)[0] + ".ok.json"
        n_ok = sum(len(v) for v in ok.values())
        with io.open(out, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps({"scene": doc.get("scene") or "draft",
                                 "files": ok}, ensure_ascii=False, indent=1))
        if not a.quiet or n_in != n_ok:
            print("%s: принято %d из %d -> %s"
                  % (os.path.basename(path), n_ok, n_in,
                     os.path.relpath(out, ROOT)))
            for name, n in notes.most_common():
                print("    отклонено · %-38s %d" % (name, n))
                for s in samples[name][:a.limit]:
                    print("        " + s)


if __name__ == "__main__":
    main()
