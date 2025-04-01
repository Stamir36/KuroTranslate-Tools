@echo off
chcp 65001 > nul
set SCRIPT_DIR=%~dp0
set MAIN_PATH=%SCRIPT_DIR%..
echo ====================================================
echo  Шаг 2: Извлечение строк PY в XLIFF
echo ====================================================
echo.
echo ВНИМАНИЕ: Убедитесь, что сделали резервную копию папки %MAIN_PATH%\data_to_py !
echo (Хотя этот скрипт не должен изменять .py файлы)
echo.
pause
echo Запуск %MAIN_PATH%\py_to_xliff.py ...
echo.

python "%MAIN_PATH%\py_to_xliff.py"

echo.
echo ====================================================
echo Извлечение строк завершено.
echo Файл для перевода: %MAIN_PATH%\data_game_strings.xliff
echo Карта строк (начальная): %MAIN_PATH%\strings_map.json
echo Теперь отредактируйте XLIFF файл.
echo ====================================================
echo.
pause