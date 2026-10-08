#!/usr/bin/env python3
"""selftest.py — автоматические проверки round-trip для TBL, DAT и PAC.

Смысл: доказать, что цепочки «разобрать -> собрать» возвращают корректный
результат, не теряя данные. Запускается без интерактива, возвращает код 0,
если все запрошенные проверки прошли.

  TBL:  tbl2json -g <игра> <f.tbl> -> json2tbl -> байт-в-байт с оригиналом.
  PAC:  pac_tools unpack -> pac_tools pack -> байт-в-байт с оригиналом.
  DAT:  dat2py (disasm, markers) -> запуск .py -> ПОВТОРНЫЙ dat2py
        пересобранного файла и сравнение двух дизассемблированных .py.
        Совпадение текста означает, что ассемблер восстановил ровно тот же
        код/операнды/строки, что были в оригинале. Побайтовое совпадение .dat
        недостижимо: Falcom раскладывает одинаковые/пустые строки по разным
        ячейкам пула, и адреса ячеек не выводятся из дизассемблированного
        представления. Это безвредно — указатели пересчитываются. Вердикты:
        BYTE_EXACT (совпало и побайтово), SEMANTIC_OK (код идентичен, пул
        разложен иначе — в т.ч. другой размер), CODE_DIFF (реальное расхождение
        кода — баг), ERR_* (сбой).

Использование:
    python selftest.py --tbl <каталог с .tbl> [--game Kyoto]
    python selftest.py --dat <каталог с .dat> [--limit N]
    python selftest.py --pac <file.pac> [--work <каталог>]
    python selftest.py --tbl <dir> --dat <dir> --pac <file>   (всё сразу)

Код возврата 0, если все проверки прошли, иначе 1. Непрошедшие проверки
печатаются в конце.
"""
import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable
ENV = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")


def run(cmd, cwd=None, env=None):
    return subprocess.run(cmd, cwd=cwd, env=env or ENV, capture_output=True,
                          text=True, encoding="utf-8", errors="replace")


def _last_lines(p, n=2):
    txt = (p.stderr or "") + "\n" + (p.stdout or "")
    return [l for l in txt.strip().splitlines() if l.strip()][-n:]


# --------------------------------------------------------------------------- TBL
def check_tbl_dir(directory, game):
    files = sorted(f for f in os.listdir(directory) if f.lower().endswith(".tbl"))
    ok = diff = err = 0
    bad = []
    for f in files:
        src = os.path.abspath(os.path.join(directory, f))
        cmd = [PY, "tbl2json.py", src]
        if game:
            cmd += ["-g", game]
        p1 = run(cmd, cwd=HERE)
        jp = os.path.join(HERE, f[:-4] + ".json")
        if p1.returncode != 0 or not os.path.exists(jp):
            err += 1
            bad.append((f, "tbl2json", _last_lines(p1)))
            continue
        p2 = run([PY, "json2tbl.py", jp], cwd=HERE)
        out = os.path.join(HERE, f)
        if p2.returncode != 0 or not os.path.exists(out):
            err += 1
            bad.append((f, "json2tbl", _last_lines(p2)))
            os.remove(jp)
            continue
        same = open(src, "rb").read() == open(out, "rb").read()
        if same:
            ok += 1
        else:
            diff += 1
            bad.append((f, "DIFF", []))
        os.remove(jp)
        os.remove(out)
    total = len(files)
    print(f"TBL: total={total} ok={ok} diff={diff} err={err} "
          f"exact%={100 * ok / max(1, total):.1f}")
    for f, kind, info in bad[:20]:
        print(f"  {kind} {f} {' '.join(info) if info else ''}")
    return ok, diff, err


# --------------------------------------------------------------------------- PAC
def check_pac(pac_path, work):
    pac_path = os.path.abspath(pac_path)
    tag = os.path.splitext(os.path.basename(pac_path))[0]
    if os.path.isdir(work):
        shutil.rmtree(work)
    os.makedirs(work)
    def _tbl(name):  # noqa: E731
        return os.path.join(HERE, name)
    up = run([PY, _tbl("pac_tools.py"), "unpack", pac_path, work], cwd=HERE)
    if up.returncode != 0:
        print(f"PAC: unpack FAILED for {pac_path}")
        print("\n".join(_last_lines(up, 4)))
        return 0, 0, 1
    repacked = work.rstrip("/\\") + "_repacked.pac"
    # --prefix "" : распаковка сохраняет внутренние имена (table/...), и эталон
    # ссылается на них же, поэтому префикс-имя каталога добавлять не нужно.
    pk = run([PY, _tbl("pac_tools.py"), "pack", work, repacked,
              "--prefix", "", "--reference", pac_path], cwd=HERE)
    if pk.returncode != 0 or not os.path.exists(repacked):
        print(f"PAC: pack FAILED for {pac_path}")
        print("\n".join(_last_lines(pk, 4)))
        return 0, 0, 1
    same = open(pac_path, "rb").read() == open(repacked, "rb").read()
    if same:
        print(f"PAC: {tag} identical=True")
        return 1, 0, 0
    print(f"PAC: {tag} identical=False")
    return 0, 1, 0


# --------------------------------------------------------------------------- DAT
def dat_string_pool(dat_path):
    """Возвращает (start, [строки пула в порядке адресов])."""
    sys.path.insert(0, HERE)
    import disasm.ED9InstructionsSet as I
    from disasm.script import script
    I.smallest_data_ptr = 10 ** 12
    with open(dat_path, "rb") as f:
        script(f, "x", markers=False)
    sp = I.smallest_data_ptr
    d = open(dat_path, "rb").read()
    parts = d[sp:].split(b"\0")[:-1]
    return sp, parts


def check_dat_file(dat_path, scratch):
    # Абсолютный путь обязателен: сгенерированный .py запускается с cwd=scratch,
    # иначе относительный путь к .py удваивается и файл не находится.
    scratch = os.path.abspath(scratch)
    os.makedirs(scratch, exist_ok=True)
    stem = os.path.splitext(os.path.basename(dat_path))[0]
    env = dict(ENV, PYTHONPATH=HERE + os.pathsep + ENV.get("PYTHONPATH", ""))
    p1 = run([PY, os.path.join(HERE, "dat2py.py"), "--decompile", "False",
              "--markers", "True", os.path.abspath(dat_path)], cwd=scratch, env=env)
    py = os.path.join(scratch, stem + ".py")
    if p1.returncode != 0 or not os.path.exists(py):
        return "ERR_DISASM", _last_lines(p1)
    py_text = open(py, encoding="utf-8", errors="replace").read()
    p2 = run([PY, py], cwd=scratch, env=env)
    out = os.path.join(scratch, stem + ".dat")
    if p2.returncode != 0 or not os.path.exists(out):
        return "ERR_ASM", _last_lines(p2)
    a = open(dat_path, "rb").read()
    b = open(out, "rb").read()
    # Повторный дизассемблер пересобранного файла — в отдельный каталог,
    # чтобы не перезаписать уже прочитанный .py.
    re_dir = os.path.join(scratch, "recheck")
    os.makedirs(re_dir, exist_ok=True)
    p3 = run([PY, os.path.join(HERE, "dat2py.py"), "--decompile", "False",
              "--markers", "True", out], cwd=re_dir, env=env)
    py2 = os.path.join(re_dir, stem + ".py")
    if p3.returncode != 0 or not os.path.exists(py2):
        return "ERR_DISASM2", _last_lines(p3)
    py2_text = open(py2, encoding="utf-8", errors="replace").read()
    if py_text != py2_text:
        lo, ln = py_text.splitlines(), py2_text.splitlines()
        for i in range(max(len(lo), len(ln))):
            x = lo[i] if i < len(lo) else "<eof>"
            y = ln[i] if i < len(ln) else "<eof>"
            if x != y:
                return "CODE_DIFF", [f"line {i + 1}: {x.strip()!r} != {y.strip()!r}"]
        return "CODE_DIFF", []
    if a == b:
        return "BYTE_EXACT", []
    if len(a) != len(b):
        return "SEMANTIC_OK_SIZE", [f"size {len(a)}->{len(b)}"]
    return "SEMANTIC_OK", []


def check_dat_dir(directory, limit, work):
    files = []
    for r, _, fs in os.walk(directory):
        files += [os.path.join(r, f) for f in fs if f.lower().endswith(".dat")]
    files.sort()
    if limit:
        files = files[:limit]
    scratch_root = os.path.join(work, "dat_scratch")
    counts = Counter()
    bad = []
    for i, f in enumerate(files):
        st, info = check_dat_file(f, os.path.join(scratch_root,
                                os.path.splitext(os.path.basename(f))[0]))
        counts[st] += 1
        if st not in ("BYTE_EXACT", "SEMANTIC_OK", "SEMANTIC_OK_SIZE"):
            bad.append((f, st, info))
        if (i + 1) % 25 == 0:
            print(f"  ...{i + 1}/{len(files)} {dict(counts)}", flush=True)
    total = len(files)
    semantic = counts["BYTE_EXACT"] + counts["SEMANTIC_OK"] + counts["SEMANTIC_OK_SIZE"]
    err = (counts["ERR_DISASM"] + counts["ERR_ASM"]
           + counts["ERR_DISASM2"])
    print(f"DAT: total={total} semantic_ok={semantic} byte_exact={counts['BYTE_EXACT']} "
          f"size_changed={counts['SEMANTIC_OK_SIZE']} code_diff={counts['CODE_DIFF']} "
          f"err={err}")
    for f, st, info in bad[:20]:
        print(f"  {st} {os.path.basename(f)} {' '.join(info) if info else ''}")
    # Для .dat «прошли» = код восстановлен семантически точно (байтовое
    # равенство — бонус, размер может отличаться из-за раскладки пула).
    return semantic, total - semantic


def main():
    ap = argparse.ArgumentParser(description="Автопроверки round-trip TBL/DAT/PAC.")
    ap.add_argument("--tbl", metavar="DIR", help="каталог с .tbl")
    ap.add_argument("--game", default="Kyoto", help="игра для схем (по умолчанию Kyoto)")
    ap.add_argument("--dat", metavar="DIR", help="каталог с .dat")
    ap.add_argument("--limit", type=int, default=0, help="ограничить число .dat")
    ap.add_argument("--pac", metavar="FILE", help="файл .pac")
    ap.add_argument("--work", default=None, help="рабочий каталог для временных файлов")
    args = ap.parse_args()

    if not (args.tbl or args.dat or args.pac):
        ap.error("укажите хотя бы один из --tbl / --dat / --pac")

    work = args.work or tempfile.mkdtemp(prefix="kuro_selftest_")
    os.makedirs(work, exist_ok=True)
    failed = 0

    if args.tbl:
        ok, diff, err = check_tbl_dir(args.tbl, args.game)
        failed += diff + err
    if args.dat:
        d_ok, d_bad = check_dat_dir(args.dat, args.limit, work)
        failed += d_bad
    if args.pac:
        p_ok, p_diff, p_err = check_pac(args.pac, os.path.join(work, "pac"))
        failed += p_diff + p_err

    print(f"\nИТОГО: {'all checks passed' if failed == 0 else str(failed) + ' failed'}")
    if not args.work:
        shutil.rmtree(work, ignore_errors=True)
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
