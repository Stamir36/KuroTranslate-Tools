# KuroTranslate Tools — рабочий цикл через launcher

Запуск: `python launcher.pyw` (или двойной клик по `launcher.pyw`).
Прямо в окне — кнопки для **PAC**, **TBL** и **DAT**. Ниже — пошаговый цикл.

Проверено на `table.pac`: цепочка **unpack → tbl2json -g Kyoto → json2tbl → pack**
даёт архив, **байт-в-байт идентичный оригиналу** (844/844 таблиц, 0 ошибок).
Распаковка/упаковка сами по себе тоже байт-точные для всех трёх архивов.

## 0. PAC архивы (FPAC)
Кнопки в разделе **«PAC архивы (FPAC)»**:
* **Распаковать .pac** — выбираешь `.pac`; файлы раскладываются в
  `pac_unpacked/<имя>/…` с сохранением внутренних путей
  (`table/…`, `script/scena/…`, `scene/…`).
* **Собрать .pac** — выбираешь папку (напр. `pac_unpacked/table` или `json_to_tbl`);
  архив кладётся в `pac_packed/<префикс>.pac`. Префикс имён внутри архива
  (`table/script/scene`) берётся из имени папки; если имя другое — спросит.
* **Информация об архиве** — число файлов/размер.

> Байт-точность сохраняется, только если префикс совпадает (table/script/scene)
> и состав файлов не менялся.

## 1. TBL (таблицы)
Раздел **«Пакетная работа с TBL файлами»**:
1. **Разобрать .tbl** — выбираешь папку с `.tbl` (напр. `pac_unpacked/table`);
   JSON-ы складываются в `tbl_to_json/`.
   Перед запуском выбери **Игра (схема)** (по умолчанию `Kyoto`; `Авто` — подбор по размеру).
2. **Собрать .json в .tbl** — `tbl_to_json/` → `json_to_tbl/`.
3. **Парсинг TBL строк JSON в XLIFF** — извлечь строки в `tbl_strings.xliff` и обратно.
4. **Строки → TSV (для ИИ)** — экспорт всех переводимых строк в `strings.tsv`
   (колонки: `id  source  translation`). Удобно целиком отдать чатовому ИИ.
5. **Перевод TSV → строки** — после того как заполнил 3-ю колонку, импортирует
   перевод обратно в JSON в `tbl_to_json/` (по значению строки).
6. **Запустить XLIFF редактор** — встроенный GUI-редактор.

## 2. DAT (скрипты)
Раздел **«Работа с DAT файлами»** — 5 шагов:
1. Дизассемблировать DAT (`dat2py_batch.py`) — выбираешь папку с `.dat`.
2. Извлечь строки (`py_to_xliff.py`) → `data_game_strings.xliff`.
3. Редактировать перевод (XLIFF).
4. Создать карту перевода (`inject_translations.py`).
5. Скомпилировать DAT (`py2dat_batch.py`).

## 3. Полная сборка (пример)
```
1) Распаковать .pac            (table.pac → pac_unpacked/table)
2) Разобрать .tbl              (pac_unpacked/table → tbl_to_json, игра = Kyoto)
3) Строки → TSV (для ИИ)       → strings.tsv
4) перевести strings.tsv
5) Перевод TSV → строки        (применить перевод)
6) Собрать .json в .tbl        (tbl_to_json → json_to_tbl)
7) Собрать .pac                (json_to_tbl, префикс = table → pac_packed/table.pac)
```

## Файлы инструментов
| файл | назначение |
|---|---|
| `pac_tools.py` | unpack / pack / info FPAC (байт-точно) |
| `tbl2json.py` / `json2tbl.py` | TBL ↔ JSON (схемы в `schemas/`) |
| `strings_map.py` | JSON ↔ TSV (экспорт/импорт строк для ИИ) |
| `dat2py_batch.py` … `py2dat_batch.py` | цикл по DAT-скриптам |
| `xliff_editor_gui.py` | редактор XLIFF |

Схемы Kyoto-вариантов лежат в `schemas/` (meta) и `schemas/headers/` (варианты по играм).
