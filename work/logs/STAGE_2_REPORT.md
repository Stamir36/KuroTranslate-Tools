# STAGE_2_REPORT.md — распаковка и инвентаризация

## Сделано
1. Прочитаны `FPACker README.md` и исходники `FalcomPACTool-main/` (`Program.cs`, `Archive/FPAC.cs`, `FPACHeader.cs`, `FPACEntry.cs`); CLI зафиксированы в `work/reports/PAC_USAGE.md`.
2. Скопированы оригиналы в `work/extract/` и распакованы **FPACker.exe** (с `msys-2.0.dll`):
   - `table.pac` → `work/extract/table/` — 844 `.tbl`, exit 0.
   - `script.pac` → `work/extract/script/` — 1016 `.dat`, exit 0.
   - `scene.pac` → `work/extract/scene/` — 1148 файлов (`.bin`/`.json`), exit 0.
   FalcomPACTool и самописный экстрактор не понадобились (FPACker отработал all-три без сбоев).
3. `work/reports/INVENTORY.md`: число файлов, гистограмма расширений, magic/first-64-bytes по расширениям, топ-20 по размеру, списки-кандидаты.
4. Пробы кодировки: UTF-8 подтверждён эмпирически (948/1016 `.dat` и 655/844 `.tbl` содержат осмысленный UTF-8-японский; конкретные смещения в INVENTORY §6).

## Наблюдения
- Магии: `.tbl` → `#TBL` (23 54 42 4C), `.dat` → `#scp` (23 73 63 70), `.json` → `JSON`, `.bin` — сырой.
- `script.pac` содержит не только сценарии: `scena/`=756 (диалоги, приоритет), `ai/`=132, `ani/`=115, `obj/`=13.
- `scene.pac` — это **не** сценарии-диалоги, а scene-ассеты (`.json`/`.bin`), поэтому в `scene.pac` текста-диалогов нет; работа с ним отложена в конец и по согласованию.
- Шрифтов (.itf) и текстур (.dds/.tex) в этих трёх архивах нет.
- `t_text.tbl` содержит строку `亰都ザナドゥ` — прямое подтверждение тайтла.

## Проблемы/риски
- `FPACker pack` по README **не гарантирует 1:1** — это главный риск для Этапа 3 (round-trip). План Б: `work/tools/pack_fpac.py`.
- Имена выходных каталогов задаются basename; при упаковке важно, чтобы FPACker сам расставил CRC/sort — проверим байт-в-байт.

## Артефакты
- `work/reports/INVENTORY.md`, `work/reports/PAC_USAGE.md`, `work/logs/encoding_probe.json`.
