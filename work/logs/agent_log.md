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
