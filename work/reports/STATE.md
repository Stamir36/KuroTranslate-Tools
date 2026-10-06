# STATE.md — состояние работ по русскому переводу KYOTO XANADU

Обновляется после каждого этапа. При возобновлении сессии — читать первым.

## Текущий этап
**ВСЕ ЭТАПЫ 0–8 ЗАВЕРШЕНЫ.** Техническая база готова; далее — перевод и игровой тест.
- **Покрытие таблиц текстом (Этап 8): 0 полностью потерянных .tbl.** JP-строк в хвостах
  27 359; извлечено 27 333 (остальные 26 — артефакты сканера, текст в JSON есть).
- Карта перевода: `work/translation_map/` (scripts 46 606 + tables 33 900).
- Пайплайн сборки: `work/tools/build_pacs.py` (3 архива EXACT).
- RUNBOOK: `work/RUNBOOK.md`; отчёты: `work/reports/REPORT.md`, `work/logs/STAGE_8_REPORT.md`.

## Сделано
- **Этап 0**: создано дерево `work/{reports,translation_map,logs,backup,extract,repack_check,decompiled,tbl_json}`; бэкап форка → `work/backup/KuroTools_baseline/`; окружение — Python 3.10.11.
- **Этап 1**: merge `KuroTools/` ← `KuroTools-master_ForUPDATE/` выполнен.
  - Схемы и `tbl2json.py`/`json2tbl.py` + `README.md`/`LICENSE.md` — из апстрима (481 схема).
  - Авторские правки дизассемблера/`dat2py.py`/`lib/parser.py` сохранены; в `ED9InstructionsSet.py` дописаны 3 ключа апстрима.
  - `compileall` → 0; авторские UI-файлы компилируются.
  - Отчёт: `work/logs/STAGE_1_REPORT.md`, план: `work/reports/MERGE_PLAN.md`.

- **Этап 2**: `PAC_USAGE.md`, `INVENTORY.md`, `encoding_probe.json`. Распакованы FPACker'ом: table=844 `.tbl`, script=1016 `.dat` (scena 756/ai 132/ani 115/obj 13), scene=1148 (`.bin`+`.json`). Кодировка строк — **UTF-8** (эмпирически). Магии: `#TBL`, `#scp`, `JSON`.

- **Этап 3**: ГОТОВО — пустой diff байт-в-байт на всех трёх архивах собственным `work/tools/pack_fpac.py`. FPACker не 1:1 на table (28/844). Выведен natural-sort (числа сравниваются лексикографически, регистронезависимо). Отчёт: `work/logs/STAGE_3_REPORT.md`.

- **Этап 4**: disasm работает на 756/756; дописано 162 опкода Kyoto; исправлены маркеры (нужен `--markers True`) и дедуп строк. Размер файла и код+строки восстанавливаются, но ПОЛНЫЙ байт-в-байт НЕ достигнут (остаток — слоты varout/struct-указателей). См. `work/logs/STAGE_4_REPORT.md` (§5 BLOCKED-остаток).

- **Этап 5**: ГОТОВО — round-trip таблиц **842/844 byte-exact (99.8%)**, 0 ошибок (было 90.0%). Устранены 3 бага `tbl2json.py`/`json2tbl.py`/`lib/parser.py` (потеря хвостового пула, потеря `length` у пустых таблиц, зацикливание на битом указателе) + O(n²)-дамп хвоста. 844 JSON сгенерированы. Отчёт: `work/logs/STAGE_5_REPORT.md`.

- **Этап 6**: ГОТОВО — карта перевода: `scripts.jsonl` (46 606), `tables.jsonl` (21 363), `MAP_INDEX.csv`; уникальных 29 395. Отчёт: `work/logs/STAGE_6_REPORT.md`.

- **Этап 7**: ГОТОВО — пайплайн сборки `work/tools/build_pacs.py` (все 3 архива **EXACT**), `work/RUNBOOK.md`, итоговый `work/reports/REPORT.md`.

## Следующий шаг
Перевод строк из `work/translation_map/` + `work/tbl_json/`, затем сборка (`json2tbl`, `py2dat_batch`) и игровой тест. См. §8 в `work/reports/REPORT.md`.

## Этап 8 (покрытие .tbl текстом)
- Дозакрыты схемы (`-g Kyoto`) для 21 из 41 «потерянных» + `t_event`/`t_todo`/`t_keyword`:
  byte-exact И текст (`t_status` 299, `t_help` 406, `t_team_name` 450, `t_event` 844,
  `t_realtime_tutorial` 453, `t_monster_note` 245, `t_dlc` 90, `t_chapter`, `t_skill` и др.).
- Для таблиц без выводимой схемы — **редактируемый текстовый пул**: `tbl2json` кладёт
  `tail_strings` (`{offset,len,text}`), `json2tbl` сплайсит правки и пересчитывает
  8-выровненные указатели в hex-записях; без правок — byte-exact. Покрыты `t_voice`
  (9001, идентификаторы голоса — не для перевода), `t_npc_c*`, `t_place`, `t_chr_name`,
  `t_lookpoint`, `t_mapjump`, `t_action_*` и др.
- Точная диагностика — `work/tools/diagnose_tbl_text2.py` (старая рвала строки по `\n`).
- Round-trip остался **842/844**, 0 ошибок (те же 2 DIFF: `t_condition_info`, `t_costume`).

## Открытый BLOCKED
- Этап 4: не байт-в-байт (указатели varout/struct на равные строки в разных ячейках). Функционально корректно, но требует доработки порядка строк.
- Этап 5: `t_condition_info.tbl`, `t_costume.tbl` — совпадают по размеру, но `toffset`-пул собирается в ином порядке (подходит чужая схема Kai/Kuro1). Нужны Kyoto-схемы `ConditionInfoTableData`/`CostumeAttachOffset`. До тех пор — только hex-passthrough, не редактировать.

## Открытые проблемы / риски
- Формат FPAC известен из README apstрима: заголовок 16 байт (`FPAC`, n_files, first_addr, unk=1); записи 32 байта, CRC32(имени)^0xFFFFFFFF, сортировка по CRC; строки имён и данные — natural sort. Точную обратимость проверим на Этапе 3.
- FalcomPACTool — под Sora 1st, вероятно несовместим с Kyoto; основной — FPACker.exe.
- Роли: приоритет `script.pac`; `scene.pac` — в последнюю очередь и **только после вопроса пользователю**.
- Чужие незакоммиченные изменения в `KuroTools/Parser/Parser XLIF to Ecxel/` (bat command.txt / scene_table.xlsx) — НЕ мои, не трогаю.

## Жёсткие ограничения (напоминание)
- `Файлы для перевода/`, `ColdSteel-TranslationApp/`, `KuroTools-master_ForUPDATE/`, `DOCS/` — READ-ONLY.
- Правка любого файла в `KuroTools/` — только после бэкапа (baseline уже есть в `work/backup/`).
- Всё создаваемое — только внутри `work/`.
