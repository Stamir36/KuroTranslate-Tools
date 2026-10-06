# MERGE_PLAN.md — план слияния `KuroTools/` ← `KuroTools-master_ForUPDATE/`

Составлен по фактическому diff (команды зафиксированы в `work/logs/agent_log.md`, Этап 1).
Сравнение — из корня проекта: `KuroTools/` (форк владельца, годовалый) vs `KuroTools-master_ForUPDATE/` (свежий апстрим nnguyen259/KuroTools).

## 0. Сводка
| Категория | Кол-во | Действие |
|---|---|---|
| UPSTREAM_ONLY (файлы/дерево) | ~182 файла (в осн. `schemas/headers/*.json`, `schemas/t_*.json`, `README.md`, `LICENSE.md`) | скопировать в `KuroTools/` |
| FORK_ONLY (авторские) | 27 файлов (UI, парсеры, батники, xliff, exe, 2 схемы) | НЕ ТРОГАТЬ |
| BOTH_DIFFER — код | 6 файлов | РУЧНОЙ merge (см. §2) |
| BOTH_DIFFER — схемы | ~80 файлов | принять апстрим (см. §3) |
| IDENTICAL | остальное (`lib/packer.py`, `lib/crc32.py`, `lib/blowfish.py`, `disasm/function.py`, `disasm/script.py`, `disasm/ED9Assembler.py`, `mdl/*`, …) | пропустить |

## 1. FORK_ONLY — авторские надстройки владельца (НЕ ТРОГАТЬ)
UI/пайплайн владельца:
`launcher.pyw`, `xliff_editor_gui.py`, `py_to_xliff.py`, `inject_translations.py`,
`dat2py_batch.py`, `py2dat_batch.py`, `tbl_strings.xliff`, `tbl_strings.xliff.bak`,
`p3a_tool.exe`, `schemas/t_npc_c0000.json`, `schemas/t_place_0.json`;
дерево `Parser/` (в т.ч. `Parser XLIF to Ecxel/`, `Parser XLIF to JSON/`);
дерево `Start/` (батники рабочего процесса, README, PNG);
в корне репозитория: `KuroTranslate.bat`, `text_assembler.py`.
**Статус: не изменялись этим merge. Проверено компиляцией (`launcher.pyw`, `xliff_editor_gui.py` → OK).**

## 2. BOTH_DIFFER — код: решения по каждому конфликту
| Файл | Суть расхождения | Решение | Обоснование |
|---|---|---|---|
| `lib/parser.py` | форк = апстрим + в конце закомментирован оригинал `get_actual_value_str` и добавлена авторская версия с экранированием `\` и `"`, обёрткой `FLOAT()/INT()` | **ОСТАВЛЕН ФОРК** | расхождение только в хвосте; авторская версия — осознанная правка под round-trip текста; основной код совпадает с апстримом |
| `disasm/ED9Disassembler.py` | единственная разница — функция чтения текстового операнда: форк экранирует `\`→`\\`, `"`→`'`, `\n`; апстрим только `\n` (плюс пустая строка) | **ОСТАВЛЕН ФОРК** | иных апстрим-изменений в файле нет; правка согласована с `lib/parser.py` и нужна для корректного round-trip строк |
| `disasm/ED9InstructionsSet.py` | форк: `commands_dict` расширен до 1533 записей; исправлен баг апстрима в `OP_27` (`operand(vakye, …)` → `operand(value, …)`); `OP_25` помечает цель меткой; в `to_string` добавлено экранирование; обработка неизвестного опкода через KeyError | **ОСТАВЛЕН ФОРК + добавлены 3 записи из апстрима** | словарь форка — надмножество (1440 имён совпадают, 85 уникальны; в апстриме на 3 больше). Форк содержит реальные фиксы round-trip. Добавлены отсутствовавшие `(6,45)`, `(13,108)`, `(13,109)` |
| `json2tbl.py` | апстрим переписал: матчинг схемы по `game`+`length`, чтение `schemas/headers/<name>.json`, фолбэк по длине | **ПРИНЯТ АПСТРИМ** | в форке нет авторских правок (нет кириллицы/marks); апстрим — строгое развитие логики |
| `tbl2json.py` | апстрим: `-g/--game`, подстановка `\d`→`%d` для generic-схем, `try/finally`, проверка схем | **ПРИНЯТ АПСТРИМ** | форк устаревший; авторских правок нет |
| `dat2py.py` | форк меняет дефолт `--decompile` на `"False"` (disasm-режим по умолчанию) | **ОСТАВЛЕН ФОРК** | соответствует приоритету проекта (disasm как релизный канал) и рекомендации апстрим-README |

## 3. BOTH_DIFFER — схемы (~80): принят апстрим
Выборочная проверка (`t_books`, `headers/BooksText`, `t_item`, `t_status`, `t_mapjump`, `t_quest`) показала: расхождения — это **чистые апстрим-дополнения** (новые заголовки в списках таблиц, например `BooksCategory`, `ItemShopTabType`, `ItemParam`, `SkillEffectText`, `MapJumpChrIcon`, `NaviText`, `QuestReportVoice`; блок `FALCOM_PC` в `BooksText`). Авторских правок (кириллица, свои имена) в схемах не обнаружено.
→ `cp -r KuroTools-master_ForUPDATE/schemas/. KuroTools/schemas/`. Fork-only схемы `t_npc_c0000.json`, `t_place_0.json` сохранены (не перетёрты).

## 4. UPSTREAM_ONLY — принято
`README.md`, `LICENSE.md`, весь новый корпус `schemas/headers/*.json` и `schemas/t_*.json` (Kyoto-специфичные: `t_abordage`, `t_free_dungeon`, `t_manaride_game`, `t_recapture_island`, `t_ship_talk`, viewer-наборы и др.).

## 5. Пост-merge проверки
- `python -m compileall -q .` в `KuroTools/` → exit 0.
- `python -m py_compile launcher.pyw` → 0; `xliff_editor_gui.py` → 0.
- Импорт `disasm.ED9Disassembler / ED9Assembler / ED9InstructionsSet` → OK.
- CLI `-h` у `tbl2json.py`, `json2tbl.py`, `dat2py.py` → OK.
