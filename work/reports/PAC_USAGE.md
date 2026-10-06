# PAC_USAGE.md — точные CLI для FPAC-архивов

## 1. FPACker (основной инструмент)
`PAC-Extractors/FPACker.exe` (by CoinKillerL). **Требует `msys-2.0.dll` рядом с exe** (лежит там же). Проверено: запуск из `PAC-Extractors/` работает.

Хелп (`./FPACker.exe` без аргументов):
```
No operation selected
FPACker by CoinKillerL - HELP
unpack-all <file.pac>          Unpack every file in the selected archive
pack <directory>               Pack every file in the selected directory and its subdirectories.
```

Команды:
```bash
# Распаковка: создаёт папку <basename без расширения> рядом с pac
cd PAC-Extractors
./FPACker.exe unpack-all "../work/extract/table.pac"   # -> ./table/
# Упаковка папки (имя выходного pac задаётся реализацией; проверяется на Этапе 3)
./FPACker.exe pack "../some/dir"
```
Наблюдение: `unpack-all` возвращает exit 0, но **не печатает прогресс**; каталог создаётся в CWD (не рядом с pac), имя = basename без расширения.

## 2. FalcomPACTool (fallback, только распаковка)
`PAC-Extractors/FalcomPACTool.exe` (by LinkOFF), создан под *Trails in the Sky 1st Chapter*.
CLI (из `FalcomPACTool-main/Program.cs`):
```
Usage: FalcomPACTool.exe extract <PAC File> <Output Folder>
```
**Только `extract`, упаковки нет.** Пересборку FalcomPACTool не умеет → для Этапа 3 не годится.

## 3. Формат FPAC (по `FPACker README.md` + `FalcomPACTool-main/Archive/*.cs`)
#### Header (16 байт)
```c
char fpac_magic[4];      // 'FPAC' = 0x46504143
u32  n_of_files;         // число файлов
u32  first_file_address; // адрес первого байта данных 1-го файла
u32  unk_magic;          // всегда 1
```
#### File Entry (32 байта), записи отсортированы по `filename_crc32` возрастанию
```c
u32 filename_crc32;         // crc32(имя без '\0') XOR 0xFFFFFFFF
u32 padding;                // = 0
u64 filename_string_address;// абсолютный адрес строки имени
u64 file_size;
u64 file_data_address;      // абсолютный адрес данных
```
Замечание: `FalcomPACTool` читает `filename_crc32`+`padding` как один `u64 Field00` (та же пара байт), а `NameOffset/DataSize/DataOffset` — как u64. Совпадает со спецификацией.
#### File
```
char* filename;   // NULL-terminated, полный путь
u8    data[file_size];
```
Строки имён и данные — в «natural sort»; для игры порядок не важен (README).

## 4. Стратегия на Этап 3
1. Базовая пересборка — `FPACker.exe pack`.
2. Распаковать результат, сравнить байт-в-байт с оригиналом.
3. При расхождениях (README прямо предупреждает: «Does not currently always make 1:1 FPACs») — дописать `work/tools/pack_fpac.py` по спецификации выше до пустого diff.
