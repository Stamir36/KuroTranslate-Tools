@echo off
chcp 65001 > nul
set SCRIPT_DIR=%~dp0
set MAIN_PATH=%SCRIPT_DIR%..
echo ====================================================
echo  Шаг 1: Дизассемблирование DAT в PY
echo ====================================================
echo.
echo Запуск %MAIN_PATH%\dat2py_batch.py
echo Режим: Дизассемблер (--decompile False)
echo.

python "%MAIN_PATH%\dat2py_batch.py"

echo.
echo ====================================================
echo Дизассемблирование завершено.
echo Проверьте лог: %MAIN_PATH%\LogDisassembler.txt
echo Если были ошибки KeyError, дополните ED9InstructionsSet.py.
echo ====================================================
echo.
pause