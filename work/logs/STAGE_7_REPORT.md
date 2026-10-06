# ЭТАП 7 — пайплайн сборки + RUNBOOK + итоговый отчёт

**Статус: ЗАВЕРШЁН.** Итоговый документ этапа — `work/reports/REPORT.md` (полный отчёт по всем этапам).
Здесь — краткая сводка и доказательства проверок.

## 1. Что сделано
- `work/tools/build_pacs.py` — оркестратор сборки: упаковывает `work/extract/{table,script,scene}` в `.pac`
  байт-точным пакером `pack_fpac.py` (с `--reference` на оригинал) и опционально сверяет результат с оригиналом.
- `work/RUNBOOK.md` — пошаговое руководство для переводчика (форматы, кодировка/разметка, команды, чек-лист,
  известные исключения).
- `work/reports/REPORT.md` — итоговый отчёт: результат по целям, этапы 0–7, форматы, отличия опкодов Kyoto,
  схемы, риски, план продолжения.
- Закоммичены `build_pacs.py`, `analyze_map.py`, `RUNBOOK.md`, `REPORT.md`; `.gitignore` дополнен `build/`,
  `stage4/` и крупными `translation_map/*.jsonl` (регенерируемы).

## 2. Проверки (acceptance)
| Проверка | Команда | Результат |
|---|---|---|
| Пересборка архивов байт-в-байт | `python work/tools/build_pacs.py --verify` | **table/script/scene = EXACT**, exit 0 |
| Round-trip таблиц | `python work/tools/batch_tbl.py work/extract/table` | `TOTAL=844 OK=842 DIFF=2 ERR=0` (99.8%) |
| Карта перевода | `python work/tools/build_translation_map.py` | 67 969 записей (29 395 уникальных) |
| Компиляция правок движка | `python -m py_compile KuroTools/{tbl2json,json2tbl}.py KuroTools/lib/parser.py` | OK |

Размеры собранных архивов: `table.pac` = 8 221 834 Б, `script.pac` = 51 012 476 Б, `scene.pac` = 61 110 404 Б —
совпадают с оригиналами при неизменённых данных.

## 3. Ограничения (перенесены в `REPORT.md` §7)
- `.dat`-сцены: функционально корректно, но не байт-в-байт (≈2.5% указателей) → обязателен игровой тест.
- `t_condition_info.tbl`, `t_costume.tbl`: нет корректных Kyoto-схем → только hex passthrough.
- Вопрос «читает ли игра loose-файлы поверх `.pac`» не подтверждён.

## 4. Воспроизведение
```bash
export PYTHONUTF8=1
python work/tools/build_pacs.py --src work/extract --out work/build/pac --orig "Файлы для перевода" --verify
```
