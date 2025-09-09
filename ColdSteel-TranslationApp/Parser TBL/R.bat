@echo off
chcp 65001 > nul
set SCRIPT_DIR=%~dp0
set MAIN_PATH=%SCRIPT_DIR%
echo ====================================================
echo  Замена строк...
echo ====================================================
echo.

python "%MAIN_PATH%\Return.py"

echo.