# KuroTranslate-Tools ![GitHub repo size](https://img.shields.io/github/repo-size/Stamir36/KuroTranslate-Tools?style=flat-square) ![GitHub last commit](https://img.shields.io/github/last-commit/Stamir36/KuroTranslate-Tools?style=flat-square)

![Banner](https://i.postimg.cc/v8jVKQwg/banner.png)

**Форк [KuroTools](https://github.com/nnguyen259/KuroTools) для работы с файлами `.tbl` и `.dat` игр Nihon Falcom — с готовым конвейером перевода.**
Инструмент извлекает, правит и возвращает в игру текст: отдельно таблицы (`.tbl`, интерфейс и меню) и отдельно скрипты (`.dat`, диалоги и сцены).

> ### ⚠️ В репозитории — только инструмент
> Здесь нет и не должно быть файлов игры и текста игры. Не публикуются: ассеты и
> архивы игры, собранные `.pac`, карты перевода и дампы исходного текста — полный
> список с причинами в разделе **«Что не входит в репозиторий и почему»** ниже.
> Сам перевод распространяется отдельно от репозитория.

---

## ✨ Особенности

*   🖥️ **Лаунчер с тремя вкладками:** `Перевод` (разобрать игру, редактор карты, применить),
    `Сборка` (одна кнопка «Собрать всё → `pac_packed`», пошаговые шаги, автотест),
    `Ещё` (старые инструменты: DAT, TBL, PAC, строки ↔ TSV).
*   📑 **Карта перевода как единственный источник правды** — `translation_map/tables.jsonl`
    и `translation_map/scripts.jsonl`. Перевод живёт в карте, а не в файлах игры, поэтому
    повторная сборка карты его не теряет, а любую строку можно найти по адресу `файл:номер`.
*   🔁 **Конвейер одной командой:** карта → правка файлов → сборка `.tbl`/`.dat` → упаковка
    архива со сверкой с оригиналом.
*   ✏️ **Редактор карты** (`map_editor_gui.py`) с выдачей блоков для ИИ, защитой от потери
    `%s`/`%d`/тегов и встроенным XLIFF-редактором с автопереводом (DeepL/Google).
*   ✅ **Проверки, а не вера на глаз:** разметка и руби, непереведённый японский, длина строк,
    50 безоконных проверок логики лаунчера, round-trip тесты форматов.
*   🈶 **Зафиксированная терминология и правила** в [KuroTools/tools/TRANSLATION_BRIEF.md](KuroTools/tools/TRANSLATION_BRIEF.md).
*   📑 **Парсер `.tbl`** основан на наработках **Trevor\_**; схемы Kyoto-вариантов лежат в `KuroTools/schemas/`.

## 🖼️ Скриншоты

**Лаунчер:**
![Launcher Screenshot](https://i.ibb.co/7N2jmqyQ/banner1.png)

**Редактор XLIFF:**
![Editor Screenshot](https://i.ibb.co/YxV2HVg/banner2.png)

## 🚀 Начало работы

1.  **Клонируйте репозиторий:**
    ```bash
    git clone https://github.com/Stamir36/KuroTranslate-Tools.git
    cd KuroTranslate-Tools
    ```

2.  **Установите зависимости** (нужен Python 3.10+):
    ```bash
    pip install -r requirements.txt
    ```
    На Windows `tkinter` входит в установщик Python, на Linux нужен пакет `python3-tk`.
    Для зашифрованных CLE-файлов используется `zstandard` — он уже в списке.

3.  **Запустите лаунчер:**
    двойной клик по [`KuroTranslate.bat`](KuroTranslate.bat) или
    ```bash
    python KuroTools/launcher.pyw
    ```

> **Кодировка при работе из терминала.** В Windows-консоли выставляйте UTF-8, иначе
> русский и японский текст поедет:
> ```bash
> set PYTHONUTF8=1
> set PYTHONIOENCODING=utf-8
> ```

## 🔁 Рабочий цикл перевода (карты `.jsonl`)

В лаунчере путь такой: вкладка **Перевод** → `1. Разобрать игру (.dat + .tbl)` →
`2. Открыть редактор карты` → заполнить перевод → вкладка **Сборка** →
**`★ Собрать всё → pac_packed`**. Готовый архив появится в `KuroTools/pac_packed/`.

То же самое из терминала (из каталога `KuroTools`):

```bash
python translation_workflow.py prepare                      # распаковать игру и собрать карты
python map_editor_gui.py --kind tbl                         # редактор карты (или --kind script)
python translation_workflow.py apply --kind tbl             # перенести перевод из карты в файлы
python translation_workflow.py build --what table           # пересобрать только устаревшее
python translation_workflow.py pack  --what table           # упаковать (префикс ставится сам)
python translation_workflow.py all   --what table           # всё вместе + сверка с оригиналом
python translation_workflow.py status                       # что сделано, что осталось
```

`all --what table|script|scene` принимает ещё `--force` (пересобрать всё, не глядя на даты)
и `--no-apply` (только собрать и упаковать). После упаковки печатается строка `ИТОГ:`
с путём, размером и списком отличий от оригинала; код возврата `1`, если что-то не сошлось.

Дополнительные пути для тех, кто переводит чатом, без GUI:

```bash
python translation_workflow.py chunks --kind script --size 500 --only-empty   # нарезать куски для ИИ
python translation_workflow.py import-chunks --kind script                    # влить ответы ИИ
python translation_workflow.py map2xliff --kind tbl                           # карта → XLIFF
python translation_workflow.py xliff2map --kind tbl                           # XLIFF → карта
```

## ✅ Проверки качества

Запускаются до сборки — они ловят именно те дефекты, которые в игре выглядят как баг.

| Инструмент | Команда | Что проверяет |
|---|---|---|
| `tools/check_markup.py` | `python tools/check_markup.py --kind both` | Целостность разметки: состав тегов против японского оригинала, правильная вложенность, сохранность одиночных тегов. Эталон — строка оригинала, поэтому унаследованный из японского незакрытый цвет нарушением не считается. |
| `tools/qa_ru.py` | `python tools/qa_ru.py --map table` | Уже внесённый перевод: непереведённый японский, аномальная длина, потерянные теги и руби. |
| `tools/review_ru.py` | `python tools/review_ru.py --kind both --top 50` | Вычитка: самые подозрительные строки списком, с записью отчёта. |
| `tools/draft_check.py` | `python tools/draft_check.py <draft.json>` | Шлюз перед внесением черновика: цел ли JSON, есть ли такие слоты, нет ли конфликтов. |
| `tools/test_launcher_state.py` | `python tools/test_launcher_state.py` | 50 безоконных проверок логики лаунчера: какая кнопка какую команду запускает и когда гаснет. |
| `selftest.py` | `python selftest.py --tbl <dir> --game Kyoto` | Round-trip форматов: `.tbl` побайтово, `.dat` семантически, `.pac` побайтово. |

Для `.dat` проверяется не побайтовое совпадение (Falcom раскладывает одинаковые строки
по разным ячейкам, и размер может отличаться на доли процента), а семантическое:
`disasm(orig) == disasm(rebuild(orig))`.

## 🗂️ Структура репозитория

```
KuroTranslate-Tools/
├── KuroTranslate.bat            # запуск лаунчера
├── requirements.txt
├── KuroTools/
│   ├── launcher.pyw             # лаунчер (3 вкладки)
│   ├── translation_workflow.py  # конвейер перевода: карта → файлы → сборка → архив
│   ├── map_editor_gui.py        # редактор карты (блоки для ИИ, защита тегов)
│   ├── pac_tools.py             # распаковка/упаковка/инфо FPAC (байт-в-точь)
│   ├── tbl2json.py / json2tbl.py        # таблицы .tbl ↔ .json
│   ├── dat2py.py / py2dat_batch.py      # скрипты .dat ↔ .py
│   ├── strings_map.py           # строки ↔ TSV (для ИИ)
│   ├── xliff_editor_gui.py      # редактор XLIFF
│   ├── kuro2compressor.py / kuro2encrypter.py   # сжатие и шифрование (Kuro 2)
│   ├── selftest.py              # автопроверки round-trip
│   ├── schemas/                 # схемы таблиц по играм
│   ├── Start/                   # .bat-цикл по DAT (шаги 1–5)
│   └── tools/                   # инструменты самого перевода (см. таблицу ниже)
├── DOCS/                        # руководства и отчёты
└── KuroTools/translation_map/   # карты перевода — в git не публикуются
```

Инструменты перевода в `KuroTools/tools/`:

| файл | назначение |
|---|---|
| `TRANSLATION_BRIEF.md` | правила и глоссарий: что переводим, как храним теги и руби, чего не трогаем |
| `scene_dump.py` | заготовки сцен: `--list` (сколько осталось), `--missing` (создать черновики) |
| `scene_show.py` | напечатать все строки файла по слотам (японский + перевод) |
| `find_text.py` | найти сцену по японской фразе и показать её целиком |
| `apply_ru.py` | внести черновики в карты (`--dry-run`, `--skip-unknown`, `--no-scene-file`) |
| `scene_set.py` | внести в карту один файл сцены (со сверкой японского) |
| `qa_ru.py` / `review_ru.py` | проверка и вычитка внесённого перевода |
| `check_markup.py` | целостность разметки против японского оригинала |
| `scene_verify.py` | проверить сцену уже внутри собранного `.pac` |
| `test_launcher_state.py` | безоконные проверки логики лаунчера |
| `LAUNCHER_AUDIT.md` | разбор найденных и исправленных ошибок лаунчера |

## 📑 Формат карты перевода

```json
{"id": "table/t_text.tbl:2442", "file": "table/t_text.tbl", "kind": "tbl",
 "jp_text": "Steamオーバーレイでポーズ", "ru_text": "Пауза через оверлей Steam", "context": "tbl string field", "flags": ""}
```

* `id` — файл плюс номер строки. Номер устойчив: и разбор карты, и перенос перевода
  идут по одному и тому же порядку строк, поэтому адрес не «разъезжается» — по нему
  можно найти строку из любого отчёта об ошибке.
* `ru_text` — заполняет переводчик; пусто означает «не переведено».
* `flags` подсказывает, что нельзя ломать при правке: `format` (`%s`/`%d`),
  `markup` (теги `<...>`), `newline` (перенос строки), `whitespace`, `short`, `suspect`.
* Разметка в переводе сохраняется полностью: теги вида `<C0>`, `</C>`, `<R>`,
  `\n`, `{0}`, `%s`. Руби записывается как `<R>иероглифы</Rчтение>` — чтение
  переводится, тег остаётся на месте.

## 🈶 Терминология

Единый глоссарий и правила лежат в [KuroTools/tools/TRANSLATION_BRIEF.md](KuroTools/tools/TRANSLATION_BRIEF.md).
Ключевые термины, чтобы правки не расходились:

| 日本語 | Русский |
|---|---|
| 怪異 | Грид |
| 異界化 | Затмение |
| 装魂霊具 | Соул-Девайс |
| ザナドゥ | Занаду |
| 如月 | Кисараги |
| 比良坂学園 | Академия Хирасака |

## 🛠️ Пакетный цикл DAT и TBL (терминал)

Готовые `.bat` лежат в [`KuroTools/Start/`](KuroTools/Start): `1_disassemble_dat.bat` →
`2_extract_strings.bat` → `3_edit_translation.bat` → `4_create_translation_map.bat` →
`5_compile_dat.bat`.

Вручную то же самое:

```bash
python dat2py_batch.py      # .dat → .py (дизассемблирование)
python py_to_xliff.py       # строки из .py → .xliff
#   ... перевод в XLIFF-редакторе ...
python inject_translations.py   # собрать карту перевода
python py2dat_batch.py      # .py → .dat
```

## 📚 Документация

* [KuroTools/START_HERE.md](KuroTools/START_HERE.md) — подробный рабочий цикл, разбор редактора
  карты, раскладка рабочих каталогов, что попадает в карту и что отсеивается.
* [nnguyen259/KuroTools](https://github.com/nnguyen259/KuroTools) — оригинальный проект, от
  которого идёт этот форк: документация по форматам, модели и схемы.
* [KuroTools/START_HERE.md](KuroTools/START_HERE.md) — раскладка каталогов, отбор строк в карту,
  правила восстановления перевода при пересборке карты.
* [DOCS/](DOCS) — руководства по схемам и по редактированию скриптов и таблиц.
* [KuroTools/tools/LAUNCHER_AUDIT.md](KuroTools/tools/LAUNCHER_AUDIT.md) — найденные и
  исправленные ошибки лаунчера.
* [DOCS/audit/TABLE_MAP_FIX_2026-10-08.md](DOCS/audit/TABLE_MAP_FIX_2026-10-08.md) — разбор
  критических ошибок карты таблиц и методы проверки.
* [DOCS/Публикация перевода.md](DOCS/Публикация%20перевода.md) — шаблон описания релиза
  перевода: правовая рамка, глоссарий, известные ограничения, как принимать багрепорты.

## ⚖️ Что не входит в репозиторий и почему

Репозиторий публикует **инструмент**, а не игру и не перевод. Исключено осознанно
(см. [`.gitignore`](.gitignore) и [KuroTools/.gitignore](KuroTools/.gitignore)):

| Что | Почему |
|---|---|
| Ассеты, шрифты, распакованные ресурсы игры | Собственность Nihon Falcom. Публикация — нарушение прав и риск блокировки репозитория. |
| Собранные архивы `.pac`, архив с русской копией игры | Это изменённые файлы данных игры; распространяются отдельно от репозитория. |
| Карты перевода `translation_map/*.jsonl` | Содержат исходный японский текст игры построчно. |
| Черновики, дампы текста для аудита сцен | То же: построчный текст игры. |
| Сторонние бинарники и редакторы | Не наш код и не наша лицензия. |
| Рабочий мусор: `__pycache__`, логи, копии карт, временные файлы | Не нужен никому, кроме автора. |

Побочный эффект: инструменты, уважающие `.gitignore`, не читают эти каталоги. При работе
над волной перевода маску можно временно снять или перенести правило в `.git/info/exclude`.

## 🧩 Совместимость

Ориентир этого форка — **Kuro no Kiseki / Kyoto** (`.tbl` + `.dat`). Инструмент основан на
KuroTools и работает также с другими играми на том же движке:

Kuro no Kiseki (CLE) · Trails through Daybreak (NISA/PH3) · Kuro no Kiseki 2 -CRIMSON SiN- ·
Trails through Daybreak 2 · Kai no Kiseki -Farewell, O Zemuria- · Trails beyond the Horizon ·
Ys X: Nordics · Ys X: Proud Nordics · Sora no Kiseki the 1st · Trails in the Sky 1st Chapter.

Для последних четырёх поддержка `.dat` частичная. Для любой игры нужна подходящая схема
таблиц (`--game` или список «Игра (схема)» в лаунчере), а для Kuro 2 — ещё сжатие и
шифрование архивов (`kuro2compressor.py`, `kuro2encrypter.py`).

## 🤝 Участие и поддержка

*   Об ошибках и предложениях сообщайте через [Issues](https://github.com/Stamir36/KuroTranslate-Tools/issues).
    Полезно приложить: команду, текст ошибки и — если дело в конкретной строке перевода —
    её адрес вида `файл:номер`.
*   Пул-реквесты приветствуются. Перед PR прогоните `check_markup.py`, `qa_ru.py`
    и `test_launcher_state.py`: они быстрые и ловят большинство регрессий.

## 📄 Лицензия и благодарности

Лицензия — **MIT** (см. [LICENSE](LICENSE)).

*   Оригинальный **KuroTools** — [nnguyen259](https://github.com/nnguyen259/KuroTools), MIT.
*   Парсер `.tbl` — на наработках **Trevor\_**.
*   Игра и её ресурсы — собственность **Nihon Falcom**. Этот репозиторий не содержит
    материалов игры и не аффилирован с правообладателем.
