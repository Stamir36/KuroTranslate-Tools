#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
FontBuilder.pyw - окно для сборки шрифтов Kuro no Kiseki из TTF.

Что делает: выбираете TTF для font_0 и (при желании другой) для font_1, жмёте
"Собрать" - программа растеризует латиницу, цифры, кириллицу и пунктуацию в
размер самого шрифта игры, вписывает глифы в атлас (BC7 .dds) и пересчитывает
метрики (.fnt). Иероглифы не трогаются: соответствующие блоки атласа остаются
байт-в-байт как в игре.

Никаких настроек в файлах не нужно: программа сама находит базовые (игровые)
font_0/1.fnt и font_0/1.dds - сначала рядом с собой в "Original Files Game",
затем в папке игры, которую вы укажете. Всё остальное (папка вывода, превью,
отчёт) подставляется автоматически.

Запуск: двойной клик по этому файлу (.pyw - окно без чёрной консоли).
Проверить без окна:  python FontBuilder.pyw --selfcheck
Собрать из командной строки: python FontBuilder.pyw --cli --ttf0 A.ttf --ttf1 B.ttf
"""

from __future__ import annotations

import json
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.join(HERE, "tools")
CONFIG = os.path.join(HERE, "FontBuilder.json")
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

# --------------------------------------------------------------------- зависимости

MISSING = []
try:
    import numpy  # noqa: F401
except Exception:
    MISSING.append("numpy")
try:
    from PIL import Image, ImageTk  # noqa: F401
except Exception:
    MISSING.append("pillow")
try:
    import texture2ddecoder  # noqa: F401
except Exception:
    MISSING.append("texture2ddecoder")
try:
    import fontTools  # noqa: F401
    HAVE_FONTTOOLS = True
except Exception:
    HAVE_FONTTOOLS = False
try:
    import customtkinter as ctk
    USING_CTK = True
except Exception:
    ctk = None
    USING_CTK = False

import tkinter as tk
from tkinter import filedialog, messagebox

# ------------------------------------------------------------------ виджеты-фасад
# customtkinter есть - используем его; нет - обычный tkinter/ttk (без зависимостей).

FONT_UI = ("Segoe UI", 12)
FONT_BOLD = ("Segoe UI", 12, "bold")
FONT_SMALL = ("Segoe UI", 10)
FONT_MONO = ("Consolas", 10)


def Pane(parent, **kw):
    if USING_CTK:
        return ctk.CTkFrame(parent, corner_radius=8, **kw)
    return tk.Frame(parent, bd=1, relief="groove", **kw)


def Lbl(parent, text="", bold=False, small=False, **kw):
    f = FONT_BOLD if bold else (FONT_SMALL if small else FONT_UI)
    if USING_CTK:
        return ctk.CTkLabel(parent, text=text, font=f, **kw)
    return tk.Label(parent, text=text, font=f, **kw)


def Ent(parent, textvariable=None, width=58, **kw):
    if USING_CTK:
        return ctk.CTkEntry(parent, textvariable=textvariable, width=width * 7, **kw)
    return tk.Entry(parent, textvariable=textvariable, width=width, font=FONT_UI, **kw)


def Btn(parent, text, command, width=150, **kw):
    if USING_CTK:
        return ctk.CTkButton(parent, text=text, command=command,
                             width=width, font=FONT_UI, **kw)
    return tk.Button(parent, text=text, command=command, font=FONT_UI, width=width // 7, **kw)


def Chk(parent, text, variable, **kw):
    if USING_CTK:
        return ctk.CTkCheckBox(parent, text=text, variable=variable, font=FONT_UI, **kw)
    return tk.Checkbutton(parent, text=text, variable=variable, font=FONT_UI, **kw)


def Box(parent, height=12, **kw):
    if USING_CTK:
        return ctk.CTkTextbox(parent, height=height * 18, font=FONT_MONO, **kw)
    t = tk.Text(parent, height=height, font=FONT_MONO, wrap="none", **kw)
    return t


def Bar(parent, **kw):
    if USING_CTK:
        return ctk.CTkProgressBar(parent, **kw)
    from tkinter import ttk
    return ttk.Progressbar(parent, mode="determinate", maximum=100, **kw)


def bar_set(bar, value):
    """value: 0..1"""
    if USING_CTK:
        bar.set(value)
    else:
        bar["value"] = value * 100


def box_clear(box):
    if USING_CTK:
        box.delete("1.0", "end")
    else:
        box.delete("1.0", "end")


def box_write(box, text):
    box.insert("end", text)
    box.see("end")


# ------------------------------------------------------------------------ конфиг

DEFAULTS = {
    "game_asset": "",          # папка <игра>\asset, если пользователь её выбрал
    "ttf0": "",
    "ttf1": "",
    "out": os.path.join(HERE, "gotovoe"),
    "add_missing": True,
    "select": "latin,cyr,punct",
    "pad": 1,
    "tracking": 0,
    "size0": "",               # пусто = размер как в игре
    "size1": "",
}


def load_config() -> dict:
    cfg = dict(DEFAULTS)
    try:
        with open(CONFIG, encoding="utf-8") as fh:
            cfg.update(json.load(fh))
    except Exception:
        pass
    return cfg


def save_config(cfg: dict) -> None:
    try:
        with open(CONFIG, "w", encoding="utf-8") as fh:
            json.dump(cfg, fh, ensure_ascii=False, indent=2)
    except Exception:
        pass


# ------------------------------------------------------- поиск базовых игровых файлов

BASE_LAYOUT = {
    "fnt0": os.path.join("common", "font", "font_0.fnt"),
    "fnt1": os.path.join("common", "font", "font_1.fnt"),
    "dds0": os.path.join("dx11", "image", "font_0.dds"),
    "dds1": os.path.join("dx11", "image", "font_1.dds"),
}


def base_files(asset_dir: str):
    """asset_dir -> словарь четырёх путей (или {} если это не папка asset игры)."""
    if not asset_dir:
        return {}
    out = {k: os.path.join(asset_dir, v) for k, v in BASE_LAYOUT.items()}
    return out if all(os.path.exists(p) for p in out.values()) else {}


def looks_like_asset(path: str) -> bool:
    return bool(base_files(path))


def autodetect_base() -> str:
    """Ищем базовую папку 'asset' сами, без настроек."""
    cands = [
        os.path.join(HERE, "Original Files Game", "asset"),
        os.path.join(HERE, "asset"),
    ]
    # папка игры целиком: <игра>\asset
    for up in (HERE, os.path.dirname(HERE)):
        cands.append(os.path.join(up, "asset"))
    for c in cands:
        if looks_like_asset(c):
            return c
    return ""


def find_ttf_folders():
    """Откуда начинать диалог выбора TTF."""
    out = [HERE]
    win = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
    if os.path.isdir(win):
        out.append(win)
    return out


# ------------------------------------------------------------------ покрытие TTF

def font_family(path: str) -> str:
    try:
        from PIL import ImageFont
        return ImageFont.truetype(path, 20).getname()[0]
    except Exception:
        return os.path.basename(path)


def missing_chars(ttf: str, codes) -> list:
    """Каких нужных символов нет в шрифте (по cmap). Нужен fontTools."""
    if not HAVE_FONTTOOLS:
        return []
    try:
        from fontTools.ttLib import TTFont
        f = TTFont(ttf, fontNumber=0, lazy=True)
        have = set()
        for t in f["cmap"].tables:
            have.update(t.cmap.keys())
        return [c for c in codes if c not in have]
    except Exception:
        return []


# ------------------------------------------------------------------ сборка шрифта

def run_build(ttf: str, base: dict, which: int, out_root: str, select: str,
              size, pad: int, tracking: int, add_missing: bool, log) -> int:
    """Собрать один шрифт через tools/ttf_to_font.py. Возвращает код возврата."""
    import ttf_to_font

    n = which
    # результат ложим в готовую папку asset - её же структуру ждёт игра:
    # <папка игры>\asset\common\font\... и \dx11\image\...
    tree = os.path.join(out_root, "asset")
    out_fnt = os.path.join(tree, "common", "font", "font_%d.fnt" % n)
    out_dds = os.path.join(tree, "dx11", "image", "font_%d.dds" % n)
    preview = os.path.join(out_root, "preview_font_%d.png" % n)
    report = os.path.join(out_root, "otchet_font_%d.txt" % n)
    os.makedirs(os.path.dirname(out_fnt), exist_ok=True)
    os.makedirs(os.path.dirname(out_dds), exist_ok=True)

    argv = ["--fnt", base["fnt%d" % n], "--dds", base["dds%d" % n], "--ttf", ttf,
            "--select", select, "--pad", str(pad), "--tracking", str(tracking),
            "--out-fnt", out_fnt, "--out-dds", out_dds,
            "--out-preview", preview, "--report", report]
    if size:
        argv += ["--size", str(size)]
    if add_missing:
        argv += ["--add-missing"]
    log("$ ttf_to_font.py " + " ".join(argv))
    rc = ttf_to_font.main(argv)
    log("код возврата: %d" % rc)
    return rc


class TextSink:
    """Подменяет stdout: все строки инструмента уходят в окно."""

    def __init__(self, log):
        self.log = log
        self.buf = ""

    def write(self, s):
        self.buf += s
        while "\n" in self.buf:
            line, self.buf = self.buf.split("\n", 1)
            self.log(line.rstrip("\r"))

    def flush(self):
        if self.buf:
            self.log(self.buf.rstrip("\r"))
            self.buf = ""


def install_into_game(asset_dir: str, out_root: str, log) -> int:
    """Скопировать готовые 4 файла в <игра>\\asset, сделав бэкап старых."""
    pairs = [("common/font/font_0.fnt", "fnt0"), ("common/font/font_1.fnt", "fnt1"),
             ("dx11/image/font_0.dds", "dds0"), ("dx11/image/font_1.dds", "dds1")]
    stamp = time.strftime("%Y%m%d-%H%M%S")
    backup = os.path.join(asset_dir, "_backup_shrift_" + stamp)
    os.makedirs(backup, exist_ok=True)
    copied = 0
    for rel, _key in pairs:
        src = os.path.join(out_root, "asset", rel.replace("/", os.sep))
        dst = os.path.join(asset_dir, rel.replace("/", os.sep))
        if not os.path.exists(src):
            log("НЕТ ФАЙЛА: %s" % src)
            continue
        if os.path.exists(dst):
            os.makedirs(os.path.dirname(os.path.join(backup, rel.replace("/", os.sep))),
                        exist_ok=True)
            shutil.copy2(dst, os.path.join(backup, rel.replace("/", os.sep)))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)
        log("скопировано: %s" % dst)
        copied += 1
    log("бэкап старых файлов: %s" % backup)
    return copied


# ---------------------------------------------------------------------------- UI

TITLE = "Сборка шрифтов Kuro no Kiseki"


class App:
    def __init__(self, root):
        self.root = root
        self.cfg = load_config()
        self.log_q = queue.Queue()
        self.busy = False
        self.photo = None          # держим ссылку на картинку превью
        self.rc = [None, None]
        root.title(TITLE)
        root.geometry("1200x930")
        root.minsize(1000, 780)

        self.v_base = tk.StringVar(value=self.cfg.get("game_asset") or autodetect_base())
        self.v_ttf0 = tk.StringVar(value=self.cfg.get("ttf0") or self._guess_ttf())
        self.v_ttf1 = tk.StringVar(value=self.cfg.get("ttf1") or "")
        self.v_same = tk.BooleanVar(value=not bool(self.cfg.get("ttf1")))
        self.v_out = tk.StringVar(value=self.cfg.get("out") or os.path.join(HERE, "gotovoe"))
        self.v_size0 = tk.StringVar(value=self.cfg.get("size0") or "")
        self.v_size1 = tk.StringVar(value=self.cfg.get("size1") or "")
        self.v_add = tk.BooleanVar(value=bool(self.cfg.get("add_missing", True)))
        self.v_select = tk.StringVar(value=self.cfg.get("select", "latin,cyr,punct"))
        self.v_pad = tk.StringVar(value=str(self.cfg.get("pad", 1)))
        self.v_track = tk.StringVar(value=str(self.cfg.get("tracking", 0)))
        self.v_preview = tk.IntVar(value=0)

        self._layout()
        for v in (self.v_base, self.v_ttf0, self.v_ttf1, self.v_same):
            v.trace_add("write", lambda *a: self.refresh_status())
        self.refresh_status()
        self.root.after(120, self._poll)

    # ------------------------------------------------------------- мелкие помощники
    def _guess_ttf(self):
        for name in ("ProductSans.ttf", "assets/ProductSans.ttf"):
            p = os.path.join(HERE, name)
            if os.path.exists(p):
                return p
        return ""

    def _row(self, parent, r=0):
        f = tk.Frame(parent) if not USING_CTK else ctk.CTkFrame(parent)
        f.pack(fill="x", padx=10, pady=(8, 0))
        return f

    def _layout(self):
        head = Pane(self.root)
        head.pack(fill="x", padx=12, pady=(12, 0))
        Lbl(head, text=TITLE, bold=True).pack(anchor="w", padx=12, pady=(8, 0))
        Lbl(head, text="Пишите TTF слева - программа собирает .dds + .fnt. Иероглифы в атласе "
                       "останутся байт-в-байт игровыми.", small=True).pack(anchor="w", padx=12, pady=(0, 8))

        # --- 1. базовые (игровые) файлы ---
        p = Pane(self.root)
        p.pack(fill="x", padx=12, pady=(10, 0))
        Lbl(p, text="1. Игровые файлы-основа (откуда берутся .fnt/.dds)", bold=True).pack(
            anchor="w", padx=12, pady=(8, 2))
        r = self._row(p)
        Lbl(r, text="Папка asset игры:").pack(side="left")
        Ent(r, self.v_base).pack(side="left", padx=8)
        Btn(r, "Обзор…", self.on_browse_base, width=110).pack(side="left")
        Btn(r, "Взять «Original Files Game»", self.on_use_original, width=250).pack(side="left", padx=8)
        self.l_base = Lbl(p, text="", small=True)
        self.l_base.pack(anchor="w", padx=12, pady=(4, 8))

        # --- 2. шрифты ---
        p2 = Pane(self.root)
        p2.pack(fill="x", padx=12, pady=(10, 0))
        Lbl(p2, text="2. Шрифты TTF", bold=True).pack(anchor="w", padx=12, pady=(8, 2))

        r = self._row(p2)
        Lbl(r, text="font_0 (основной):").pack(side="left")
        Ent(r, self.v_ttf0).pack(side="left", padx=8)
        Btn(r, "Обзор…", lambda: self.on_browse_ttf(0), width=110).pack(side="left")
        Lbl(r, text="размер:").pack(side="left", padx=(12, 2))
        Ent(r, self.v_size0, width=6).pack(side="left")
        self.l_ttf0 = Lbl(p2, text="", small=True)
        self.l_ttf0.pack(anchor="w", padx=12, pady=(4, 6))

        r = self._row(p2)
        Lbl(r, text="font_1 (второй):").pack(side="left")
        self.e_ttf1 = Ent(r, self.v_ttf1)
        self.e_ttf1.pack(side="left", padx=8)
        self.b_ttf1 = Btn(r, "Обзор…", lambda: self.on_browse_ttf(1), width=110)
        self.b_ttf1.pack(side="left")
        Lbl(r, text="размер:").pack(side="left", padx=(12, 2))
        Ent(r, self.v_size1, width=6).pack(side="left")
        r2 = self._row(p2)
        Chk(r2, "тот же шрифт, что и font_0", self.v_same, command=self.refresh_status).pack(side="left")
        self.l_ttf1 = Lbl(p2, text="", small=True)
        self.l_ttf1.pack(anchor="w", padx=12, pady=(4, 8))

        # --- 3. опции ---
        p3 = Pane(self.root)
        p3.pack(fill="x", padx=12, pady=(10, 0))
        Lbl(p3, text="3. Что перерисовывать и как", bold=True).pack(anchor="w", padx=12, pady=(8, 2))
        r = self._row(p3)
        Lbl(r, text="символы:").pack(side="left")
        Ent(r, self.v_select, width=34).pack(side="left", padx=6)
        Chk(r, "добавить отсутствующие (— – « » №)", self.v_add).pack(side="left", padx=10)
        r = self._row(p3)
        Lbl(r, text="прозрачная рамка:").pack(side="left")
        Ent(r, self.v_pad, width=6).pack(side="left", padx=6)
        Lbl(r, text="межбуквенный интервал:").pack(side="left", padx=(14, 0))
        Ent(r, self.v_track, width=6).pack(side="left", padx=6)
        Lbl(r, text="размер пустой = как в игре (49/50)", small=True).pack(side="left", padx=10)
        r = self._row(p3)
        Lbl(r, text="папка результата:").pack(side="left")
        Ent(r, self.v_out).pack(side="left", padx=8)
        Btn(r, "Сменить…", self.on_browse_out, width=110).pack(side="left")
        Lbl(p3, text="", small=True).pack(pady=(0, 6))

        # --- 4. кнопки ---
        p4 = Pane(self.root)
        p4.pack(fill="x", padx=12, pady=(10, 0))
        r = self._row(p4)
        self.b_build = Btn(r, "Собрать шрифты", self.on_build, width=200)
        self.b_build.pack(side="left")
        Btn(r, "Открыть папку результата", self.on_open_out, width=210).pack(side="left", padx=8)
        self.b_install = Btn(r, "Установить в игру…", self.on_install, width=190)
        self.b_install.pack(side="left")
        self.bar = Bar(p4)
        self.bar.pack(fill="x", padx=12, pady=(6, 10))
        bar_set(self.bar, 0)

        # --- 5. лог и превью ---
        p5 = Pane(self.root)
        p5.pack(fill="both", expand=True, padx=12, pady=(10, 12))
        r = self._row(p5)
        Lbl(r, text="Журнал", bold=True).pack(side="left")
        Btn(r, "Очистить", self.on_clear_log, width=110).pack(side="right")
        Btn(r, "Показать превью font_1", lambda: self.show_preview(1), width=190).pack(side="right", padx=6)
        Btn(r, "Показать превью font_0", lambda: self.show_preview(0), width=190).pack(side="right")
        self.log = Box(p5, height=11)
        self.log.pack(fill="both", expand=True, padx=12, pady=(6, 8))
        self.preview = Lbl(p5, text="", small=True)
        self.preview.pack(fill="x", padx=12, pady=(0, 10))

    # ------------------------------------------------------------- проверки полей
    def _base(self) -> dict:
        d = self.v_base.get().strip()
        b = base_files(d)
        if b:
            return b
        return base_files(os.path.join(d, "asset"))       # дали папку игры целиком

    def _require(self):
        """(ttf0, ttf1, base, ошибка) - всё проверено до старта сборки."""
        base = self._base()
        if not base:
            return None, None, None, ("Не найдены игровые файлы-основа.\n\n"
                                      "Укажите папку <игра>\\asset (в ней должны лежать "
                                      "common\\font\\font_0.fnt и dx11\\image\\font_0.dds), "
                                      "либо нажмите «Взять Original Files Game».")
        ttf0 = self.v_ttf0.get().strip()
        if not ttf0 or not os.path.exists(ttf0):
            return None, None, None, "Выберите TTF для font_0 (файл не найден)."
        ttf1 = ttf0 if self.v_same.get() or not self.v_ttf1.get().strip() else self.v_ttf1.get().strip()
        if not os.path.exists(ttf1):
            return None, None, None, "Файл TTF для font_1 не найден."
        return ttf0, ttf1, base, None

    def _int(self, var, fallback, name, lo=-64, hi=200):
        s = str(var.get()).strip()
        if not s:
            return fallback, None
        try:
            v = int(s)
        except ValueError:
            return fallback, "%s: не число (%r)" % (name, s)
        if not (lo <= v <= hi):
            return fallback, "%s: допустимо %d..%d" % (name, lo, hi)
        return v, None

    def refresh_status(self):
        base = self._base()
        self.l_base.configure(
            text="✓ найдены: font_0/1.fnt + font_0/1.dds" if base else
                 "не найдены — укажите папку <игра>\\asset или возьмите Original Files Game",
            text_color="#2e7d32" if base else "#c62828")

        same = self.v_same.get()
        self.e_ttf1.configure(state="disabled" if same else "normal")
        self.b_ttf1.configure(state="disabled" if same else "normal")

        codes = None
        try:
            from ttf_to_font import parse_selection
            codes = [c for c in parse_selection(self.v_select.get())
                     if c not in (0x200B, 0x200C, 0x200D, 0x200E, 0x200F)]
        except Exception as exc:
            self.l_ttf0.configure(text="не удалось прочитать настройку символов: %s" % exc)
            self.l_ttf1.configure(text="")
            return

        for i, lab in ((0, self.l_ttf0), (1, self.l_ttf1)):
            path = self.v_ttf0.get().strip() if (i == 0 or same) else self.v_ttf1.get().strip()
            if not path or not os.path.exists(path):
                lab.configure(text="TTF не выбран" + (" (используется шрифт font_0)" if i == 1 and same else ""),
                              text_color="#c62828")
                continue
            miss = missing_chars(path, codes) if HAVE_FONTTOOLS else []
            cyr = sum(1 for c in codes if 0x400 <= c <= 0x4FF and c not in miss)
            cyr_all = sum(1 for c in codes if 0x400 <= c <= 0x4FF)
            txt = "%s · кириллица %d/%d" % (font_family(path), cyr, cyr_all)
            color = "#2e7d32"
            if miss:
                txt += " · нет %d: %s" % (len(miss), "".join(chr(c) for c in miss[:24]))
                color = "#ef6c00"
            lab.configure(text=txt, text_color=color)

    # ------------------------------------------------------------------- обзоры
    def on_browse_base(self):
        d = filedialog.askdirectory(title="Папка asset игры (или папка игры целиком)")
        if d:
            self.v_base.set(d)
            self.log_q.put("базовая папка: " + d)

    def on_use_original(self):
        p = os.path.join(HERE, "Original Files Game", "asset")
        if looks_like_asset(p):
            self.v_base.set(p)
            self.log_q.put("базовая папка: " + p)
        else:
            messagebox.showerror(TITLE, "Не найдена папка:\n%s" % p)

    def on_browse_ttf(self, which):
        f = filedialog.askopenfilename(title="Выберите шрифт (TTF/OTF/TTC)",
                                       initialdir=find_ttf_folders()[0],
                                       filetypes=[("Шрифты", "*.ttf *.otf *.ttc"),
                                                  ("Все файлы", "*.*")])
        if f:
            (self.v_ttf0 if which == 0 else self.v_ttf1).set(f)

    def on_browse_out(self):
        d = filedialog.askdirectory(title="Куда складывать готовые файлы")
        if d:
            self.v_out.set(d)

    def on_open_out(self):
        d = self.v_out.get().strip()
        if os.path.isdir(d):
            try:
                os.startfile(d)          # только Windows
            except Exception:
                subprocess.Popen(["explorer", d])
        else:
            messagebox.showinfo(TITLE, "Папки ещё нет:\n%s" % d)

    def on_clear_log(self):
        box_clear(self.log)

    # --------------------------------------------------------------------- лог
    def _drain(self):
        """Очередь не только для лога: строки 'progress N' и 'show I' - команды окну."""
        while True:
            try:
                line = self.log_q.get_nowait()
            except queue.Empty:
                return
            if line.startswith("progress "):
                try:
                    bar_set(self.bar, float(line.split()[1]))
                except Exception:
                    pass
                continue
            if line.startswith("show "):
                try:
                    i = int(line.split()[1])
                except Exception:
                    i = -1
                self.busy = False
                self.b_build.configure(state="normal")
                self.b_install.configure(state="normal")
                if i >= 0:
                    self.show_preview(i)
                continue
            box_write(self.log, line + "\n")

    def _poll(self):
        self._drain()
        self.root.after(120, self._poll)

    # ------------------------------------------------------------------ сборка
    def _save_cfg(self):
        self.cfg.update({
            "game_asset": self.v_base.get().strip(),
            "ttf0": self.v_ttf0.get().strip(),
            "ttf1": "" if self.v_same.get() else self.v_ttf1.get().strip(),
            "out": self.v_out.get().strip(),
            "size0": self.v_size0.get().strip(),
            "size1": self.v_size1.get().strip(),
            "add_missing": bool(self.v_add.get()),
            "select": self.v_select.get().strip(),
        })
        for key, var in (("pad", self.v_pad), ("tracking", self.v_track)):
            v, _e = self._int(var, 0, key)
            self.cfg[key] = v
        save_config(self.cfg)

    def on_build(self):
        if self.busy:
            return
        ttf0, ttf1, base, err = self._require()
        if err:
            messagebox.showerror(TITLE, err)
            return
        pad, e1 = self._int(self.v_pad, 1, "прозрачная рамка", 0, 8)
        track, e2 = self._int(self.v_track, 0, "интервал", -8, 20)
        s0, e3 = self._int(self.v_size0, None, "размер font_0", 6, 200)
        s1, e4 = self._int(self.v_size1, None, "размер font_1", 6, 200)
        for e in (e1, e2, e3, e4):
            if e:
                messagebox.showerror(TITLE, e)
                return
        self._save_cfg()
        self.busy = True
        self.b_build.configure(state="disabled")
        self.b_install.configure(state="disabled")
        bar_set(self.bar, 0.02)
        self.log_q.put("")
        self.log_q.put("=== сборка: %s" % time.strftime("%H:%M:%S"))
        args = dict(base=base, out=self.v_out.get().strip(), select=self.v_select.get().strip(),
                    pad=pad, track=track, add=bool(self.v_add.get()),
                    sizes=(s0, s1), ttfs=(ttf0, ttf1))
        threading.Thread(target=self._worker, args=(args,), daemon=True).start()

    def _worker(self, a):
        sink = TextSink(self.log_q.put)
        old, old_err = sys.stdout, sys.stderr
        rc = [1, 1]
        try:
            sys.stdout = sys.stderr = sink
            for i, ttf in enumerate(a["ttfs"]):
                self.log_q.put("--- font_%d: %s" % (i, ttf))
                try:
                    rc[i] = run_build(ttf, a["base"], i, a["out"], a["select"],
                                      a["sizes"][i], a["pad"], a["track"], a["add"],
                                      self.log_q.put)
                except Exception:
                    self.log_q.put(traceback.format_exc())
                    rc[i] = 1
                sink.flush()
                self.log_q.put("progress %.1f" % (0.5 * (i + 1)))
            ok = [i for i in (0, 1) if rc[i] == 0]
            self.log_q.put("=== готово, успешно: %s; ошибки: %s"
                           % (", ".join("font_%d" % i for i in ok) or "нет",
                              ", ".join("font_%d" % i for i in (0, 1) if rc[i] != 0) or "нет"))
            self.log_q.put("progress 1.0")
            self.log_q.put("show %d" % (ok[0] if ok else -1))
        finally:
            sys.stdout, sys.stderr = old, old_err

    # --------------------------------------------------------------- превью
    def show_preview(self, i):
        if i < 0:
            return
        path = os.path.join(self.v_out.get().strip(), "preview_font_%d.png" % i)
        if not os.path.exists(path):
            box_write(self.log, "превью не найдено: %s\n" % path)
            return
        img = Image.open(path)
        scale = min(1.0, 1080.0 / img.width)
        if scale < 1.0:
            img = img.resize((int(img.width * scale), int(img.height * scale)), Image.LANCZOS)
        if USING_CTK:
            self.photo = ctk.CTkImage(light_image=img, size=(img.width, img.height))
            self.preview.configure(image=self.photo, text="")
        else:
            self.photo = ImageTk.PhotoImage(img)
            self.preview.configure(image=self.photo, text="")

    # --------------------------------------------------------------- установка
    def on_install(self):
        out = self.v_out.get().strip()
        need = [os.path.join(out, "asset", "common", "font", "font_0.fnt"),
                os.path.join(out, "asset", "common", "font", "font_1.fnt"),
                os.path.join(out, "asset", "dx11", "image", "font_0.dds"),
                os.path.join(out, "asset", "dx11", "image", "font_1.dds")]
        if not all(os.path.exists(p) for p in need):
            messagebox.showinfo(TITLE, "Сначала нажмите «Собрать шрифты».")
            return
        d = filedialog.askdirectory(title="Папка asset игры (та, куда ставим шрифт)")
        if not d:
            return
        asset = d if looks_like_asset(d) else os.path.join(d, "asset")
        if not looks_like_asset(asset):
            if not messagebox.askyesno(TITLE, "В папке не видно игровых font_0.fnt/font_0.dds:\n%s\n\n"
                                             "Всё равно скопировать 4 файла туда?" % asset):
                return
        if not messagebox.askyesno(TITLE, "Скопировать 4 файла в:\n%s\n\n"
                                         "Старые файлы будут сохранены в подпапку _backup_shrift_*." % asset):
            return
        try:
            n = install_into_game(asset, out, self.log_q.put)
        except Exception:
            self.log_q.put(traceback.format_exc())
            n = 0
        self.log_q.put("=== установлено файлов: %d" % n)
        if n:
            messagebox.showinfo(TITLE, "Готово: %d файла(ов) скопированы в игру.\n"
                                        "Можно запускать игру." % n)

    # ---- main ----


def _root():
    if USING_CTK:
        ctk.set_appearance_mode("system")
        ctk.set_default_color_theme("blue")
        return ctk.CTk()
    return tk.Tk()


def selfcheck() -> int:
    """Без mainloop: строится ли окно, находятся ли файлы, читается ли покрытие TTF."""
    print("customtkinter: %s" % ("есть" if USING_CTK else "нет, используется tkinter"))
    print("нет библиотек: %s" % (", ".join(MISSING) or "—"))
    print("fontTools: %s" % ("есть" if HAVE_FONTTOOLS else "нет"))
    base = autodetect_base()
    print("базовая папка найдена автоматически: %s" % (base or "НЕ НАЙДЕНА"))
    if not base:
        return 1
    ok = True
    try:
        root = _root()
    except Exception as exc:
        print("не удалось создать окно: %s" % exc)
        return 1
    try:
        app = App(root)
        for _ in range(5):
            root.update()
        print("окно построено; база в окне: %s" % (app.v_base.get() or "пусто"))
        ttf0, ttf1, b, err = app._require()
        print("_require: %s" % (err or "ok, font_0=%s font_1=%s" % (os.path.basename(ttf0),
                                                               os.path.basename(ttf1))))
        print("статус font_0: %s" % app.l_ttf0.cget("text"))
        print("статус font_1: %s" % app.l_ttf1.cget("text"))
        ok = err is None

        # проверяем очередь окна: "progress N" и "show I" - это команды, а не лог
        app.log_q.put("progress 0.5")
        app.log_q.put("строка журнала")
        app.log_q.put("show -1")
        app._drain()
        root.update()
        print("после _drain: busy=%s, кнопка сборки=%s, в журнале есть строка: %s"
              % (app.busy, app.b_build.cget("state"),
                 "строка журнала" in app.log.get("1.0", "end")))
        if app.busy or "строка журнала" not in app.log.get("1.0", "end"):
            ok = False
    except Exception:
        traceback.print_exc()
        ok = False
    finally:
        root.destroy()
    return 0 if ok else 1


def cli(argv) -> int:
    """То же самое без окна: python FontBuilder.pyw --cli --ttf0 A.ttf --ttf1 B.ttf"""
    import argparse
    ap = argparse.ArgumentParser(description="Сборка шрифтов из TTF без окна")
    ap.add_argument("--base", default=None, help="папка <игра>\\asset (по умолчанию - авто"
                                                  "поиск Original Files Game)")
    ap.add_argument("--ttf0", required=True)
    ap.add_argument("--ttf1", default=None, help="по умолчанию - тот же, что --ttf0")
    ap.add_argument("--out", default=os.path.join(HERE, "gotovoe"))
    ap.add_argument("--size0", type=int, default=None)
    ap.add_argument("--size1", type=int, default=None)
    ap.add_argument("--pad", type=int, default=1)
    ap.add_argument("--tracking", type=int, default=0)
    ap.add_argument("--select", default="latin,cyr,punct")
    ap.add_argument("--no-add", action="store_true")
    a = ap.parse_args([x for x in argv if x != "--cli"])
    b = base_files(a.base) if a.base else base_files(autodetect_base())
    if not b:
        print("не найдены игровые файлы-основа (--base)")
        return 2
    rc = 0
    for i, ttf in enumerate((a.ttf0, a.ttf1 or a.ttf0)):
        print("=== font_%d <- %s" % (i, ttf))
        rc |= run_build(ttf, b, i, a.out, a.select, (a.size0, a.size1)[i],
                        a.pad, a.tracking, not a.no_add, print)
    print("итог: %s" % ("ok" if rc == 0 else "есть ошибки"))
    return rc


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--selfcheck" in argv:
        return selfcheck()
    if "--cli" in argv:
        return cli(argv)
    if MISSING:
        root = _root()
        root.title(TITLE)
        root.geometry("720x260")
        Lbl(root, text="Не хватает библиотек: " + ", ".join(MISSING) + "\n\n"
                       "В командной строке выполните:\n"
                       "pip install numpy pillow texture2ddecoder",
            small=True).pack(padx=24, pady=24)
        root.mainloop()
        return 1
    root = _root()
    App(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
