@echo off
chcp 65001 > nul
set SCRIPT_DIR=%~dp0
set MAIN_PATH=%SCRIPT_DIR%
echo ====================================================
echo  Парсинг...
echo ====================================================
echo.

python "%MAIN_PATH%\Parser.py"

echo.