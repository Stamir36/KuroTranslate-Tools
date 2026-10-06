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
