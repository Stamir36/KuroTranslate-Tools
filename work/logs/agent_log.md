# agent_log.md — журнал команд и exit-кодов

Формат: `[дата] cmd → exit_code :: примечание`

## Сессия 2026-10-06

### ЭТАП 0 — фиксация базы
- `pwd; ls -la` → 0 :: Корень `/c/Develop/GitHib/KuroTranslate-Tools`. Python 3.10.11. `work/`, `reports/` отсутствовали (свежий старт).
- `git status --short` → 0 :: Уже присутствовали чужие изменения (НЕ мои): ` M "KuroTools/Parser/Parser XLIF to Ecxel/bat command.txt"`, ` D "KuroTools/Parser/Parser XLIF to Ecxel/scene_table.xlsx"`. Не трогаю.
- `mkdir -p work/{reports,translation_map,logs,backup,extract,repack_check,decompiled,tbl_json}` → 0
- `cp -r KuroTools work/backup/KuroTools_baseline` → 0 :: 4.5 МБ, полная копия форка до merge.

### ЭТАП 1 — merge KuroTools ← KuroTools-master_ForUPDATE
- `find ... comm` diff дерева → 0 :: upstream-only ~180 схем/header + README/LICENSE; fork-only = авторские UI/парсеры/лаунчер + 2 схемы; обоюдные различия — в основном схемы.
- `cmp` по общим файлам → 0 :: реально различаются по содержимому: `dat2py.py`, `disasm/ED9Disassembler.py`, `disasm/ED9InstructionsSet.py`, `json2tbl.py`, `lib/parser.py`, `tbl2json.py` и ~80 схем.
- Анализ `commands_dict` → 0 :: форк 1533 входа, апстрим 1451 (1440 совпадающих имён, 85 только в форке, 3 только в апстриме).
- `cp -r .../schemas/. KuroTools/schemas/` + `cp tbl2json.py json2tbl.py README.md LICENSE.md` → 0 :: схем стало 481 (479 апстрим + 2 авторских fork-only).
- `python -m compileall -q .` → 0 :: ошибок компиляции нет.
- `python -m py_compile launcher.pyw` → 0; `xliff_editor_gui.py` → 0.
- smoke: `tbl2json.py -h`, `json2tbl.py -h`, `dat2py.py -h`, `import disasm.*` → 0.
- `git add <точные пути>; git commit` → 0 :: commit c63c747 (335 файлов, без pycache).

### ЭТАП 2 — распаковка .pac и инвентаризация
- `FPACker.exe` (без арг.) → 0 :: usage: `unpack-all <file.pac>`, `pack <directory>`.
- `cp table/script/scene.pac work/extract/` → 0.
- `./FPACker.exe unpack-all ../work/extract/table.pac` → 0 :: создал `PAC-Extractors/table/` (844 .tbl). Перенесён в `work/extract/table`.
- `./FPACker.exe unpack-all ../work/extract/script.pac` → 0 :: 1016 .dat.
- `./FPACker.exe unpack-all ../work/extract/scene.pac` → 0 :: 1148 файлов (.bin/.json).
- python-проба кодировки → 0 :: UTF-8 подтверждён; результат `work/logs/encoding_probe.json`.
- `git commit` → 0 :: commit b395714.

### ЭТАП 3 — обратимая пересборка
- `FPACker.exe pack ../../extract/table` → 0 :: out.pac в work/extract; сравнение — 28/844 записей отличаются (offset 0x3D8).
- Анализ порядка → 0 :: вывод — оригинал сортирует числовые прогоны лексикографически (left-aligned), регистронезависимо; FPACker сортирует численно.
- `python work/tools/pack_fpac.py work/extract/<p> ... --prefix <p>` → 0 :: таблица/script/scene **byte-identical** с оригиналами (cmp совпал).
- `FPACker.exe pack` для script/scene → byte-identical; для table — DIFFER.
- Распаковка `table_mine.pac` и `diff -r` → **FILES IDENTICAL**.
- `git commit` → 0 :: commit 5c0b290.

### ЭТАП 4 — сценарии (.dat)
- `dat2py.py --decompile False 00_00_00.dat` → KeyError (18,22) :: нужны опкоды Kyoto.
- Добавлен `register_discovered_command` в `ED9InstructionsSet.py` → 0 :: сбор 162 опкодов.
- `scan_opcodes.py scena` → 756/756 OK, 162 уникальных опкодов (лог в work/logs).
- Запечены 162 опкода в статический словарь → py_compile OK, словарь 1698 записей.
- `roundtrip_dat.py` → DIFF; расследование: `opcode_bytes.py` выявил потерю 3807 байт на opcode 0x26 (ADDLINEMARKER) → нужен `--markers True`.
- Исправлен размер: code_len 45116 совпал; затем добавлен дедуп struct params → размер файла совпал (97650).
- Батч 60 файлов → 60 DIFF, размеры совпадают, 0 ошибок. Остаток: слоты varout/sparam-указателей. Статус — частичный (см. STAGE_4_REPORT.md §5).

### ЭТАП 5 — таблицы (.tbl): схемы + json→tbl round-trip
- `batch_tbl.py work/extract/table` → 0 :: базовая линия 844: OK=760 DIFF=81 ERR=3 (90.0%).
- Диагностика: у 811/844 файлов есть хвостовой пул (данные после объявленных таблиц); `tbl2json.py` сохранял его только при полном отсутствии схемы → потеря хвоста (new==end).
- Правка `tbl2json.py`: сохранять хвост (data_dump), если хотя бы один header не покрыт схемой (`all_headers_covered`). Бэкап `work/backup/tbl2json.py.pre_stage5`.
- Batch → OK=831 DIFF=9 ERR=4 (98.5%).
- Диагностика оставшихся DIFF: у 5 файлов `count=0`; `json2tbl.py` терял `length` (в hex-режиме берёт длину из первой записи). Правка: `tbl2json` сохраняет `length` в JSON; `json2tbl` не затирает его нулём. → эти 5 + t_btlsys стали EXACT.
- Причина «зависаний» (t_mapjump/t_active_voice/t_inc): `lib/parser.readtext` зацикливался при `stream.read(1)==b""` (указатель за EOF). Добавлены guard от EOF/длины + `strict` (только для таблиц через `process_data`). Бэкап `work/backup/parser.py.pre_stage5`.
- `tbl2json.py`: при ошибке декодирования по схеме header откатывается на hex (size-match ≠ layout-match, напр. чужая игра) → t_mapjump/t_active_voice/t_achievement стали EXACT.
- O(n²)-баг: `remaining.hex()` вызывался внутри генератора (хвост 629 КБ у t_inc). Исправлено → t_inc EXACT (1.7s).
- Остаются DIFF: t_condition_info, t_costume (совпадают по размеру; схемы подходят по размеру, но layout иной → порядок пула строк различается; нужны собственные Kyoto-схемы).
- Правка таймаута batch: TIMEOUT 60 → 180.

### ЭТАП 6 — карта перевода
- `python work/tools/build_translation_map.py` → 0 :: scripts=46606, tables=21363, total 67969; `work/translation_map/{scripts,tables}.jsonl` + `MAP_INDEX.csv`.
- `python work/tools/analyze_map.py` → 0 :: уникальных строк 29395 (script 11230 + tbl 18252); scena=41766, ai=1167, ani=3665, obj=8.
