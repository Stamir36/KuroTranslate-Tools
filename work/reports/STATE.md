# STATE.md — состояние работ по русскому переводу KYOTO XANADU

Обновляется после каждого этапа. При возобновлении сессии — читать первым.

## Текущий этап
**Этап 2 — распаковка .pac и инвентаризация** (следующий к запуску).

## Сделано
- **Этап 0**: создано дерево `work/{reports,translation_map,logs,backup,extract,repack_check,decompiled,tbl_json}`; бэкап форка → `work/backup/KuroTools_baseline/`; окружение — Python 3.10.11.
- **Этап 1**: merge `KuroTools/` ← `KuroTools-master_ForUPDATE/` выполнен.
  - Схемы и `tbl2json.py`/`json2tbl.py` + `README.md`/`LICENSE.md` — из апстрима (481 схема).
  - Авторские правки дизассемблера/`dat2py.py`/`lib/parser.py` сохранены; в `ED9InstructionsSet.py` дописаны 3 ключа апстрима.
  - `compileall` → 0; авторские UI-файлы компилируются.
  - Отчёт: `work/logs/STAGE_1_REPORT.md`, план: `work/reports/MERGE_PLAN.md`.

## Следующий шаг
Этап 2: прочитать `PAC-Extractors/FPACker README.md` + исходники `FalcomPACTool-main/`; зафиксировать CLI в `reports/PAC_USAGE.md`; распаковать `table.pac`, `script.pac` и (в отдельную папку) `scene.pac` в `work/extract/`; построить `reports/INVENTORY.md`; пробы кодировки.

## Открытые проблемы / риски
- Формат FPAC известен из README apstрима: заголовок 16 байт (`FPAC`, n_files, first_addr, unk=1); записи 32 байта, CRC32(имени)^0xFFFFFFFF, сортировка по CRC; строки имён и данные — natural sort. Точную обратимость проверим на Этапе 3.
- FalcomPACTool — под Sora 1st, вероятно несовместим с Kyoto; основной — FPACker.exe.
- Роли: приоритет `script.pac`; `scene.pac` — в последнюю очередь и **только после вопроса пользователю**.
- Чужие незакоммиченные изменения в `KuroTools/Parser/Parser XLIF to Ecxel/` (bat command.txt / scene_table.xlsx) — НЕ мои, не трогаю.

## Жёсткие ограничения (напоминание)
- `Файлы для перевода/`, `ColdSteel-TranslationApp/`, `KuroTools-master_ForUPDATE/`, `DOCS/` — READ-ONLY.
- Правка любого файла в `KuroTools/` — только после бэкапа (baseline уже есть в `work/backup/`).
- Всё создаваемое — только внутри `work/`.
