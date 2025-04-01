@echo off
chcp 65001 > nul
set SCRIPT_DIR=%~dp0
set MAIN_PATH=%SCRIPT_DIR%..
set COMPILE_MODE=

:ASK_MODE
echo ====================================================
echo  Шаг 5: Компиляция PY в DAT
echo ====================================================
echo.
echo Выберите режим компиляции:
echo   1) Только файлы с переведенными строками (рекомендуется, по умолчанию)
echo   2) Все файлы в папке data_to_py
echo.
set /p MODE_CHOICE="Введите 1 или 2: "

if "%MODE_CHOICE%"=="1" (
    set COMPILE_MODE=--only-translated true
    goto COMPILE
)
if "%MODE_CHOICE%"=="2" (
    set COMPILE_MODE=--only-translated false
    goto COMPILE
)
echo Неверный ввод. Попробуйте снова.
goto ASK_MODE

:COMPILE
echo.
echo Запуск %MAIN_PATH%\py2dat_batch.py с опцией %COMPILE_MODE% ...
echo.

python "%MAIN_PATH%\py2dat_batch.py" %COMPILE_MODE%

echo.
echo ====================================================
echo Компиляция завершена.
echo Готовые .dat файлы находятся в папке %MAIN_PATH%\py_to_data
echo Проверьте консольный вывод на наличие ошибок компиляции.
echo ====================================================
echo.
pause