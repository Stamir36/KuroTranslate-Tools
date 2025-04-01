@echo off
chcp 65001 > nul
set SCRIPT_DIR=%~dp0
set MAIN_PATH=%SCRIPT_DIR%

pip install colorama astunparse lxml customtkinter pygments deep_translator
start pythonw "%MAIN_PATH%\KuroTools\launcher.pyw"