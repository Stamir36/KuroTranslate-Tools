@echo off
chcp 65001 > nul
set SCRIPT_DIR=%~dp0
set MAIN_PATH=%SCRIPT_DIR%..
echo ====================================================
echo  Шаг 4: Создание карты строк XLIFF в JSON
echo ====================================================
echo.
echo ВНИМАНИЕ: Убедитесь, что вы перевели и сохранили файл %MAIN_PATH%\data_game_strings.xliff !
echo.
pause
echo Запуск %MAIN_PATH%\inject_translations.py ...
echo (Этот скрипт только создает %MAIN_PATH%\strings_map.json)
echo.

python "%MAIN_PATH%\inject_translations.py"

echo.
echo ====================================================
echo Создание карты строк завершено.
echo Файл карты строк: %MAIN_PATH%\strings_map.json
echo Теперь можно запускать компиляцию.
echo ====================================================
echo.
pause