#!/usr/bin/env python3
"""map_editor_gui.py — постраничный редактор карты перевода.

Карта: KuroTools/translation_map/scripts.jsonl | tables.jsonl
Рабочий цикл рассчитан на перевод вместе с ИИ:

    1. выставить фильтры (карта, файл, «только непереведённые»);
    2. «Скопировать блок для ИИ» — страница уезжает в буфер как jsonl;
    3. ответ ИИ вставить в правое поле и нажать «Применить блок»;
    4. переведённые строки исчезают из выдачи, страница сама наполняется
       следующими — так проход идёт до конца без разметки вручную.

Ручной перевод тоже есть: у каждой строки на странице своё поле «RU».

Защита от поломок (ИИ правит всю строку целиком):
    * одиночные идентификаторы и служебные строки в карту не попадают;
    * ключ в строках вида «KEY：текст» хранится отдельно и не переводится;
    * строки с флагами format (%s/%d), markup (<...>), newline проверяются:
      если в переводе потерян спецификатор или тег — строка не применяется
      (переключатель «не применять опасные строки» включён по умолчанию).

Запуск:
    python map_editor_gui.py [--kind tbl|script] [--page 50]
"""
import argparse
import io
import json
import os
import re
import sys

import tkinter as tk
from tkinter import filedialog, messagebox

import customtkinter as ctk

HERE = os.path.dirname(os.path.abspath(__file__))
MAPS = os.path.join(HERE, "translation_map")
MAP_FILES = {"script": "scripts.jsonl", "tbl": "tables.jsonl"}
KIND_TITLES = {"script": "Скрипты (.dat — реплики, подсказки)",
               "tbl": "Таблицы (.tbl — UI, меню, описания)"}
PAGE_SIZES = ["25", "50", "100", "200"]
ALL_FILES = "— все файлы —"
STATUSES = ["непереведённые", "переведённые", "все"]

ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")

FORMAT_RE = re.compile(r"%[0-9]*[sdf]")
TAG_RE = re.compile(r"</?[A-Za-z][A-Za-z0-9_]*>")


# ===========================================================================
#  Логика карты (без GUI — её же проверяет тест)
# ===========================================================================
def map_path(kind):
    return os.path.join(MAPS, MAP_FILES[kind])


def load_map(kind):
    path = map_path(kind)
    if not os.path.exists(path):
        return []
    recs = []
    with io.open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                recs.append(json.loads(line))
    return recs


def save_map(kind, recs):
    path = map_path(kind)
    tmp = path + ".tmp"
    with io.open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        for r in recs:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    os.replace(tmp, path)
    return sum(1 for r in recs if (r.get("ru_text") or "").strip())


def is_done(rec):
    return bool((rec.get("ru_text") or "").strip())


def flag_set(rec):
    return set((rec.get("flags") or "").split(",")) - {""}


def pick_rows(recs, file_filter=None, status="непереведённые", search="",
              only_flags=False):
    """Индексы записей карты, попадающих в выдачу, в порядке файла."""
    needle = search.strip().lower()
    out = []
    for i, r in enumerate(recs):
        if file_filter and file_filter != ALL_FILES and r.get("file") != file_filter:
            continue
        done = is_done(r)
        if status == "непереведённые" and done:
            continue
        if status == "переведённые" and not done:
            continue
        if only_flags:
            fl = flag_set(r)
            if not (fl & {"format", "markup", "newline"}):
                continue
        if needle:
            hay = (r.get("jp_text", "") + "\n" + r.get("ru_text", "")
                   + "\n" + r.get("id", "")).lower()
            if needle not in hay:
                continue
        out.append(i)
    return out


def block_text(recs, idxs):
    """Блок для ИИ: те же записи карты, только с пустым ru_text."""
    lines = []
    for i in idxs:
        r = recs[i]
        lines.append(json.dumps({
            "id": r.get("id"),
            "file": r.get("file"),
            "kind": r.get("kind"),
            "jp_text": r.get("jp_text", ""),
            "ru_text": "",
            "context": r.get("context", ""),
            "flags": r.get("flags", ""),
        }, ensure_ascii=False))
    return "\n".join(lines)


def safety_problems(src, ru, flags):
    """Что потерялось при переводе строки (для строк с флагами)."""
    bad = []
    fl = set((flags or "").split(",")) - {""}
    if "format" in fl:
        a = FORMAT_RE.findall(src)
        b = FORMAT_RE.findall(ru)
        if sorted(a) != sorted(b):
            bad.append(f"спецификаторы %s/%d: было {a}, стало {b}")
    if "markup" in fl:
        a = TAG_RE.findall(src)
        b = TAG_RE.findall(ru)
        if sorted(a) != sorted(b):
            bad.append(f"теги: было {a}, стало {b}")
    if "newline" in fl and src.count("\n") != ru.count("\n"):
        bad.append(f"переносы строк: было {src.count(chr(10))}, "
                   f"стало {ru.count(chr(10))}")
    return bad


def _strip_fences(text):
    text = text.strip()
    m = re.match(r"^```[a-zA-Z]*\s*\n(.*?)\n?```$", text, re.S)
    if m:
        text = m.group(1)
    return text


def parse_reply(text, by_id, by_jp):
    """Разбирает ответ ИИ в {id: перевод} и список предупреждений.

    Принимаем: jsonl построчно, JSON-массив объектов, JSON-объект вида
    {"id": "перевод"} и строки «id<TAB>перевод».
    """
    text = _strip_fences(text or "")
    if not text.strip():
        return {}, ["пусто: нечего применять"]
    items = []
    warn = []
    try:
        data = json.loads(text)
        if isinstance(data, list):
            items = data
        elif isinstance(data, dict):
            if "records" in data and isinstance(data["records"], list):
                items = data["records"]
            elif "id" in data and "ru_text" in data:
                items = [data]
            else:
                items = [{"id": k, "ru_text": v} for k, v in data.items()]
    except json.JSONDecodeError:
        for n, line in enumerate(text.splitlines(), 1):
            line = line.strip().rstrip(",")
            if not line or line in "[]{}":
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                if "\t" in line:
                    ident, _, ru = line.partition("\t")
                    obj = {"id": ident.strip(), "ru_text": ru.strip()}
                else:
                    warn.append(f"строка {n}: не разобрана")
                    continue
            if isinstance(obj, dict):
                items.append(obj)
    out = {}
    for it in items:
        if not isinstance(it, dict):
            continue
        ru = it.get("ru_text")
        if ru is None:
            ru = it.get("ru") or it.get("translation") or it.get("target")
        if not isinstance(ru, str) or not ru.strip():
            continue
        ident = it.get("id")
        rec = by_id.get(ident) if ident else None
        if rec is None:
            jp = it.get("jp_text") or it.get("source") or it.get("jp")
            rec = by_jp.get(jp) if jp else None
        if rec is None:
            warn.append(f"не найдена запись: {str(ident)[:60]}")
            continue
        out[rec["id"]] = ru.strip()
    return out, warn


# ===========================================================================
#  GUI
# ===========================================================================
class MapEditorApp:
    def __init__(self, root, kind="tbl", page_size=50):
        self.root = root
        self.kind = kind if kind in MAP_FILES else "tbl"
        self.recs = []
        self.rows = []
        self.page = 0
        self.page_size = page_size
        self.row_vars = []          # [(rec, tk.StringVar)] для текущей страницы
        self.jp_labels = []         # метки японского текста (перенос под ширину)
        self.wrap_px = 700
        self.changed = False

        root.title("Редактор карты перевода — KYOTO XANADU")
        root.geometry("1500x900")
        root.minsize(1100, 700)

        self._build_top()
        self._build_body()
        self._build_bottom()
        root.bind("<Control-s>", lambda e: self.save(banner=True))
        root.bind("<Control-Right>", lambda e: self.go(1))
        root.bind("<Control-Left>", lambda e: self.go(-1))
        root.bind("<Control-Return>", lambda e: self.apply_from_field())
        self.load()

    # ---------------- интерфейс ----------------
    def _build_top(self):
        bar = ctk.CTkFrame(self.root, corner_radius=6)
        bar.pack(fill="x", padx=10, pady=(10, 6))
        ctk.CTkLabel(bar, text="Карта:", font=ctk.CTkFont(weight="bold")).pack(
            side="left", padx=(10, 4), pady=8)
        self.kind_combo = ctk.CTkComboBox(bar, width=190, values=list(KIND_TITLES.values()),
                                          command=lambda v: self.switch_kind(v))
        self.kind_combo.set(KIND_TITLES[self.kind])
        self.kind_combo.pack(side="left", padx=(0, 12), pady=8)
        ctk.CTkButton(bar, text="Загрузить", width=90, command=self.load).pack(
            side="left", padx=(0, 12), pady=8)

        self.file_combo = ctk.CTkComboBox(bar, width=260, values=[ALL_FILES],
                                          command=lambda v: self.refresh())
        self.file_combo.set(ALL_FILES)
        self.file_combo.pack(side="left", padx=(0, 12), pady=8)

        self.status_combo = ctk.CTkComboBox(bar, width=150, values=STATUSES,
                                            command=lambda v: self.refresh())
        self.status_combo.set("непереведённые")
        self.status_combo.pack(side="left", padx=(0, 12), pady=8)

        self.only_flags = ctk.CTkCheckBox(bar, text="только с %s/тегами",
                                          command=self.refresh)
        self.only_flags.pack(side="left", padx=(0, 12), pady=8)

        self.search_entry = ctk.CTkEntry(bar, width=220,
                                         placeholder_text="поиск: японский или русский")
        self.search_entry.pack(side="left", padx=(0, 12), pady=8)
        self.search_entry.bind("<Return>", lambda e: self.refresh())

        ctk.CTkLabel(bar, text="строк:").pack(side="left", padx=(0, 4))
        self.size_combo = ctk.CTkComboBox(bar, width=80, values=PAGE_SIZES,
                                          command=self.change_size)
        self.size_combo.set(str(self.page_size))
        self.size_combo.pack(side="left", pady=8)

    def _build_body(self):
        body = ctk.CTkFrame(self.root, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=10, pady=(0, 6))

        left = ctk.CTkFrame(body, corner_radius=6)
        left.pack(side="left", fill="both", expand=True)
        ctk.CTkLabel(left, text="Страница карты", font=ctk.CTkFont(weight="bold")).pack(
            anchor="w", padx=12, pady=(10, 2))
        self.page_info = ctk.CTkLabel(left, text="", anchor="w",
                                      text_color="gray60")
        self.page_info.pack(anchor="w", padx=12, pady=(0, 6))
        self.list_frame = ctk.CTkScrollableFrame(left, label_text="")
        self.list_frame.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        # Перенос строк подстраивается под ширину панели, иначе длинный
        # японский текст вылезает за левый край.
        self.list_frame.bind("<Configure>", self._on_list_resize)

        right = ctk.CTkFrame(body, corner_radius=6, width=470)
        right.pack(side="left", fill="y", padx=(10, 0))
        right.pack_propagate(False)

        ctk.CTkLabel(right, text="1. Скопируйте этот блок и отдайте ИИ",
                     font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=12,
                                                           pady=(10, 2))
        ctk.CTkLabel(right, text="(jsonl: заполнить ru_text, остальное не менять)",
                     text_color="gray60", anchor="w").pack(anchor="w", padx=12)
        self.block_box = ctk.CTkTextbox(right, height=250, wrap="none",
                                        font=ctk.CTkFont(family="Consolas", size=11))
        self.block_box.pack(fill="x", padx=12, pady=(4, 4))
        row1 = ctk.CTkFrame(right, fg_color="transparent")
        row1.pack(fill="x", padx=12, pady=(0, 8))
        ctk.CTkButton(row1, text="Скопировать блок", command=self.copy_block).pack(
            side="left")
        ctk.CTkButton(row1, text="Перевести вручную", fg_color="transparent",
                      border_width=1, command=self.make_skeleton).pack(
            side="left", padx=8)

        ctk.CTkLabel(right, text="2. Вставьте ответ ИИ и примените",
                     font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=12,
                                                           pady=(6, 2))
        self.reply_box = ctk.CTkTextbox(right, height=170, wrap="none",
                                        font=ctk.CTkFont(family="Consolas", size=11))
        self.reply_box.pack(fill="x", padx=12, pady=(4, 4))
        row2 = ctk.CTkFrame(right, fg_color="transparent")
        row2.pack(fill="x", padx=12, pady=(0, 6))
        ctk.CTkButton(row2, text="Вставить из буфера", command=self.paste_reply).pack(
            side="left")
        ctk.CTkButton(row2, text="Применить блок", command=self.apply_from_field,
                      fg_color="green", hover_color="darkgreen").pack(
            side="left", padx=8)

        self.guard = ctk.CTkCheckBox(right, text="не применять строки, где потеряны %s/теги")
        self.guard.select()
        self.guard.pack(anchor="w", padx=12, pady=(0, 8))

        self.log_label = ctk.CTkLabel(right, text="", anchor="w", justify="left",
                                      wraplength=430, text_color="gray70")
        self.log_label.pack(anchor="w", padx=12, pady=(0, 8))

    def _build_bottom(self):
        bar = ctk.CTkFrame(self.root, corner_radius=6)
        bar.pack(fill="x", padx=10, pady=(0, 10))
        ctk.CTkButton(bar, text="◀", width=44, command=lambda: self.go(-1)).pack(
            side="left", padx=(10, 6), pady=8)
        self.page_entry = ctk.CTkEntry(bar, width=70)
        self.page_entry.pack(side="left", pady=8)
        self.page_entry.bind("<Return>", self.jump)
        self.pages_label = ctk.CTkLabel(bar, text="")
        self.pages_label.pack(side="left", padx=8)
        ctk.CTkButton(bar, text="▶", width=44, command=lambda: self.go(1)).pack(
            side="left", padx=(0, 16), pady=8)

        ctk.CTkButton(bar, text="Сохранить карту (Ctrl+S)", command=lambda: self.save(banner=True),
                      fg_color="transparent", border_width=1).pack(
            side="left", padx=(0, 10), pady=8)
        ctk.CTkButton(bar, text="Пересобрать карту заново",
                      fg_color="transparent", border_width=1,
                      command=self.rebuild_map).pack(side="left", padx=(0, 10), pady=8)
        self.stats = ctk.CTkLabel(bar, text="", anchor="e")
        self.stats.pack(side="right", padx=12)

    # ---------------- загрузка и фильтры ----------------
    def switch_kind(self, title):
        for k, t in KIND_TITLES.items():
            if t == title:
                self.kind = k
        self.load()

    def load(self):
        if self.changed and not self._confirm_discard():
            return
        self.recs = load_map(self.kind)
        files = sorted({r.get("file", "") for r in self.recs})
        self.file_combo.configure(values=[ALL_FILES] + files)
        if self.file_combo.get() not in ([ALL_FILES] + files):
            self.file_combo.set(ALL_FILES)
        self.changed = False
        self.page = 0
        self.refresh()

    def _confirm_discard(self):
        if not self.changed:
            return True
        ans = messagebox.askyesnocancel("Не сохранено",
                                        "Есть правки в полях RU. Сохранить карту?")
        if ans is None:
            return False
        if ans:
            self.save()
        return True

    def change_size(self, value):
        try:
            self.page_size = int(value)
        except ValueError:
            self.page_size = 50
        self.page = 0
        self.refresh(keep_edits=True)

    def refresh(self, keep_edits=False):
        if keep_edits:
            self.collect_rows()
        self.rows = pick_rows(
            self.recs,
            file_filter=self.file_combo.get(),
            status=self.status_combo.get(),
            search=self.search_entry.get(),
            only_flags=bool(self.only_flags.get()))
        pages = max(1, (len(self.rows) + self.page_size - 1) // self.page_size)
        self.page = max(0, min(self.page, pages - 1))
        self.render_page(pages)
        done = sum(1 for r in self.recs if is_done(r))
        total = len(self.recs)
        pct = 100.0 * done / total if total else 0.0
        self.stats.configure(
            text=f"переведено {done} / {total} ({pct:.1f} %)   |   "
                 f"в выдаче {len(self.rows)}")

    def _page_slice(self):
        start = self.page * self.page_size
        return self.rows[start:start + self.page_size]

    def _on_list_resize(self, event):
        self.wrap_px = max(240, event.width - 60)
        for lbl in self.jp_labels:
            try:
                lbl.configure(wraplength=self.wrap_px)
            except Exception:
                pass

    def render_page(self, pages):
        for w in self.list_frame.winfo_children():
            w.destroy()
        self.row_vars = []
        self.jp_labels = []
        idxs = self._page_slice()
        for i in idxs:
            self._make_row(self.recs[i])
        self.page_info.configure(
            text=f"{self.kind}.jsonl · страница {self.page + 1} из {pages} · "
                 f"показано {len(idxs)}")
        self.page_entry.delete(0, "end")
        self.page_entry.insert(0, str(self.page + 1))
        self.pages_label.configure(text=f"/ {pages}")
        self.block_box.delete("1.0", "end")
        self.block_box.insert("1.0", block_text(self.recs, idxs))
        self.grab()
        self._show(f"на странице {len(idxs)} строк")

    def _make_row(self, rec):
        flags = flag_set(rec)
        card = ctk.CTkFrame(self.list_frame, corner_radius=5)
        card.pack(fill="x", pady=3, padx=2)
        head = ctk.CTkFrame(card, fg_color="transparent")
        head.pack(fill="x", padx=8, pady=(6, 0))
        ctk.CTkLabel(head, text=rec.get("id", ""), anchor="w",
                     text_color="gray60",
                     font=ctk.CTkFont(size=11)).pack(side="left")
        if flags:
            color = "#8B0000" if (flags & {"format", "markup", "newline"}) else "gray50"
            ctk.CTkLabel(head, text=" " + ",".join(sorted(flags)), anchor="e",
                         text_color=color).pack(side="right")
        jp = ctk.CTkLabel(card, text=rec.get("jp_text", ""), anchor="w", justify="left",
                          wraplength=self.wrap_px)
        jp.pack(fill="x", padx=8, pady=(2, 2))
        self.jp_labels.append(jp)
        var = tk.StringVar(value=rec.get("ru_text", "") or "")
        entry = ctk.CTkEntry(card, textvariable=var)
        entry.pack(fill="x", padx=8, pady=(0, 6))
        self.row_vars.append((rec, var))

    def collect_rows(self):
        for rec, var in self.row_vars:
            val = var.get()
            if val != (rec.get("ru_text") or ""):
                rec["ru_text"] = val
                self.changed = True

    # ---------------- блоки для ИИ ----------------
    def copy_block(self):
        text = self.block_box.get("1.0", "end").strip()
        if not text:
            self._show("блок пуст — нет строк на странице")
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        n = text.count("\n") + 1
        self._show(f"скопировано строк: {n} (вставить в чат ИИ)")

    def make_skeleton(self):
        """Подставить в поле ответа заготовку, чтобы перевести вручную/в чате."""
        self.reply_box.delete("1.0", "end")
        self.reply_box.insert("1.0", self.block_box.get("1.0", "end").strip())
        self._show("заготовка перенесена в поле ответа — заполните ru_text")

    def paste_reply(self):
        try:
            text = self.root.clipboard_get()
        except tk.TclError:
            self._show("буфер обмена пуст")
            return
        self.reply_box.delete("1.0", "end")
        self.reply_box.insert("1.0", text)
        self._show(f"вставлено из буфера: {len(text)} символов")

    def apply_from_field(self):
        self.collect_rows()
        text = self.reply_box.get("1.0", "end")
        by_id = {r["id"]: r for r in self.recs if "id" in r}
        by_jp = {}
        for r in self.recs:
            by_jp.setdefault(r.get("jp_text"), r)
        updates, warn = parse_reply(text, by_id, by_jp)
        if not updates:
            self._show("в ответе не найдено ни одной переводимой строки"
                       + (f"; предупреждений: {len(warn)}" if warn else ""))
            return
        blocked = []
        applied = 0
        for ident, ru in updates.items():
            rec = by_id.get(ident)
            if rec is None:
                continue
            if self.guard.get():
                bad = safety_problems(rec.get("jp_text", ""), ru,
                                      rec.get("flags", ""))
                if bad:
                    blocked.append((ident, bad))
                    continue
            rec["ru_text"] = ru
            applied += 1
        self.changed = True
        # collect=False: правки из полей уже собраны выше, а повторный сбор
        # перезаписал бы только что применённый перевод пустыми полями страницы.
        self.save(collect=False)
        self.reply_box.delete("1.0", "end")
        msg = f"применено строк: {applied}"
        if blocked:
            msg += f" | заблокировано опасных: {len(blocked)}"
        if warn:
            msg += f" | предупреждений: {len(warn)}"
        self.refresh()
        self._show(msg, extra=blocked[:3] + [(w, ["предупреждение"]) for w in warn[:3]])

    # ---------------- сохранение ----------------
    def save(self, banner=False, collect=True):
        if collect:
            self.collect_rows()
        done = save_map(self.kind, self.recs)
        self.changed = False
        if banner:
            self._show(f"карта сохранена: переведено {done} из {len(self.recs)}")
        return done

    def rebuild_map(self):
        if not messagebox.askyesno(
                "Пересобрать карту",
                "Пересобрать карту из разобранных файлов?\n\n"
                "Готовые ru_text будут перенесены, но если правки в полях RU не "
                "сохранены — сохраните их сначала."):
            return
        if self.changed:
            self.save()
        import subprocess
        env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
        p = subprocess.run([sys.executable, "-u",
                            os.path.join(HERE, "translation_workflow.py"), "maps"],
                           cwd=HERE, env=env, capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        out = (p.stdout or p.stderr or "").strip().splitlines()
        self.load()
        self._show(" ".join(out[-2:]) or "готово")

    # ---------------- навигация ----------------
    def go(self, delta):
        self.collect_rows()
        pages = max(1, (len(self.rows) + self.page_size - 1) // self.page_size)
        target = self.page + delta
        if 0 <= target < pages:
            self.page = target
            self.render_page(pages)
        else:
            self._show("это крайняя страница")

    def jump(self, event=None):
        self.collect_rows()
        try:
            n = int(self.page_entry.get()) - 1
        except ValueError:
            return
        pages = max(1, (len(self.rows) + self.page_size - 1) // self.page_size)
        if 0 <= n < pages:
            self.page = n
            self.render_page(pages)

    # ---------------- мелочи ----------------
    def grab(self):
        """Забирает фокус с полей, чтобы Ctrl+S/Ctrl+Enter работали."""
        try:
            self.root.focus_set()
        except tk.TclError:
            pass

    def _show(self, text, extra=None):
        lines = [text]
        for ident, problems in (extra or []):
            lines.append(f"• {ident}: {'; '.join(problems)}")
        self.log_label.configure(text="\n".join(lines))


def main():
    ap = argparse.ArgumentParser(description="Постраничный редактор карты перевода.")
    ap.add_argument("--kind", default="tbl", choices=["script", "tbl"],
                    help="какую карту открыть (по умолчанию tbl)")
    ap.add_argument("--page", type=int, default=50, help="строк на странице")
    args = ap.parse_args()
    root = ctk.CTk()
    MapEditorApp(root, kind=args.kind, page_size=args.page)
    root.mainloop()


if __name__ == "__main__":
    main()
