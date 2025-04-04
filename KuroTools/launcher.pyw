# --- START OF FILE launcher.py ---

import tkinter
import tkinter.messagebox
import tkinter.filedialog
import customtkinter # type: ignore
import subprocess
import threading
import queue
import os
import sys
import signal
import re
import time
import platform
import shutil
import json           # Added for JSON operations
import uuid           # Added for generating unique IDs
import xml.etree.ElementTree as ET # Added for XLIFF operations
import xml.dom.minidom # Added for pretty printing XLIFF
import string as string_module # For character checks

# --- Configuration ---
customtkinter.set_appearance_mode("System")
customtkinter.set_default_color_theme("blue")

script_dir = os.path.dirname(os.path.abspath(__file__))
# --- Path Detection Logic ---
if os.path.basename(script_dir).lower() == "start":
     MAIN_PATH = os.path.dirname(script_dir)
     START_DIR = script_dir
elif os.path.isdir(os.path.join(script_dir, "Start")):
     MAIN_PATH = script_dir
     START_DIR = os.path.join(script_dir, "Start")
else:
     MAIN_PATH = script_dir
     START_DIR = os.path.join(MAIN_PATH, "Start")
     print(f"Warning: Could not find 'Start' directory conventionally. Assuming MAIN_PATH='{MAIN_PATH}' and START_DIR='{START_DIR}'")

# --- Constants ---
PARSER_FOLDER_NAME = "Parser"
PARSER_FOLDER_PATH = os.path.join(MAIN_PATH, PARSER_FOLDER_NAME)
DATA_TO_PY_FOLDER = "data_to_py"
DATA_TO_PY_DECOMPILE_TEMP_FOLDER = "data_to_py_DECOMPILE"
# --- TBL Constants ---
TBL_TO_JSON_FOLDER = "tbl_to_json" # Relative to MAIN_PATH (Source for parsing/assembly)
JSON_TO_TBL_FOLDER = "json_to_tbl" # Relative to MAIN_PATH (Output for assembly)
TBL_JSON_FOLDER_PATH = os.path.join(MAIN_PATH, TBL_TO_JSON_FOLDER) # Full path to JSONs
TBL_ASSEMBLED_FOLDER_PATH = os.path.join(MAIN_PATH, JSON_TO_TBL_FOLDER) # Full path for assembled TBLs
TBL_DISASSEMBLE_SCRIPT = "tbl2json.py"
TBL_ASSEMBLE_SCRIPT = "json2tbl.py"
TBL_STRINGS_XLIFF_FILE = "tbl_strings.xliff" # Combined XLIFF file in MAIN_PATH
TBL_XLIFF_FILE_PATH = os.path.join(MAIN_PATH, TBL_STRINGS_XLIFF_FILE)
# --- TBL String Filter Constants ---
TBL_MIN_STRING_LENGTH = 3     # Min length for extraction
TBL_REQUIRE_SPACE = True      # Require space (unless non-ASCII)
TBL_IGNORE_TBL_IDS = True     # Ignore strings starting with 'tbl_'
TBL_IGNORE_UNDERSCORE_ONLY = True # Ignore 'AniReset', 'chr001' style IDs
TBL_IGNORE_NUMERIC_PUNCT = True # Ignore strings with only numbers/punctuation/spaces
# --- END TBL Constants ---

# --- Python Executable ---
PYTHON_EXECUTABLE = sys.executable

# --- Encoding ---
CONSOLE_ENCODING = 'utf-8'

# --- Language Strings ---
# (Keep the extensive LANGUAGES dictionary from the previous version)
LANGUAGES = {
    'en': {
        'title': "KuroTranslate Tools",
        'status_idle': "Status: Idle",
        'status_running': "Status: Running {script_name}...",
        'status_finished': "Status: Finished {script_name} successfully.",
        'status_error': "Status: Error occurred",
        'status_terminated': "Status: Terminated / Idle",
        'log_running': "--- Running {script_name} {args} ---",
        'log_finished': "--- {status_message} ---",
        'log_error': "!!! {error_message} !!!",
        'log_input_sent': "--- Sending input: {user_input} ---",
        'log_input_cancelled': "--- Input cancelled by user ---",
        'log_terminate_attempt': "--- Attempting to terminate script ---",
        'log_terminate_error': "ERROR: Could not terminate process: {e}",
        'error_dir_not_found': "ERROR: Main project directory not found or 'Start' folder missing in: {path}\nCannot determine script paths.",
        'error_script_not_found': "ERROR: Script not found: {path}",
        'error_script_not_found_run': "ERROR: Cannot run. Script not found: {path}",
        'error_input_fail': "ERROR: Cannot send input, process not running or stdin not available.",
        'error_send_input_fail': "ERROR: Failed to send input to script: {e}",
        'error_unexpected': "An unexpected error occurred: {e}",
        'error_open_folder': "ERROR: Could not open folder: {path}\n{e}",
        'info_scripts_found': "\nProject path configured: {path}",
        'info_found_script': "Ready: {script_name}",
        'info_opening_folder': "Opening folder: {path}",
        'warn_already_running': "Busy",
        'warn_already_running_msg': "Another script is already running.",
        'confirm_exit_title': "Running Script",
        'confirm_exit_msg': "A script is currently running. Do you want to terminate it and exit?",
        'input_prompt_title': "Script Input Needed",
        'input_prompt_default': "Enter input for script:",
        'compile_mode_title': "Compilation Mode",
        'compile_mode_prompt': "Select compilation mode:",
        'compile_mode_1': "1) Only files with translated strings (Recommended)",
        'compile_mode_2': "2) All files in data_to_py folder",
        'compile_mode_invalid': "Invalid input. Please enter 1 or 2.",
        'dat_files_label': "Work with DAT files",
        'button_1_disassemble': "1. Disassemble DAT",
        'button_2_extract': "2. Extract Strings",
        'button_3_edit': "3. Edit Translation (DAT XLIFF)",
        'button_4_create_map': "4. Create Translation Map",
        'button_5_compile': "5. Compile DAT",
        'tbl_files_label': "Batch work with TBL files", # Updated Section Title
        'button_open_parser': "Open parsing folder", # Kept original text, opens MAIN_PATH now
        'button_tbl_edit': "Launch XLIFF editor", # Changed from "Launch XLIFF Editor"
        'xliff_editor_note': "XLIFF editor has auto-translation features.",
        'lang_select_label': "Language:",
        'terminate_button': "Terminate Script",
        'startup_error_title': "Startup Error",
        'startup_error_python_not_found': "Python executable not found or invalid: {path}\nPlease ensure Python is installed and accessible.",
        'startup_error_main_path_not_found': "Main project directory ({main_path}) or Start directory ({start_path}) not found.\nPlease ensure the folder structure is correct. Exiting.",
        'warning_title': "Warning",
        'warning_arg_file_not_found': "Argument file not found for {script}: {arg_path}",
        'dat_folder_prompt_title': "{button_text} - Select Folder",
        'dat_folder_prompt_log': "Prompting for DAT folder path...",
        'dat_folder_selected_log': "Selected DAT folder: {path}",
        'dat_folder_cancel_log': "Folder selection cancelled.",
        'status_extract_running': "Status: Extracting strings...",
        'log_extract_start': "--- Starting String Extraction Sequence ---",
        'log_rename_orig_to_temp': "Renaming '{orig}' to '{temp}'...",
        'log_rename_failed': "ERROR: Failed to rename '{orig}' to '{temp}': {e}",
        'log_run_disasm_extract': "Running disassembly (extraction mode)...",
        'log_run_disasm_extract_fail': "ERROR: Disassembly (extraction mode) failed. Aborting sequence.",
        'log_run_pytoxliff': "Running string extraction from .py files...",
        'log_run_pytoxliff_fail': "ERROR: String extraction script failed.",
        'log_delete_temp_py': "Deleting temporary folder '{path}'...",
        'log_delete_failed': "ERROR: Failed to delete temporary folder '{path}': {e}",
        'log_rename_temp_to_orig': "Restoring original folder '{temp}' to '{orig}'...",
        'log_extract_complete': "--- String Extraction Sequence Completed ---",
        'log_extract_complete_errors': "--- String Extraction Sequence Completed with errors ---",
        'error_no_dat_path': "ERROR: Cannot extract strings. Please run Step 1 (Disassemble DAT) first or select the DAT folder now.",
        'error_orig_folder_missing': "Warning: Original folder '{path}' not found. Skipping initial rename.",
        'error_temp_folder_missing_del': "Warning: Temporary folder '{path}' not found for deletion.",
        'error_temp_folder_missing_restore': "ERROR: Cannot restore original folder. Temporary backup '{path}' not found.",
        'error_restore_failed': "CRITICAL ERROR: Failed to restore original folder '{orig}' from '{temp}': {e}. Manual restoration might be needed.",
        'extract_prompt_dat_folder_title': "Extract Strings - Select DAT Folder",
        # --- TBL Strings ---
        'button_tbl_disassemble': "Disassemble .tbl", # UI Change
        'button_tbl_assemble': "Assemble .json to .tbl", # UI Change
        'button_tbl_parse_json_xliff': "Parse TBL strings JSON to XLIFF file", # New Button
        'tbl_folder_prompt_title_disassemble': "Batch Disassemble TBL - Select Folder with TBLs",
        'tbl_folder_prompt_log': "Prompting for TBL folder path...",
        'tbl_folder_selected_log': "Selected TBL folder: {path}",
        'tbl_folder_cancel_log': "Folder selection cancelled.",
        'log_tbl_disassemble_start': "--- Starting TBL to JSON Batch Disassembly ---",
        'log_tbl_assemble_start': "--- Starting JSON to TBL Batch Assembly (from '{source_folder}') ---",
        'log_processing_file': "Processing: {filename}",
        'log_move_file_success': "Moved result to: {target_path}",
        'log_move_file_failed': "ERROR: Failed to move '{source}' to '{target}': {e}",
        'log_move_file_source_missing': "WARNING: Expected output file '{source}' not found in '{search_dir}' after script ran.",
        'log_skipping_file': "Skipping file (error): {filename}",
        'log_batch_complete': "--- Batch process completed. Success: {success_count}, Failed: {fail_count} ---",
        'log_batch_complete_errors': "--- Batch process completed with errors. Success: {success_count}, Failed: {fail_count} ---",
        'error_script_missing_batch': "ERROR: Required script '{script_name}' not found. Cannot start batch.",
        'error_no_files_found': "No '{extension}' files found in the source folder: {folder_path}",
        'error_create_folder_failed': "ERROR: Failed to create output directory '{path}': {e}",
        'error_source_folder_not_found': "ERROR: Source folder not found: {path}", # General source folder error
        'status_tbl_disassembling': "Status: Batch Disassembling TBL files...",
        'status_tbl_assembling': "Status: Batch Assembling TBL files...",
        # New Parsing Strings
        'tbl_parse_dialog_title': "TBL JSON/XLIFF Parsing",
        'tbl_parse_json_to_xliff': "JSON to XLIFF (Extract strings)", # Button Text
        'tbl_parse_xliff_to_json': "XLIFF to JSON (Inject strings)", # Button Text
        'tbl_parse_prompt_text': "Choose parsing direction:", # Dialog Label Text
        'tbl_parse_invalid_choice': "Invalid choice selected.", # Error (not used with button dialog)
        'status_tbl_parsing_j2x': "Status: Extracting TBL strings from JSON to XLIFF...",
        'status_tbl_parsing_x2j': "Status: Injecting TBL strings from XLIFF to JSON...",
        'log_tbl_parse_j2x_start': "--- Starting JSON to XLIFF TBL String Extraction ---",
        'log_tbl_parse_x2j_start': "--- Starting XLIFF to JSON TBL String Injection ---",
        'log_tbl_parse_reading_json': "Reading JSON: {filename}",
        'log_tbl_parse_writing_json': "Writing modified JSON: {filename}",
        'log_tbl_parse_creating_xliff': "Creating combined XLIFF file: {filename}",
        'log_tbl_parse_reading_xliff': "Reading XLIFF file: {filename}",
        'log_tbl_parse_found_strings': "Found {count} new translatable strings in {filename}.",
        'log_tbl_parse_total_strings': "Total unique strings extracted: {count}.",
        'log_tbl_parse_no_strings': "No translatable strings found to extract.",
        'log_tbl_parse_replacing_ids': "Replacing IDs in JSON: {filename}",
        'log_tbl_parse_map_loaded': "Loaded {count} translations from XLIFF.",
        'log_tbl_parse_complete': "--- TBL Parsing process completed. ---",
        'log_tbl_parse_complete_errors': "--- TBL Parsing process completed with errors. ---",
        'error_tbl_parse_read_json': "ERROR reading JSON file {filename}: {e}",
        'error_tbl_parse_write_json': "ERROR writing JSON file {filename}: {e}",
        'error_tbl_parse_read_xliff': "ERROR reading XLIFF file {filename}: {e}",
        'error_tbl_parse_write_xliff': "ERROR writing XLIFF file {filename}: {e}",
        'error_tbl_parse_no_xliff': "ERROR: XLIFF file not found for injection: {filename}",
        'error_tbl_parse_no_map': "ERROR: Could not load translations from XLIFF: {filename}",
        # --- END TBL Strings ---
    },
    'ru': {
        'title': "KuroTranslate Tools",
        'status_idle': "Статус: Ожидание",
        'status_running': "Статус: Выполняется {script_name}...",
        'status_finished': "Статус: {script_name} завершен успешно.",
        'status_error': "Статус: Произошла ошибка",
        'status_terminated': "Статус: Прервано / Ожидание",
        'log_running': "--- Запуск {script_name} {args} ---",
        'log_finished': "--- {status_message} ---",
        'log_error': "!!! {error_message} !!!",
        'log_input_sent': "--- Отправка ввода: {user_input} ---",
        'log_input_cancelled': "--- Ввод отменен пользователем ---",
        'log_terminate_attempt': "--- Попытка прервать скрипт ---",
        'log_terminate_error': "ОШИБКА: Не удалось прервать процесс: {e}",
        'error_dir_not_found': "ОШИБКА: Основная директория проекта не найдена или отсутствует папка 'Start' в: {path}\nНе могу определить пути к скриптам.",
        'error_script_not_found': "ОШИБКА: Скрипт не найден: {path}",
        'error_script_not_found_run': "ОШИБКА: Не могу запустить. Скрипт не найден: {path}",
        'error_input_fail': "ОШИБКА: Не могу отправить ввод, процесс не запущен или stdin недоступен.",
        'error_send_input_fail': "ОШИБКА: Не удалось отправить ввод скрипту: {e}",
        'error_unexpected': "Произошла непредвиденная ошибка: {e}",
        'error_open_folder': "ОШИБКА: Не удалось открыть папку: {path}\n{e}",
        'info_scripts_found': "\nПуть к проекту настроен: {path}",
        'info_found_script': "Готов: {script_name}",
        'info_opening_folder': "Открываю папку: {path}",
        'warn_already_running': "Занято",
        'warn_already_running_msg': "Другой скрипт уже выполняется.",
        'confirm_exit_title': "Выполняется скрипт",
        'confirm_exit_msg': "Скрипт еще выполняется. Прервать его и выйти?",
        'input_prompt_title': "Требуется ввод для скрипта",
        'input_prompt_default': "Введите данные для скрипта:",
        'compile_mode_title': "Режим компиляции",
        'compile_mode_prompt': "Выберите режим компиляции:",
        'compile_mode_1': "1) Только файлы с переведенными строками (Рекомендуется)",
        'compile_mode_2': "2) Все файлы в папке data_to_py",
        'compile_mode_invalid': "Неверный ввод. Введите 1 или 2.",
        'dat_files_label': "Работа с DAT файлами",
        'button_1_disassemble': "1. Дизассемблировать DAT",
        'button_2_extract': "2. Извлечь строки",
        'button_3_edit': "3. Редактировать перевод (DAT XLIFF)",
        'button_4_create_map': "4. Создать карту перевода",
        'button_5_compile': "5. Скомпилировать DAT",
        'tbl_files_label': "Пакетная работа с TBL файлами", # Обновлен заголовок секции
        'button_open_parser': "Открыть папку парсинга", # Текст сохранен, открывает MAIN_PATH
        'button_tbl_edit': "Запустить XLIFF редактор", # Текст из скриншота
        'xliff_editor_note': "XLIFF редактор имеет функции автоматического перевода.",
        'lang_select_label': "Язык:",
        'terminate_button': "Прервать Скрипт",
        'startup_error_title': "Ошибка Запуска",
        'startup_error_python_not_found': "Исполняемый файл Python не найден или неверен: {path}\nУбедитесь, что Python установлен и доступен.",
        'startup_error_main_path_not_found': "Основная директория проекта ({main_path}) или папка Start ({start_path}) не найдена.\nУбедитесь в правильности структуры папок. Выход.",
        'warning_title': "Предупреждение",
        'warning_arg_file_not_found': "Файл аргумента не найден для {script}: {arg_path}",
        'dat_folder_prompt_title': "{button_text} - Выберите папку",
        'dat_folder_prompt_log': "Запрос пути к папке с DAT...",
        'dat_folder_selected_log': "Выбрана папка DAT: {path}",
        'dat_folder_cancel_log': "Выбор папки отменен.",
        'status_extract_running': "Статус: Извлечение строк...",
        'log_extract_start': "--- Запуск последовательности извлечения строк ---",
        'log_rename_orig_to_temp': "Переименование '{orig}' в '{temp}'...",
        'log_rename_failed': "ОШИБКА: Не удалось переименовать '{orig}' в '{temp}': {e}",
        'log_run_disasm_extract': "Запуск дизассемблирования (режим извлечения)...",
        'log_run_disasm_extract_fail': "ОШИБКА: Дизассемблирование (режим извлечения) не удалось. Отмена последовательности.",
        'log_run_pytoxliff': "Запуск извлечения строк из .py файлов...",
        'log_run_pytoxliff_fail': "ОШИБКА: Скрипт извлечения строк не удался.",
        'log_delete_temp_py': "Удаление временной папки '{path}'...",
        'log_delete_failed': "ОШИБКА: Не удалось удалить временную папку '{path}': {e}",
        'log_rename_temp_to_orig': "Восстановление исходной папки '{temp}' в '{orig}'...",
        'log_extract_complete': "--- Последовательность извлечения строк завершена ---",
        'log_extract_complete_errors': "--- Последовательность извлечения строк завершена с ошибками ---",
        'error_no_dat_path': "ОШИБКА: Невозможно извлечь строки. Сначала выполните Шаг 1 (Дизассемблировать DAT) или выберите папку DAT сейчас.",
        'error_orig_folder_missing': "Предупреждение: Исходная папка '{path}' не найдена. Пропуск начального переименования.",
        'error_temp_folder_missing_del': "Предупреждение: Временная папка '{path}' не найдена для удаления.",
        'error_temp_folder_missing_restore': "ОШИБКА: Невозможно восстановить исходную папку. Временная копия '{path}' не найдена.",
        'error_restore_failed': "КРИТИЧЕСКАЯ ОШИБКА: Не удалось восстановить исходную папку '{orig}' из '{temp}': {e}. Может потребоваться ручное восстановление.",
        'extract_prompt_dat_folder_title': "Извлечь строки - Выберите папку DAT",
        # --- TBL Strings ---
        'button_tbl_disassemble': "Разобрать .tbl", # Текст из скриншота
        'button_tbl_assemble': "Собрать .json в .tbl", # Текст из скриншота
        'button_tbl_parse_json_xliff': "Парсинг TBL строк JSON в XLIFF файл", # Новая кнопка
        'tbl_folder_prompt_title_disassemble': "Пакетный разбор TBL - Выберите папку с TBL",
        'tbl_folder_prompt_log': "Запрос пути к папке с TBL...",
        'tbl_folder_selected_log': "Выбрана папка TBL: {path}",
        'tbl_folder_cancel_log': "Выбор папки отменен.",
        'log_tbl_disassemble_start': "--- Запуск пакетного разбора TBL в JSON ---",
        'log_tbl_assemble_start': "--- Запуск пакетной сборки TBL из JSON (из '{source_folder}') ---",
        'log_processing_file': "Обработка: {filename}",
        'log_move_file_success': "Результат перемещен в: {target_path}",
        'log_move_file_failed': "ОШИБКА: Не удалось переместить '{source}' в '{target}': {e}",
        'log_move_file_source_missing': "ВНИМАНИЕ: Ожидаемый файл результата '{source}' не найден в '{search_dir}' после выполнения скрипта.",
        'log_skipping_file': "Пропуск файла (ошибка): {filename}",
        'log_batch_complete': "--- Пакетная обработка завершена. Успешно: {success_count}, Ошибок: {fail_count} ---",
        'log_batch_complete_errors': "--- Пакетная обработка завершена с ошибками. Успешно: {success_count}, Ошибок: {fail_count} ---",
        'error_script_missing_batch': "ОШИБКА: Не найден требуемый скрипт '{script_name}'. Не могу начать пакетную обработку.",
        'error_no_files_found': "В исходной папке не найдены файлы '{extension}': {folder_path}",
        'error_create_folder_failed': "ОШИБКА: Не удалось создать папку для результатов '{path}': {e}",
        'error_source_folder_not_found': "ОШИБКА: Не найдена исходная папка: {path}", # Общая ошибка
        'status_tbl_disassembling': "Статус: Пакетный разбор TBL файлов...",
        'status_tbl_assembling': "Статус: Пакетная сборка TBL файлов...",
         # Новые строки для парсинга
        'tbl_parse_dialog_title': "Парсинг TBL JSON/XLIFF",
        'tbl_parse_json_to_xliff': "JSON в XLIFF (Извлечь строки)", # Текст кнопки
        'tbl_parse_xliff_to_json': "XLIFF в JSON (Внедрить строки)", # Текст кнопки
        'tbl_parse_prompt_text': "Выберите направление парсинга:", # Текст метки в диалоге
        'tbl_parse_invalid_choice': "Выбран неверный вариант.", # Ошибка (не используется с кнопками)
        'status_tbl_parsing_j2x': "Статус: Извлечение TBL строк из JSON в XLIFF...",
        'status_tbl_parsing_x2j': "Статус: Внедрение TBL строк из XLIFF в JSON...",
        'log_tbl_parse_j2x_start': "--- Запуск извлечения TBL строк из JSON в XLIFF ---",
        'log_tbl_parse_x2j_start': "--- Запуск внедрения TBL строк из XLIFF в JSON ---",
        'log_tbl_parse_reading_json': "Чтение JSON: {filename}",
        'log_tbl_parse_writing_json': "Запись измененного JSON: {filename}",
        'log_tbl_parse_creating_xliff': "Создание общего XLIFF файла: {filename}",
        'log_tbl_parse_reading_xliff': "Чтение XLIFF файла: {filename}",
        'log_tbl_parse_found_strings': "Найдено {count} новых переводимых строк в {filename}.",
        'log_tbl_parse_total_strings': "Всего извлечено уникальных строк: {count}.",
        'log_tbl_parse_no_strings': "Не найдено переводимых строк для извлечения.",
        'log_tbl_parse_replacing_ids': "Замена ID в JSON: {filename}",
        'log_tbl_parse_map_loaded': "Загружено {count} переводов из XLIFF.",
        'log_tbl_parse_complete': "--- Процесс парсинга TBL завершен. ---",
        'log_tbl_parse_complete_errors': "--- Процесс парсинга TBL завершен с ошибками. ---",
        'error_tbl_parse_read_json': "ОШИБКА чтения JSON файла {filename}: {e}",
        'error_tbl_parse_write_json': "ОШИБКА записи JSON файла {filename}: {e}",
        'error_tbl_parse_read_xliff': "ОШИБКА чтения XLIFF файла {filename}: {e}",
        'error_tbl_parse_write_xliff': "ОШИБКА записи XLIFF файла {filename}: {e}",
        'error_tbl_parse_no_xliff': "ОШИБКА: XLIFF файл не найден для внедрения: {filename}",
        'error_tbl_parse_no_map': "ОШИБКА: Не удалось загрузить переводы из XLIFF: {filename}",
        # --- END TBL Strings ---
    }
}

# --- ANSI Color Parsing ---
ANSI_ESCAPE_REGEX = re.compile(r'\x1B\[[0-?]*[ -/]*[@-~]')
ANSI_COLOR_REGEX = re.compile(r'\x1B\[(\d+(?:;\d+)*)m')
ANSI_CODE_TO_TAG = { '0':'reset','1':'bold','4':'underline','30':'fg_black','31':'fg_red','32':'fg_green','33':'fg_yellow','34':'fg_blue','35':'fg_magenta','36':'fg_cyan','37':'fg_white','90':'fg_bright_black','91':'fg_bright_red','92':'fg_bright_green','93':'fg_bright_yellow','94':'fg_bright_blue','95':'fg_bright_magenta','96':'fg_bright_cyan','97':'fg_bright_white','40':'bg_black','41':'bg_red','42':'bg_green','43':'bg_yellow','44':'bg_blue','45':'bg_magenta','46':'bg_cyan','47':'bg_white','100':'bg_bright_black','101':'bg_bright_red','102':'bg_bright_green','103':'bg_bright_yellow','104':'bg_bright_blue','105':'bg_bright_magenta','106':'bg_bright_cyan','107':'bg_bright_white' }

class App(customtkinter.CTk):
    def __init__(self):
        super().__init__()
        self.current_lang="ru"
        self.languages_map={"Русский":"ru","English":"en"}
        if not os.path.isdir(MAIN_PATH) or not os.path.isdir(START_DIR):
            title=LANGUAGES[self.current_lang].get('startup_error_title',"Error")
            msg=LANGUAGES[self.current_lang].get('startup_error_main_path_not_found',"Dir error").format(main_path=MAIN_PATH,start_path=START_DIR)
            tkinter.messagebox.showerror(title,msg)
            sys.exit(1)
        xliff_dat_path=os.path.join(MAIN_PATH,"data_game_strings.xliff")
        self.script_definitions={'1_disassemble':("dat2py_batch.py",[]),'2_extract':("py_to_xliff.py",[]),'3_edit':("xliff_editor_gui.py",[xliff_dat_path]),'4_create_map':("inject_translations.py",[]),'5_compile':("py2dat_batch.py",[]),'tbl_disassemble_check':(TBL_DISASSEMBLE_SCRIPT,[]),'tbl_assemble_check':(TBL_ASSEMBLE_SCRIPT,[]),'tbl_xliff_edit_check':("xliff_editor_gui.py",[])}
        self.dat_button_order=['1_disassemble','2_extract','3_edit','4_create_map','5_compile']
        self.title(self.get_string('title'))
        self.geometry(f"{1100}x720")
        self.grid_columnconfigure(0,weight=3)
        self.grid_columnconfigure(1,weight=1)
        self.grid_rowconfigure(0,weight=1)
        self.grid_rowconfigure(1,weight=0)
        dfont=customtkinter.CTkFont()
        bfont=customtkinter.CTkFont(family=dfont.cget("family"),size=dfont.cget("size"),weight="bold")
        self.output_textbox=customtkinter.CTkTextbox(self,width=700,corner_radius=5,font=bfont)
        self.output_textbox.grid(row=0,column=0,padx=(20,10),pady=(20,20),sticky="nsew")
        self.output_textbox.configure(state="disabled",wrap="word")
        self._configure_text_tags()
        self.button_frame=customtkinter.CTkFrame(self,width=250,corner_radius=5)
        self.button_frame.grid(row=0,column=1,padx=(10,20),pady=(20,20),sticky="nsew")
        self.button_frame.grid_columnconfigure(0,weight=1)
        self.button_frame.grid_columnconfigure(1,weight=1)
        row=0
        self.buttons={}
        self.dat_label=customtkinter.CTkLabel(self.button_frame,text=self.get_string('dat_files_label'),font=customtkinter.CTkFont(weight="bold"))
        self.dat_label.grid(row=row,column=0,columnspan=2,padx=20,pady=(10,10),sticky="ew")
        row+=1
        for i, sid in enumerate(self.dat_button_order):
            bkey=f"button_{sid}"
            btext=self.get_string(bkey,default=sid.replace("_"," ").title())
            btn=customtkinter.CTkButton(self.button_frame,text=btext)
            btn.grid(row=row+i,column=0,columnspan=2,padx=20,pady=(5,5),sticky="ew")
            if sid=='1_disassemble':
                btn.configure(command=self.prompt_for_dat_path_and_run)
            elif sid=='2_extract':
                btn.configure(command=self.run_extract_strings_sequence)
            elif sid=='5_compile':
                btn.configure(command=lambda s=sid: self.prompt_compile_mode_and_run(s))
            else:
                btn.configure(command=lambda s=sid: self.run_script_thread(s))
            self.buttons[sid]=btn
        row+=len(self.dat_button_order)
        self.tbl_label=customtkinter.CTkLabel(self.button_frame,text=self.get_string('tbl_files_label'),font=customtkinter.CTkFont(weight="bold"))
        self.tbl_label.grid(row=row,column=0,columnspan=2,padx=20,pady=(15,10),sticky="ew")
        row+=1
        self.tbl_disassemble_button=customtkinter.CTkButton(self.button_frame,text=self.get_string('button_tbl_disassemble'),command=lambda: self.run_batch_tbl_process('disassemble'))
        self.tbl_disassemble_button.grid(row=row,column=0,padx=(20,5),pady=(5,5),sticky="ew")
        self.buttons['tbl_disassemble']=self.tbl_disassemble_button
        self.tbl_assemble_button=customtkinter.CTkButton(self.button_frame,text=self.get_string('button_tbl_assemble'),command=lambda: self.run_batch_tbl_process('assemble'))
        self.tbl_assemble_button.grid(row=row,column=1,padx=(5,20),pady=(5,5),sticky="ew")
        self.buttons['tbl_assemble']=self.tbl_assemble_button
        row+=1
        self.tbl_parse_button=customtkinter.CTkButton(self.button_frame,text=self.get_string('button_tbl_parse_json_xliff'),command=self.prompt_tbl_parse_mode)
        self.tbl_parse_button.grid(row=row,column=0,columnspan=2,padx=20,pady=(5,5),sticky="ew")
        self.buttons['tbl_parse_json_xliff']=self.tbl_parse_button
        row+=1
        self.open_parser_button=customtkinter.CTkButton(self.button_frame,text=self.get_string('button_open_parser'),command=self.open_main_path_folder)
        self.open_parser_button.grid(row=row,column=0,columnspan=2,padx=20,pady=(5,5),sticky="ew")
        row+=1
        self.tbl_xliff_edit_button=customtkinter.CTkButton(self.button_frame,text=self.get_string('button_tbl_edit'),command=lambda: self.run_script_thread('tbl_xliff_edit_check',extra_args=[]))
        self.tbl_xliff_edit_button.grid(row=row,column=0,columnspan=2,padx=20,pady=(5,5),sticky="ew")
        self.buttons['tbl_xliff_edit']=self.tbl_xliff_edit_button
        row+=1
        self.lang_label=customtkinter.CTkLabel(self.button_frame,text=self.get_string('lang_select_label'),anchor="w")
        self.lang_label.grid(row=row,column=0,padx=(20,5),pady=(15,5),sticky="w")
        self.lang_combo=customtkinter.CTkComboBox(self.button_frame,values=list(self.languages_map.keys()),command=self.change_language)
        self.lang_combo.set(list(self.languages_map.keys())[list(self.languages_map.values()).index(self.current_lang)])
        self.lang_combo.grid(row=row,column=1,padx=(5,20),pady=(15,5),sticky="ew")
        row+=1
        self.terminate_button=customtkinter.CTkButton(self.button_frame,text=self.get_string('terminate_button'),command=self.terminate_process,state="disabled",fg_color="red",hover_color="darkred")
        self.terminate_button.grid(row=row,column=0,columnspan=2,padx=20,pady=(10,10),sticky="ew")
        self.buttons['terminate_button']=self.terminate_button
        row+=1
        self.author_label=customtkinter.CTkLabel(self.button_frame,text="Developer Launcher: Stamir\nРабота основана на форке: nnguyen259/KuroTools",font=customtkinter.CTkFont(size=10),text_color="gray50")
        self.author_label.grid(row=row,column=0,columnspan=2,padx=20,pady=(0,10),sticky="ew")
        row+=1
        self.button_frame.grid_rowconfigure(row,weight=1)
        self.status_label=customtkinter.CTkLabel(self,text=self.get_string('status_idle'),anchor="w")
        self.status_label.grid(row=1,column=0,columnspan=2,padx=20,pady=(0,10),sticky="ew")
        self.process=None
        self.message_queue=queue.Queue()
        self.is_running=False
        self.current_tags=set()
        self.last_dat_input_dir=None
        self.current_process_pid=None
        self.initial_check_done=False
        self._parse_choice=None
        self.update_ui_language()
        self.check_scripts_exist()
        self.after(100,self.process_queue)

    # --- UI Helpers ---
    def _configure_text_tags(self):
        try:
            bfobj=self.output_textbox.cget("font")
            family,size=("Consolas",12) if not isinstance(bfobj,customtkinter.CTkFont) else (bfobj.cget("family"),bfobj.cget("size"))
            bf=(family,int(size),"bold")
            self.output_textbox.tag_config("bold",font=bf)
            self.output_textbox.tag_config("underline",underline=True)
            tc=self.output_textbox.tag_config
            tc("fg_black","black"); tc("fg_red","red"); tc("fg_green","green"); tc("fg_yellow","#B8860B"); tc("fg_blue","blue"); tc("fg_magenta","magenta"); tc("fg_cyan","cyan"); tc("fg_white","white"); tc("fg_bright_black","gray50"); tc("fg_bright_red","#FF5555"); tc("fg_bright_green","#55FF55"); tc("fg_bright_yellow","#FFFF55"); tc("fg_bright_blue","#5555FF"); tc("fg_bright_magenta","#FF55FF"); tc("fg_bright_cyan","#55FFFF"); tc("fg_bright_white","#FFFFFF")
            bc=self.output_textbox.tag_config
            bc("bg_black","black"); bc("bg_red","red"); bc("bg_green","green"); bc("bg_yellow","yellow"); bc("bg_blue","blue"); bc("bg_magenta","magenta"); bc("bg_cyan","cyan"); bc("bg_white","gray90")
            tc("error_log","red"); tc("warning_log","#FFA500"); tc("success_log","green"); tc("info_log","gray50")
        except Exception:
            pass

    def get_string(self, key, default="", **kwargs):
        try:
            tmpl=LANGUAGES[self.current_lang].get(key,default)
            if not tmpl and default=="":
                tmpl=LANGUAGES['en'].get(key,f"<{key}>")
            elif not tmpl and default!="":
                tmpl=default
            elif not tmpl:
                tmpl=f"<{key}>"
            return tmpl.replace("\\n","\n").format(**kwargs)
        except KeyError:
            try:
                tmpl=LANGUAGES['en'].get(key,default)
                tmpl=tmpl if tmpl else f"<Missing Key: {key}>"
                print(f"Warn: Lang '{self.current_lang}' missing, using EN for '{key}'.")
                return tmpl.replace("\\n","\n").format(**kwargs)
            except Exception as e:
                print(f"Err fmt EN fallback '{key}': {e}")
                return f"<Lang Error: {key}>"
        except Exception as e:
            print(f"Err fmt '{key}': {e}")
            return f"<Format Error: {key}>"

    def change_language(self, selected_language_name):
        new_code=self.languages_map.get(selected_language_name)
        if new_code and new_code!=self.current_lang:
            self.current_lang=new_code
            self.update_ui_language()

    def update_ui_language(self):
        self.title(self.get_string('title'))
        cstat=self.status_label.cget("text")
        if self.is_running:
            rname="script"
            status_map={'status_extract_running':'button_2_extract','status_tbl_disassembling':'button_tbl_disassemble','status_tbl_assembling':'button_tbl_assemble','status_tbl_parsing_j2x':'tbl_parse_json_to_xliff','status_tbl_parsing_x2j':'tbl_parse_xliff_to_json'}
            found_status=False
            for skey,bkey in status_map.items():
                s_str=self.get_string(skey)
                if s_str and s_str in cstat:
                    rname=self.get_string(bkey)
                    found_status=True
                    break
            if not found_status:
                for sid,btn in self.buttons.items():
                    if btn.cget("state")=="disabled" and sid not in ['terminate_button','tbl_disassemble','tbl_assemble','tbl_parse_json_xliff','tbl_xliff_edit']:
                        sdef_id='3_edit' if sid=='3_edit' else sid
                        sdef=self.script_definitions.get(sdef_id)
                        if sdef:
                            rname=sdef[0]
                            break
            self.set_status(self.get_string('status_running',script_name=rname))
        elif self.get_string('status_terminated') in cstat:
            self.set_status(self.get_string('status_terminated'))
        elif self.get_string('status_error') in cstat:
            self.set_status(self.get_string('status_error'))
        else:
            self.set_status(self.get_string('status_idle'))
        if hasattr(self,'dat_label'): self.dat_label.configure(text=self.get_string('dat_files_label'))
        if hasattr(self,'tbl_label'): self.tbl_label.configure(text=self.get_string('tbl_files_label'))
        if hasattr(self,'lang_label'): self.lang_label.configure(text=self.get_string('lang_select_label'))
        for sid in self.dat_button_order:
            bkey=f"button_{sid}"
            dtxt=sid.replace("_"," ").title()
            btxt=self.get_string(bkey,default=dtxt)
            if sid in self.buttons:
                self.buttons[sid].configure(text=btxt)
        if hasattr(self,'tbl_disassemble_button'): self.tbl_disassemble_button.configure(text=self.get_string('button_tbl_disassemble'))
        if hasattr(self,'tbl_assemble_button'): self.tbl_assemble_button.configure(text=self.get_string('button_tbl_assemble'))
        if hasattr(self,'tbl_parse_button'): self.tbl_parse_button.configure(text=self.get_string('button_tbl_parse_json_xliff'))
        if hasattr(self,'open_parser_button'): self.open_parser_button.configure(text=self.get_string('button_open_parser'))
        if hasattr(self,'tbl_xliff_edit_button'): self.tbl_xliff_edit_button.configure(text=self.get_string('button_tbl_edit'))
        if hasattr(self,'terminate_button'): self.terminate_button.configure(text=self.get_string('terminate_button'))

    def check_scripts_exist(self):
        all_ok=True
        log=not self.initial_check_done
        if not os.path.isdir(MAIN_PATH):
            self.log_message(self.get_string('error_dir_not_found',path=MAIN_PATH),tags=("error_log",))
            self.disable_all_buttons()
            return False
        flog=[]
        mlog=[]
        checked=set()
        dat_edit_def=self.script_definitions.get('3_edit')
        if dat_edit_def:
            rel,args=dat_edit_def
            abs_p=os.path.join(MAIN_PATH,rel)
            ex=os.path.isfile(abs_p)
            checked.add(rel)
            if not ex:
                if log:
                    mlog.append(self.get_string('error_script_not_found',path=abs_p))
                all_ok=False
                self.buttons.get('3_edit',{}).configure(state="disabled",fg_color="gray")
                self.buttons.get('tbl_xliff_edit',{}).configure(state="disabled",fg_color="gray")
            else:
                if log:
                    flog.append(self.get_string('info_found_script',script_name=rel))
                xliff_p=args[0] if args else None
                dat_arg_ok=(not xliff_p) or os.path.exists(xliff_p)
                if xliff_p and not dat_arg_ok and log:
                    self.log_message(f"WARN: {self.get_string('warning_arg_file_not_found',script=rel,arg_path=xliff_p)}",tags=("warning_log",))
                self.buttons.get('3_edit',{}).configure(state="normal" if dat_arg_ok else "disabled")
                self.buttons.get('tbl_xliff_edit',{}).configure(state="normal")
        for sid,(rel,args) in self.script_definitions.items():
            if rel in checked:
                continue
            abs_p=os.path.join(MAIN_PATH,rel)
            ex=os.path.isfile(abs_p)
            checked.add(rel)
            btn=None
            if sid=='tbl_disassemble_check':
                btn=self.buttons.get('tbl_disassemble')
            elif sid=='tbl_assemble_check':
                btn=self.buttons.get('tbl_assemble')
            elif not sid.startswith('tbl_'):
                btn=self.buttons.get(sid)
            if not ex:
                if log:
                    mlog.append(self.get_string('error_script_not_found',path=abs_p))
                all_ok=False
                if btn:
                    btn.configure(state="disabled",fg_color="gray")
                if sid in ['tbl_disassemble_check','tbl_assemble_check'] and 'tbl_parse_json_xliff' in self.buttons:
                     self.buttons.get('tbl_parse_json_xliff',{}).configure(state="disabled",fg_color="gray")
            else:
                if log:
                    flog.append(self.get_string('info_found_script',script_name=rel))
                if btn:
                    btn.configure(state="normal")
        tbl_d_ok=os.path.isfile(os.path.join(MAIN_PATH,TBL_DISASSEMBLE_SCRIPT))
        tbl_a_ok=os.path.isfile(os.path.join(MAIN_PATH,TBL_ASSEMBLE_SCRIPT))
        self.buttons.get('tbl_parse_json_xliff',{}).configure(state="normal" if tbl_d_ok and tbl_a_ok else "disabled")
        if log:
            for msg in mlog:
                self.log_message(msg,tags=("error_log",))
            if flog:
                self.log_message("\n".join(flog),tags=("success_log",))
            if all_ok and flog:
                self.log_message(self.get_string('info_scripts_found',path=MAIN_PATH))
        self.initial_check_done=True
        if self.is_running:
            self.disable_all_buttons()
        return all_ok

    def log_message(self, raw_message, tags=None):
        try:
            self.output_textbox.configure(state="normal")
            msg=str(raw_message)
            last=0
            ctags_set=set(tags or [])
            ctags_set.update(self.current_tags)
            ctags_tuple=tuple(sorted(list(ctags_set)))
            for m in ANSI_COLOR_REGEX.finditer(msg):
                s,e=m.span()
                if s>last:
                    self.output_textbox.insert("end",msg[last:s],ctags_tuple)
                codes=m.group(1).split(';')
                atags=set(ctags_tuple)
                for c in codes:
                    tag=ANSI_CODE_TO_TAG.get(c)
                    if tag=='reset':
                        atags=set(tags or [])
                        self.current_tags.clear()
                    elif tag:
                        if tag.startswith("fg_"):
                            atags={t for t in atags if not t.startswith("fg_")}
                            self.current_tags={t for t in self.current_tags if not t.startswith("fg_")}
                        if tag.startswith("bg_"):
                            atags={t for t in atags if not t.startswith("bg_")}
                            self.current_tags={t for t in self.current_tags if not t.startswith("bg_")}
                        atags.add(tag)
                        self.current_tags.add(tag)
                ctags_tuple=tuple(sorted(list(atags)))
                last=e
            if last<len(msg):
                self.output_textbox.insert("end",msg[last:],ctags_tuple)
            self.output_textbox.insert("end","\n")
            if ANSI_COLOR_REGEX.search(msg) and msg.rstrip().endswith('\x1B[0m'):
                self.current_tags.clear()
            self.output_textbox.configure(state="disabled")
            self.output_textbox.see("end")
        except Exception as e:
            print(f"Log err: {e}\nMsg: {raw_message}")
            try:
                self.output_textbox.configure(state="normal")
                self.output_textbox.insert("end",str(raw_message)+"\n",("error_log",))
                self.output_textbox.configure(state="disabled")
                self.output_textbox.see("end")
            except Exception:
                pass

    def set_status(self, message):
        self.status_label.configure(text=str(message))

    def disable_all_buttons(self, terminating=False):
        for bid,btn in self.buttons.items():
            state = "disabled"
            if bid == 'terminate_button':
                if self.is_running and self.current_process_pid and not terminating:
                    state = "normal"
                else:
                    state = "disabled"
            btn.configure(state=state)
        if hasattr(self,'open_parser_button'):
            self.open_parser_button.configure(state="normal")

    def enable_all_buttons(self):
        if self.is_running:
            self.disable_all_buttons()
            return
        self.check_scripts_exist()
        if 'terminate_button' in self.buttons:
            self.buttons['terminate_button'].configure(state="disabled")
        if hasattr(self,'open_parser_button'):
            self.open_parser_button.configure(state="normal")

    # --- Button Actions ---
    def prompt_for_dat_path_and_run(self):
        if self.is_running:
            tkinter.messagebox.showwarning(self.get_string('warn_already_running'),self.get_string('warn_already_running_msg'))
            return
        sid='1_disassemble'
        sdef=self.script_definitions.get(sid)
        spath=os.path.join(MAIN_PATH,sdef[0]) if sdef else ''
        if not sdef or not os.path.isfile(spath):
            self.log_message(self.get_string('error_script_not_found_run',path=spath),tags=("error_log",))
            return
        self.log_message(self.get_string('dat_folder_prompt_log'))
        bt=self.get_string(f'button_{sid}',default="Select")
        dt=self.get_string('dat_folder_prompt_title',button_text=bt)
        idir=self.last_dat_input_dir if self.last_dat_input_dir and os.path.isdir(self.last_dat_input_dir) else MAIN_PATH
        fpath=tkinter.filedialog.askdirectory(title=dt,initialdir=idir)
        if fpath:
            self.log_message(self.get_string('dat_folder_selected_log',path=fpath))
            self.last_dat_input_dir=fpath
            self.run_script_thread(sid,extra_args=['-i',fpath])
        else:
            self.log_message(self.get_string('dat_folder_cancel_log'))

    def prompt_compile_mode_and_run(self, script_id):
        if self.is_running:
            tkinter.messagebox.showwarning(self.get_string('warn_already_running'),self.get_string('warn_already_running_msg'))
            return
        sdef=self.script_definitions.get(script_id)
        spath=os.path.join(MAIN_PATH,sdef[0]) if sdef else ''
        if not sdef or not os.path.isfile(spath):
            self.log_message(self.get_string('error_script_not_found_run',path=spath),tags=("error_log",))
            return
        dlg=customtkinter.CTkInputDialog(title=self.get_string('compile_mode_title'),text=f"{self.get_string('compile_mode_prompt')}\n\n{self.get_string('compile_mode_1')}\n{self.get_string('compile_mode_2')}")
        choice=dlg.get_input()
        carg=None
        if choice=="1":
            carg="--only-translated=true"
        elif choice=="2":
            carg="--only-translated=false"
        else:
            if choice is not None and choice.strip()!="":
                tkinter.messagebox.showwarning(self.get_string('compile_mode_title'),self.get_string('compile_mode_invalid'))
            return
        self.run_script_thread(script_id,extra_args=[carg])

    def open_main_path_folder(self):
        fpath=MAIN_PATH
        self.log_message(self.get_string('info_opening_folder',path=fpath))
        try:
            if platform.system()=="Windows":
                os.startfile(os.path.normpath(fpath))
            elif platform.system()=="Darwin":
                subprocess.run(['open',fpath],check=True)
            else:
                subprocess.run(['xdg-open',fpath],check=True)
        except FileNotFoundError:
            emsg=self.get_string('error_open_folder',path=fpath,e="Cmd missing.")
            self.log_message(emsg,tags=("error_log",))
            tkinter.messagebox.showerror(self.get_string('error_unexpected',e=''),emsg)
        except Exception as e:
            emsg=self.get_string('error_open_folder',path=fpath,e=e)
            self.log_message(emsg,tags=("error_log",))
            tkinter.messagebox.showerror(self.get_string('error_unexpected',e=''),emsg)

    def run_script_thread(self, script_id, extra_args=None):
        if self.is_running:
            print(f"Busy, skip '{script_id}'.")
            tkinter.messagebox.showwarning(self.get_string('warn_already_running'),self.get_string('warn_already_running_msg'))
            return
        actual_sid='3_edit' if script_id=='tbl_xliff_edit_check' else script_id
        sdef=self.script_definitions.get(actual_sid)
        if not sdef:
            self.log_message(f"ERR: Script def missing: {actual_sid} (req: {script_id})",tags=("error_log",))
            return
        rel_path,base_args=sdef
        abs_path=os.path.join(MAIN_PATH,rel_path)
        if not os.path.isfile(abs_path):
            self.log_message(self.get_string('error_script_not_found_run',path=abs_path),tags=("error_log",))
            return
        fargs=extra_args if extra_args is not None else base_args
        fargs_str=[str(a) for a in fargs if a is not None]
        cmd=[PYTHON_EXECUTABLE,"-u",abs_path]+fargs_str
        self.is_running=True
        self.process=None
        self.current_process_pid=None
        self.disable_all_buttons()
        self.set_status(self.get_string('status_running',script_name=rel_path))
        log_args=" ".join(f'"{a}"' if " " in a else a for a in fargs_str)
        self.log_message(self.get_string('log_running',script_name=rel_path,args=log_args))
        thread=threading.Thread(target=self.execute_script,args=(cmd,rel_path),daemon=True)
        thread.start()

    # --- Process Execution & Control ---
    def execute_script(self, cmd_list, sname_log):
        pid_end=None
        try:
            penv=os.environ.copy()
            penv["PYTHONIOENCODING"]="utf-8"
            ppath=os.pathsep.join(sys.path+[MAIN_PATH])
            penv["PYTHONPATH"]=ppath
            self.process=subprocess.Popen(cmd_list,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,stdin=subprocess.PIPE,shell=False,cwd=MAIN_PATH,encoding='utf-8',errors='replace',creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform=="win32" else 0,bufsize=1,env=penv)
            self.current_process_pid=self.process.pid
            pid_end=self.current_process_pid
            for line in iter(self.process.stdout.readline,''):
                if not line:
                    break
                self.message_queue.put({"type":"output","data":line.rstrip('\r\n')})
            self.process.stdout.close()
            rcode=self.process.wait()
            if self.current_process_pid==pid_end:
                self.current_process_pid=None
            cstat=self.status_label.cget("text")
            is_term=self.get_string('status_terminated') in cstat
            if is_term:
                self.message_queue.put({"type":"output","data":f"(Proc {pid_end} end: {rcode} post-term)"})
            elif rcode==0:
                self.message_queue.put({"type":"status","data":self.get_string('status_finished',script_name=sname_log)})
            else:
                 twin=(1,-1,0xC000013A,-1073741510,0xFFFFFFFF)
                 tunix=(signal.SIGTERM*-1,signal.SIGINT*-1,130)
                 is_tcode=(sys.platform=="win32" and rcode in twin) or (sys.platform!="win32" and rcode in tunix)
                 if is_tcode:
                     self.message_queue.put({"type":"status","data":self.get_string('status_terminated')})
                     self.message_queue.put({"type":"output","data":f"({sname_log} likely term - Code: {rcode})"})
                 else:
                     self.message_queue.put({"type":"error","data":f"{sname_log} failed (Code: {rcode})"})
        except FileNotFoundError:
            self.message_queue.put({"type":"error","data":f"ERR: File not found. Cmd: {' '.join(cmd_list)}"})
        except Exception as e:
            self.message_queue.put({"type":"error","data":self.get_string('error_unexpected',e=e)})
            import traceback
            traceback.print_exc()
        finally:
            self.message_queue.put({"type":"done"})
            self.process=None
            if self.current_process_pid==pid_end: # Final check
                self.current_process_pid=None

    def _run_command_and_wait(self, cmd_list, step_log):
        proc=None
        try:
            penv=os.environ.copy()
            penv["PYTHONIOENCODING"]="utf-8"
            ppath=os.pathsep.join(sys.path+[MAIN_PATH])
            penv["PYTHONPATH"]=ppath
            largs=" ".join(f'"{a}"' if " " in a else a for a in cmd_list[2:])
            self.message_queue.put({"type":"output","data":f"--- Run step: {step_log} {largs} ---"})
            proc=subprocess.Popen(cmd_list,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,stdin=subprocess.PIPE,shell=False,cwd=MAIN_PATH,encoding='utf-8',errors='replace',creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform=="win32" else 0,bufsize=1,env=penv)
            for line in iter(proc.stdout.readline,''):
                if not line:
                    break
                self.message_queue.put({"type":"output","data":line.rstrip('\r\n')})
            proc.stdout.close()
            rcode=proc.wait()
            self.message_queue.put({"type":"output","data":f"--- Step finish: {step_log} (Code: {rcode}) ---"})
            return rcode
        except FileNotFoundError:
            self.message_queue.put({"type":"error","data":f"ERR: File not found step {step_log}. Cmd: {' '.join(cmd_list)}"})
            return -1
        except Exception as e:
            self.message_queue.put({"type":"error","data":f"Err step {step_log}: {e}"})
            import traceback
            traceback.print_exc()
            return -1
        finally:
             if proc and proc.poll() is None:
                 try:
                     proc.kill()
                 except Exception:
                     pass

    # --- DAT Extraction ---
    def run_extract_strings_sequence(self):
        if self.is_running:
            tkinter.messagebox.showwarning(self.get_string('warn_already_running'),self.get_string('warn_already_running_msg'))
            return
        if not self.last_dat_input_dir or not os.path.isdir(self.last_dat_input_dir):
            self.log_message(self.get_string('extract_prompt_dat_folder_log'),tags=("warning_log",))
            dt=self.get_string('extract_prompt_dat_folder_title')
            fp=tkinter.filedialog.askdirectory(title=dt,initialdir=MAIN_PATH)
            if fp and os.path.isdir(fp):
                self.log_message(self.get_string('dat_folder_selected_log',path=fp))
                self.last_dat_input_dir=fp
            else:
                self.log_message(self.get_string('dat_folder_cancel_log'))
                tkinter.messagebox.showerror(self.get_string('warning_title'),self.get_string('error_no_dat_path'))
                return
        self.is_running=True
        self.process=None
        self.current_process_pid=None
        self.disable_all_buttons()
        self.set_status(self.get_string('status_extract_running'))
        self.log_message(self.get_string('log_extract_start'))
        thread=threading.Thread(target=self._execute_extract_sequence,daemon=True)
        thread.start()

    def _execute_extract_sequence(self):
        succ=True
        err=False
        opath=os.path.join(MAIN_PATH,DATA_TO_PY_FOLDER)
        tpath=os.path.join(MAIN_PATH,DATA_TO_PY_DECOMPILE_TEMP_FOLDER)
        oexists=os.path.isdir(opath)
        if not self.last_dat_input_dir or not os.path.isdir(self.last_dat_input_dir):
            self.message_queue.put({"type":"error","data":"CRIT: DAT input dir missing."})
            self.message_queue.put({"type":"done"})
            return
        try:
            if oexists:
                self.message_queue.put({"type":"output","data":self.get_string('log_rename_orig_to_temp',orig=DATA_TO_PY_FOLDER,temp=DATA_TO_PY_DECOMPILE_TEMP_FOLDER)})
                try:
                    if os.path.exists(tpath):
                        shutil.rmtree(tpath)
                        self.message_queue.put({"type":"output","data":f" (Note: Removed old temp '{DATA_TO_PY_DECOMPILE_TEMP_FOLDER}')","tags":("info_log",)})
                    shutil.move(opath,tpath)
                except Exception as e:
                    self.message_queue.put({"type":"error","data":self.get_string('log_rename_failed',orig=DATA_TO_PY_FOLDER,temp=DATA_TO_PY_DECOMPILE_TEMP_FOLDER,e=e)})
                    err=True
                    succ=False
                    return
            else:
                self.message_queue.put({"type":"output","data":self.get_string('error_orig_folder_missing',path=DATA_TO_PY_FOLDER),"tags":("warning_log",)})
            sdef1=self.script_definitions.get('1_disassemble')
            spath1=os.path.join(MAIN_PATH,sdef1[0])
            cmd1=[PYTHON_EXECUTABLE,"-u",spath1,"-i",self.last_dat_input_dir,"--decompile-mode","false"]
            exit1=self._run_command_and_wait(cmd1,f"{sdef1[0]} (Extract)")
            if exit1!=0:
                self.message_queue.put({"type":"error","data":self.get_string('log_run_disasm_extract_fail')})
                err=True
                succ=False
                return
            if not os.path.isdir(opath):
                if exit1==0:
                     self.message_queue.put({"type":"error","data":f"ERR: '{DATA_TO_PY_FOLDER}' not created."})
                err=True
                succ=False
                return
            sdef2=self.script_definitions.get('2_extract')
            spath2=os.path.join(MAIN_PATH,sdef2[0])
            cmd2=[PYTHON_EXECUTABLE,"-u",spath2]
            exit2=self._run_command_and_wait(cmd2,sdef2[0])
            if exit2!=0:
                self.message_queue.put({"type":"error","data":self.get_string('log_run_pytoxliff_fail')})
                err=True
                succ=False
        except Exception as e:
            self.message_queue.put({"type":"error","data":f"ERR DAT extract: {e}"})
            err=True
            succ=False
            import traceback
            traceback.print_exc()
        finally:
            try:
                if os.path.isdir(opath):
                    self.message_queue.put({"type":"output","data":self.get_string('log_delete_temp_py',path=DATA_TO_PY_FOLDER)})
                    try:
                        shutil.rmtree(opath)
                    except Exception as e:
                        self.message_queue.put({"type":"error","data":self.get_string('log_delete_failed',path=DATA_TO_PY_FOLDER,e=e)})
                        err=True
                if oexists:
                     if os.path.isdir(tpath):
                        self.message_queue.put({"type":"output","data":self.get_string('log_rename_temp_to_orig',temp=DATA_TO_PY_DECOMPILE_TEMP_FOLDER,orig=DATA_TO_PY_FOLDER)})
                        try:
                            if os.path.exists(opath):
                                shutil.rmtree(opath)
                                self.message_queue.put({"type":"output","data":f" (Note: Removed target '{DATA_TO_PY_FOLDER}')","tags":("info_log",)})
                            shutil.move(tpath,opath)
                        except Exception as e:
                            self.message_queue.put({"type":"error","data":self.get_string('error_restore_failed',temp=DATA_TO_PY_DECOMPILE_TEMP_FOLDER,orig=DATA_TO_PY_FOLDER,e=e)})
                            err=True
                     elif succ:
                        self.message_queue.put({"type":"error","data":self.get_string('error_temp_folder_missing_restore',path=DATA_TO_PY_DECOMPILE_TEMP_FOLDER)})
                        err=True
            except Exception as fe:
                self.message_queue.put({"type":"error","data":f"CRIT cleanup err: {fe}"})
                err=True
            flog=self.get_string('log_extract_complete_errors') if err else self.get_string('log_extract_complete')
            fstat=self.get_string('status_error') if err else self.get_string('status_idle')
            self.message_queue.put({"type":"output","data":flog})
            if err:
                self.message_queue.put({"type":"status","data":fstat})
            self.message_queue.put({"type":"done"})

    # --- TBL Batch Processing ---
    def run_batch_tbl_process(self, mode):
        if self.is_running:
            tkinter.messagebox.showwarning(self.get_string('warn_already_running'),self.get_string('warn_already_running_msg'))
            return
        sname=None
        sid_check=None
        skey=None
        lstart_key=None
        lstart_args={}
        src_fpath=None
        if mode=='disassemble':
            sname=TBL_DISASSEMBLE_SCRIPT
            sid_check='tbl_disassemble_check'
            skey='status_tbl_disassembling'
            lstart_key='log_tbl_disassemble_start'
            self.log_message(self.get_string('tbl_folder_prompt_log'))
            dt=self.get_string('tbl_folder_prompt_title_disassemble')
            src_fpath=tkinter.filedialog.askdirectory(title=dt,initialdir=MAIN_PATH)
            if not src_fpath:
                self.log_message(self.get_string('tbl_folder_cancel_log'))
                return
            self.log_message(self.get_string('tbl_folder_selected_log',path=src_fpath))
        elif mode=='assemble':
            sname=TBL_ASSEMBLE_SCRIPT
            sid_check='tbl_assemble_check'
            skey='status_tbl_assembling'
            lstart_key='log_tbl_assemble_start'
            src_fpath=TBL_JSON_FOLDER_PATH
            lstart_args['source_folder']=TBL_TO_JSON_FOLDER
            if not os.path.isdir(src_fpath):
                err=self.get_string('error_source_folder_not_found',path=src_fpath)
                self.log_message(err,tags=("error_log",))
                tkinter.messagebox.showerror(self.get_string('error_unexpected',e=''),err)
                return
        else:
            self.log_message(f"ERR: Invalid TBL batch mode '{mode}'.",tags=("error_log",))
            return
        sdef=self.script_definitions.get(sid_check)
        abs_path=os.path.join(MAIN_PATH,sname)
        if not sdef or not os.path.isfile(abs_path):
            msg=self.get_string('error_script_missing_batch',script_name=sname)
            self.log_message(msg,tags=("error_log",))
            tkinter.messagebox.showerror(self.get_string('warning_title'),msg)
            return
        self.is_running=True
        self.process=None
        self.current_process_pid=None
        self.disable_all_buttons()
        self.set_status(self.get_string(skey))
        self.log_message(self.get_string(lstart_key,**lstart_args))
        thread=threading.Thread(target=self._execute_batch_tbl_process,args=(src_fpath,mode),daemon=True)
        thread.start()

    def _execute_batch_tbl_process(self, input_fpath, mode):
        s_cnt=0
        f_cnt=0
        err=False
        s_name=None
        s_path=None
        i_ext=None
        o_ext=None
        o_sdir=None
        if mode=='disassemble':
            s_name=TBL_DISASSEMBLE_SCRIPT
            i_ext=".tbl"
            o_ext=".json"
            o_sdir=TBL_TO_JSON_FOLDER
        elif mode=='assemble':
            s_name=TBL_ASSEMBLE_SCRIPT
            i_ext=".json"
            o_ext=".tbl"
            o_sdir=JSON_TO_TBL_FOLDER
        else:
            self.message_queue.put({"type":"error","data":f"Internal Err: Invalid mode '{mode}'."})
            self.message_queue.put({"type":"done"})
            return
        s_path=os.path.join(MAIN_PATH,s_name)
        o_sdir_path=os.path.join(MAIN_PATH,o_sdir)
        try:
            try:
                os.makedirs(o_sdir_path,exist_ok=True)
            except OSError as e:
                self.message_queue.put({"type":"error","data":self.get_string('error_create_folder_failed',path=o_sdir_path,e=e)})
                err=True
                self.message_queue.put({"type":"done"})
                return
            ifiles=[]
            try:
                for item in os.listdir(input_fpath):
                    ipath=os.path.join(input_fpath,item)
                    if os.path.isfile(ipath) and item.lower().endswith(i_ext):
                        ifiles.append(ipath)
            except FileNotFoundError:
                emsg=self.get_string('error_source_folder_not_found',path=input_fpath)
                self.message_queue.put({"type":"error","data":emsg})
                err=True
                self.message_queue.put({"type":"done"})
                return
            if not ifiles:
                self.message_queue.put({"type":"output","data":self.get_string('error_no_files_found',extension=i_ext,folder_path=input_fpath),"tags":("warning_log",)})
                self.message_queue.put({"type":"done"})
                return
            for ifile_path in ifiles:
                bname=os.path.basename(ifile_path)
                self.message_queue.put({"type":"output","data":self.get_string('log_processing_file',filename=bname)})
                cmd=[PYTHON_EXECUTABLE,"-u",s_path,ifile_path]
                exit_code=self._run_command_and_wait(cmd,f"{s_name} ({bname})")
                if exit_code==0:
                    exp_out=os.path.splitext(bname)[0]+o_ext
                    src_out=os.path.join(MAIN_PATH,exp_out)
                    tgt_out=os.path.join(o_sdir_path,exp_out)
                    if os.path.exists(src_out):
                        try:
                            if os.path.exists(tgt_out):
                                os.remove(tgt_out)
                            shutil.move(src_out,tgt_out)
                            self.message_queue.put({"type":"output","data":self.get_string('log_move_file_success',target_path=tgt_out),"tags":("info_log",)})
                            s_cnt+=1
                        except Exception as e:
                            self.message_queue.put({"type":"error","data":self.get_string('log_move_file_failed',source=src_out,target=tgt_out,e=e)})
                            f_cnt+=1
                            err=True
                    else:
                        self.message_queue.put({"type":"output","data":self.get_string('log_move_file_source_missing',source=exp_out,search_dir=MAIN_PATH),"tags":("warning_log",)})
                        f_cnt+=1
                        err=True
                else:
                    self.message_queue.put({"type":"output","data":self.get_string('log_skipping_file',filename=bname),"tags":("warning_log",)})
                    f_cnt+=1
                    err=True
        except Exception as e:
            self.message_queue.put({"type":"error","data":f"Unexpected TBL batch error: {e}"})
            err=True
            import traceback
            traceback.print_exc()
        finally:
             lkey='log_batch_complete_errors' if err else 'log_batch_complete'
             skey='status_error' if err else 'status_idle'
             self.message_queue.put({"type":"output","data":self.get_string(lkey,success_count=s_cnt,fail_count=f_cnt)})
             if err:
                 self.message_queue.put({"type":"status","data":self.get_string(skey)})
             self.message_queue.put({"type":"done"})

    # --- TBL JSON <-> XLIFF Parsing ---
    def _show_parse_choice_dialog(self):
        dialog=customtkinter.CTkToplevel(self)
        dialog.geometry("400x150")
        dialog.title(self.get_string('tbl_parse_dialog_title'))
        dialog.transient(self)
        dialog.grab_set()
        self._parse_choice=None
        def set_choice(mode):
            self._parse_choice=mode
            dialog.destroy()
        customtkinter.CTkLabel(dialog,text=self.get_string('tbl_parse_prompt_text')).pack(pady=10)
        customtkinter.CTkButton(dialog,text=self.get_string('tbl_parse_json_to_xliff'),command=lambda: set_choice('json_to_xliff')).pack(pady=5,padx=20,fill='x')
        customtkinter.CTkButton(dialog,text=self.get_string('tbl_parse_xliff_to_json'),command=lambda: set_choice('xliff_to_json')).pack(pady=5,padx=20,fill='x')
        dialog.wait_window()
        return self._parse_choice

    def prompt_tbl_parse_mode(self):
        if self.is_running:
            tkinter.messagebox.showwarning(self.get_string('warn_already_running'),self.get_string('warn_already_running_msg'))
            return
        choice = self._show_parse_choice_dialog()
        if choice in ['json_to_xliff', 'xliff_to_json']:
            self.run_tbl_parse_process(choice)

    def run_tbl_parse_process(self, mode):
        if self.is_running:
            tkinter.messagebox.showwarning(self.get_string('warn_already_running'),self.get_string('warn_already_running_msg'))
            return
        if mode=='json_to_xliff' and not os.path.isdir(TBL_JSON_FOLDER_PATH):
            err=self.get_string('error_source_folder_not_found',path=TBL_JSON_FOLDER_PATH)
            self.log_message(err,tags=("error_log",))
            tkinter.messagebox.showerror(self.get_string('warning_title'),err)
            return
        if mode=='xliff_to_json':
            if not os.path.isdir(TBL_JSON_FOLDER_PATH):
                err=self.get_string('error_source_folder_not_found',path=TBL_JSON_FOLDER_PATH)
                self.log_message(err,tags=("error_log",))
                tkinter.messagebox.showerror(self.get_string('warning_title'),err)
                return
            if not os.path.isfile(TBL_XLIFF_FILE_PATH):
                err=self.get_string('error_tbl_parse_no_xliff',filename=TBL_XLIFF_FILE_PATH)
                self.log_message(err,tags=("error_log",))
                tkinter.messagebox.showerror(self.get_string('warning_title'),err)
                return
        self.is_running=True
        self.process=None
        self.current_process_pid=None
        self.disable_all_buttons()
        skey = 'status_tbl_parsing_j2x' if mode=='json_to_xliff' else 'status_tbl_parsing_x2j'
        lkey = 'log_tbl_parse_j2x_start' if mode=='json_to_xliff' else 'log_tbl_parse_x2j_start'
        self.set_status(self.get_string(skey))
        self.log_message(self.get_string(lkey))
        thread=threading.Thread(target=self._execute_tbl_parse_process,args=(mode,),daemon=True)
        thread.start()

    def _execute_tbl_parse_process(self, mode):
        err=False
        try:
            if mode=='json_to_xliff':
                err=not self._execute_json_to_xliff()
            elif mode=='xliff_to_json':
                err=not self._execute_xliff_to_json()
        except Exception as e:
            self.message_queue.put({"type":"error","data":f"ERR TBL Parse: {e}"})
            err=True
            import traceback
            traceback.print_exc()
        finally:
             lkey='log_tbl_parse_complete_errors' if err else 'log_tbl_parse_complete'
             skey='status_error' if err else 'status_idle'
             self.message_queue.put({"type":"output","data":self.get_string(lkey)})
             if err:
                 self.message_queue.put({"type":"status","data":self.get_string(skey)})
             self.message_queue.put({"type":"done"})

    def _is_tbl_translatable_string(self, s):
        if not isinstance(s, str) or not s:
            return False
        if len(s) < TBL_MIN_STRING_LENGTH:
            return False
        if TBL_IGNORE_TBL_IDS and s.startswith("tbl_") and all(c.isalnum() or c=='_' for c in s):
            return False
        if TBL_REQUIRE_SPACE and ' ' not in s and '\n' not in s and all(ord(c)<128 for c in s):
            return False
        if TBL_IGNORE_UNDERSCORE_ONLY and '_' in s and ' ' not in s and '\n' not in s and all(c.isalnum() or c=='_' for c in s) and s[0].isalpha():
             return False
        if TBL_IGNORE_NUMERIC_PUNCT and all(c in (string_module.digits + string_module.punctuation + string_module.whitespace) for c in s):
            return False
        return True

    def _execute_json_to_xliff(self):
        xliff_data={}
        id_map={}
        total_strings=0
        files_processed=0
        json_files=[]
        if not os.path.isdir(TBL_JSON_FOLDER_PATH):
            self.message_queue.put({"type":"error","data":self.get_string('error_source_folder_not_found',path=TBL_JSON_FOLDER_PATH)})
            return False
        for fname in os.listdir(TBL_JSON_FOLDER_PATH):
            if fname.lower().endswith(".json"):
                json_files.append(fname)
        if not json_files:
            self.message_queue.put({"type":"output","data":self.get_string('error_no_files_found',extension='.json',folder_path=TBL_JSON_FOLDER_PATH),"tags":("warning_log",)})
            return True
        for fname in sorted(json_files):
            fpath=os.path.join(TBL_JSON_FOLDER_PATH,fname)
            self.message_queue.put({"type":"output","data":self.get_string('log_tbl_parse_reading_json',filename=fname)})
            try:
                with open(fpath,'r',encoding='utf-8') as f:
                    json_data=json.load(f)
            except Exception as e:
                self.message_queue.put({"type":"error","data":self.get_string('error_tbl_parse_read_json',filename=fname,e=e)})
                continue
            strings_in_file=self._recursive_find_and_replace(json_data,id_map,xliff_data,fname) # Pass maps and filename
            total_strings+=strings_in_file
            if strings_in_file>0:
                self.message_queue.put({"type":"output","data":self.get_string('log_tbl_parse_found_strings',count=strings_in_file,filename=fname),"tags":("info_log",)})
            self.message_queue.put({"type":"output","data":self.get_string('log_tbl_parse_writing_json',filename=fname)})
            try:
                 with open(fpath,'w',encoding='utf-8') as f:
                     json.dump(json_data,f,indent="\t",ensure_ascii=False)
                 files_processed+=1
            except IOError as e:
                 self.message_queue.put({"type":"error","data":self.get_string('error_tbl_parse_write_json',filename=fname,e=e)})
        if xliff_data:
            self.message_queue.put({"type":"output","data":self.get_string('log_tbl_parse_total_strings',count=len(xliff_data))})
            self.message_queue.put({"type":"output","data":self.get_string('log_tbl_parse_creating_xliff',filename=TBL_XLIFF_FILE_PATH)})
            if not self._create_combined_xliff(xliff_data,TBL_XLIFF_FILE_PATH):
                return False
        else:
             self.message_queue.put({"type":"output","data":self.get_string('log_tbl_parse_no_strings'),"tags":("warning_log",)})
        return True

    def _recursive_find_and_replace(self, obj, id_map, xliff_data, filename): # No 'keys' needed
        count = 0
        if isinstance(obj, dict):
            for key, value in list(obj.items()):
                if isinstance(value, str):
                    if self._is_tbl_translatable_string(value):
                        if value in id_map:
                            obj[key] = id_map[value]
                        else:
                            tid = f"tbl_{uuid.uuid4().hex[:10]}"
                            id_map[value] = tid
                            xliff_data[tid] = {"source": value, "file": filename}
                            obj[key] = tid
                            count += 1
                elif isinstance(value, (dict, list)):
                    count += self._recursive_find_and_replace(value, id_map, xliff_data, filename)
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                if isinstance(item, str):
                   if self._is_tbl_translatable_string(item):
                        if item in id_map:
                            obj[i] = id_map[item]
                        else:
                            tid = f"tbl_{uuid.uuid4().hex[:10]}"
                            id_map[item] = tid
                            xliff_data[tid] = {"source": item, "file": filename}
                            obj[i] = tid
                            count += 1
                elif isinstance(item, (dict, list)):
                    count += self._recursive_find_and_replace(item, id_map, xliff_data, filename)
        return count

    def _create_combined_xliff(self, xliff_data, xliff_filepath):
        try:
            root=ET.Element("xliff",version="1.2",xmlns="urn:oasis:names:tc:xliff:document:1.2")
            fe=ET.SubElement(root,"file",original="combined_tbl_json",datatype="plaintext",source_language="en",target_language="ru")
            body=ET.SubElement(fe,"body")
            for tid in sorted(xliff_data.keys()):
                data=xliff_data[tid]
                tu=ET.SubElement(body,"trans-unit",id=tid)
                ET.SubElement(tu,"note").text=f"File: {data['file']}"
                src=ET.SubElement(tu,"source")
                src.text=data["source"].replace("\n","\\n")
                tgt=ET.SubElement(tu,"target")
            xml_str=ET.tostring(root,encoding='utf-8')
            dom=xml.dom.minidom.parseString(xml_str)
            pretty_xml=dom.toprettyxml(indent="  ",encoding='utf-8')
            with open(xliff_filepath,"wb") as f:
                f.write(pretty_xml) # Corrected: Added closing parenthesis
            return True
        except Exception as e:
            self.message_queue.put({"type":"error","data":self.get_string('error_tbl_parse_write_xliff',filename=xliff_filepath,e=e)})
            return False

    def _execute_xliff_to_json(self):
        if not os.path.isfile(TBL_XLIFF_FILE_PATH):
            self.message_queue.put({"type":"error","data":self.get_string('error_tbl_parse_no_xliff',filename=TBL_XLIFF_FILE_PATH)})
            return False
        if not os.path.isdir(TBL_JSON_FOLDER_PATH):
            self.message_queue.put({"type":"error","data":self.get_string('error_source_folder_not_found',path=TBL_JSON_FOLDER_PATH)})
            return False
        self.message_queue.put({"type":"output","data":self.get_string('log_tbl_parse_reading_xliff',filename=TBL_XLIFF_FILE_PATH)})
        trans_map=self._load_xliff_translations(TBL_XLIFF_FILE_PATH)
        if not trans_map:
            self.message_queue.put({"type":"error","data":self.get_string('error_tbl_parse_no_map',filename=TBL_XLIFF_FILE_PATH)})
            return False
        self.message_queue.put({"type":"output","data":self.get_string('log_tbl_parse_map_loaded',count=len(trans_map)),"tags":("info_log",)})
        json_files=[]
        for fname in os.listdir(TBL_JSON_FOLDER_PATH):
            if fname.lower().endswith(".json"):
                json_files.append(fname)
        if not json_files:
            self.message_queue.put({"type":"output","data":self.get_string('error_no_files_found',extension='.json',folder_path=TBL_JSON_FOLDER_PATH),"tags":("warning_log",)})
            return True
        for fname in sorted(json_files):
            fpath=os.path.join(TBL_JSON_FOLDER_PATH,fname)
            self.message_queue.put({"type":"output","data":self.get_string('log_tbl_parse_replacing_ids',filename=fname)})
            try:
                with open(fpath,'r',encoding='utf-8') as f:
                    json_data=json.load(f)
            except Exception as e:
                self.message_queue.put({"type":"error","data":self.get_string('error_tbl_parse_read_json',filename=fname,e=e)})
                continue
            self._recursive_replace_ids(json_data,trans_map)
            try:
                 with open(fpath,'w',encoding='utf-8') as f:
                     json.dump(json_data,f,indent="\t",ensure_ascii=False)
            except IOError as e:
                 self.message_queue.put({"type":"error","data":self.get_string('error_tbl_parse_write_json',filename=fname,e=e)})
        return True

    def _load_xliff_translations(self, xliff_filepath):
        translations={}
        try:
            tree=ET.parse(xliff_filepath)
            root=tree.getroot()
            ns={'xliff':'urn:oasis:names:tc:xliff:document:1.2'}
            for tu in root.findall(".//xliff:trans-unit",ns):
                uid=tu.get('id')
                if not uid:
                    continue
                tgt=tu.find("xliff:target",ns)
                src=tu.find("xliff:source",ns)
                txt=None
                if tgt is not None and tgt.text:
                    txt=tgt.text
                elif src is not None and src.text: # Fallback
                    txt=src.text
                if txt is not None:
                    translations[uid]=txt.replace("\\n","\n")
            return translations
        except Exception as e:
            self.message_queue.put({"type":"error","data":self.get_string('error_tbl_parse_read_xliff',filename=xliff_filepath,e=e)})
            return None

    def _recursive_replace_ids(self, obj, translation_map):
        if isinstance(obj,dict):
            for key,value in obj.items():
                if isinstance(value,str) and value in translation_map:
                    obj[key]=translation_map[value]
                elif isinstance(value,(dict,list)):
                    self._recursive_replace_ids(value,translation_map)
        elif isinstance(obj,list):
            for i,item in enumerate(obj):
                 if isinstance(item,str) and item in translation_map:
                     obj[i]=translation_map[item]
                 elif isinstance(item,(dict,list)):
                     self._recursive_replace_ids(item,translation_map)

    # --- Other Helpers & Main Loop ---
    def process_queue(self):
        try:
            while True: # Process all available messages
                msg = self.message_queue.get_nowait()
                mtype = msg.get("type")
                mdata = msg.get("data")
                mtags = msg.get("tags")

                if mtype == "output":
                    self.log_message(mdata, tags=mtags)
                elif mtype == "status":
                    self.set_status(mdata)
                    # Log significant status changes using language strings
                    status_keys = ['status_finished', 'status_terminated', 'status_error']
                    # Construct the search string format for status_finished (handles cases with or without script name)
                    finished_fmt_base = self.get_string('status_finished', script_name='X') # Use placeholder
                    finished_start = finished_fmt_base.split('X')[0].strip()

                    # Check if the message indicates a significant status change
                    is_significant = False
                    if self.get_string('status_terminated') in mdata: is_significant = True
                    elif self.get_string('status_error') in mdata: is_significant = True
                    elif finished_start and finished_start in mdata: is_significant = True # Check beginning part

                    if is_significant:
                        self.log_message(f"--- {mdata} ---", tags=mtags)

                elif mtype == "error":
                    self.set_status(self.get_string('status_error'))
                    self.log_message(self.get_string('log_error', error_message=mdata), tags=("error_log",))
                elif mtype == "done":
                    was_running = self.is_running
                    self.is_running = False
                    self.process = None # Clear process handle
                    # Don't clear PID here necessarily, execute_script handles its own PID clearing
                    cstat = self.status_label.cget("text")
                    # Only set to Idle if it wasn't an error or termination
                    if was_running and not any(self.get_string(k) in cstat for k in ['status_terminated', 'status_error'] if self.get_string(k)):
                         self.set_status(self.get_string('status_idle'))
                    self.enable_all_buttons() # Re-enable buttons after task completion

        except queue.Empty:
            pass # No messages left
        except Exception as e:
             print(f"Queue Error: {e}")
             self.log_message(f"Queue Error: {e}",tags=("error_log",))
             if self.is_running: # Try to recover UI state
                 self.is_running=False
                 self.enable_all_buttons()
                 self.set_status(self.get_string('status_error')+" (Queue Err)")
        finally:
            # Schedule next check
            self.after(100,self.process_queue)

    def terminate_process(self):
        pid=self.current_process_pid
        if self.is_running and pid:
            self.log_message(self.get_string('log_terminate_attempt')+f" (PID: {pid})")
            self.set_status(self.get_string('status_terminated'))
            self.disable_all_buttons(terminating=True)
            ok=False
            try:
                if sys.platform=="win32":
                    res=subprocess.run(['taskkill','/F','/T','/PID',str(pid)],capture_output=True,text=True,check=False,creationflags=subprocess.CREATE_NO_WINDOW)
                    ok=(res.returncode==0 or res.returncode==128)
                    if not ok:
                         self.log_message(f"Taskkill failed (Code: {res.returncode}): {res.stderr.strip()}", tags=("warning_log",))
                else:
                    try:
                        pgid=os.getpgid(pid)
                        os.killpg(pgid,signal.SIGTERM)
                        ok=True
                    except (ProcessLookupError,AttributeError):
                         try:
                             os.kill(pid,signal.SIGTERM)
                             ok=True
                         except ProcessLookupError:
                             ok=True # Already gone
                         except Exception as ek:
                             self.log_message(f"Fallback kill fail: {ek}",tags=("error_log",))
            except Exception as e:
                self.log_message(self.get_string('log_terminate_error',e=e),tags=("error_log",))
            # Update state AFTER attempting termination
            self.is_running=False
            self.process=None
            # Don't clear PID here, let execute_script handle it when the process actually exits or errors
            self.set_status(self.get_string('status_terminated'))
            # Rely on the 'done' message from the thread queue to re-enable buttons
        elif self.is_running: # Terminate during batch/parse (no PID)
             self.log_message("Terminate req during batch/parse. Signaling done.",tags=("warning_log",))
             self.is_running=False
             self.process=None
             self.set_status(self.get_string('status_terminated'))
             self.disable_all_buttons(terminating=True) # Keep disabled until 'done' received
        else: # Not running
             self.log_message("No running process.",tags=("info_log",))
             if not self.is_running: # Ensure UI state is correct
                 self.enable_all_buttons()

    def on_closing(self):
        if self.is_running:
            msg=self.get_string('confirm_exit_msg')
            if not self.current_process_pid:
                msg+="\n\n(Batch/Parse may not stop immediately.)"
            if tkinter.messagebox.askyesno(self.get_string('confirm_exit_title'),msg):
                if self.current_process_pid:
                    self.terminate_process()
                else: # Batch/Parse running
                     self.log_message("--- Exit during batch/parse ---",tags=("warning_log",))
                     self.is_running=False # Allow closing
                     self.set_status(self.get_string('status_terminated'))
                     self.disable_all_buttons(terminating=True)
                self.after(500,self.destroy) # Give a moment
            else:
                return # User cancelled exit
        else:
            self.destroy() # Exit immediately

# --- Main Execution ---
if __name__=="__main__":
    lang="ru"
    errors=[]
    if not PYTHON_EXECUTABLE or not os.path.isfile(PYTHON_EXECUTABLE):
        errors.append(LANGUAGES[lang].get('startup_error_python_not_found','Py err').format(path=PYTHON_EXECUTABLE))
    if not os.path.isdir(MAIN_PATH) or not os.path.isdir(START_DIR):
        errors.append(LANGUAGES[lang].get('startup_error_main_path_not_found',"Path err").format(main_path=MAIN_PATH,start_path=START_DIR))
    if errors:
        title=LANGUAGES[lang].get('startup_error_title','Startup Error')
        msg="\n\n".join(errors)
        tr=tkinter.Tk()
        tr.withdraw()
        tkinter.messagebox.showerror(title,msg)
        tr.destroy()
        sys.exit(1)
    app=App()
    app.protocol("WM_DELETE_WINDOW",app.on_closing)
    app.mainloop()
# --- END OF FILE launcher.py ---