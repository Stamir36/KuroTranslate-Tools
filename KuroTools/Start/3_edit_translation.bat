@echo off
chcp 65001 > nul
set SCRIPT_DIR=%~dp0
set MAIN_PATH=%SCRIPT_DIR%..

echo ====================================================
echo  Шаг 3: Редактирование XLIFF строк
echo ====================================================
echo.
echo Запуск редактора. 
echo Файл: %MAIN_PATH%\data_game_strings.xliff
echo Пожалуйста, не злоупотребляйте автоматическим переводчиком.
echo.

python "%MAIN_PATH%\xliff_editor_gui.py" "%MAIN_PATH%\data_game_strings.xliff"

echo.
echo ====================================================
echo Редактирование XLIFF завершено.
echo Если вы полностью перевели файл, можете приступать к следующему шагу.
echo ====================================================
echo.
pause