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
import shutil # <<< ADDED for folder operations

# --- Configuration ---
customtkinter.set_appearance_mode("System")
customtkinter.set_default_color_theme("blue")

script_dir = os.path.dirname(os.path.abspath(__file__))
# --- Path Detection Logic ---
# (Keep existing logic)
if os.path.basename(script_dir).lower() == "start":
     MAIN_PATH = os.path.dirname(script_dir)
     START_DIR = script_dir
elif os.path.isdir(os.path.join(script_dir, "Start")):
     MAIN_PATH = script_dir
     START_DIR = os.path.join(script_dir, "Start")
else:
     MAIN_PATH = script_dir
     START_DIR = os.path.join(MAIN_PATH, "Start")
     # Use print here as logging might not be ready
     print(f"Warning: Could not find 'Start' directory conventionally. Assuming MAIN_PATH='{MAIN_PATH}' and START_DIR='{START_DIR}'")

# --- Constants ---
PARSER_FOLDER_NAME = "Parser"
PARSER_FOLDER_PATH = os.path.join(MAIN_PATH, PARSER_FOLDER_NAME)
# --- ADDED Constants for folder names ---
DATA_TO_PY_FOLDER = "data_to_py"
DATA_TO_PY_DECOMPILE_TEMP_FOLDER = "data_to_py_DECOMPILE"
# --- END ADDED Constants ---

# --- Python Executable ---
PYTHON_EXECUTABLE = sys.executable

# --- Encoding ---
CONSOLE_ENCODING = 'utf-8'

# --- Language Strings ---
LANGUAGES = {
    'en': {
        # ... (all EN strings including added ones) ...
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
        'tbl_files_label': "Work with TBL files",
        'button_open_parser': "Open Parsing Folder",
        'button_tbl_edit': "Launch XLIFF Editor",
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
        'error_no_dat_path': "ERROR: Cannot extract strings. Please run Step 1 (Disassemble DAT) first or select the DAT folder now.", # Modified message
        'error_orig_folder_missing': "Warning: Original folder '{path}' not found. Skipping initial rename.",
        'error_temp_folder_missing_del': "Warning: Temporary folder '{path}' not found for deletion.",
        'error_temp_folder_missing_restore': "ERROR: Cannot restore original folder. Temporary backup '{path}' not found.",
        'error_restore_failed': "CRITICAL ERROR: Failed to restore original folder '{orig}' from '{temp}': {e}. Manual restoration might be needed.",
        'extract_prompt_dat_folder_title': "Extract Strings - Select DAT Folder", # New string
        'extract_prompt_dat_folder_log': "DAT folder path not set. Prompting user...", # New string
    },
    'ru': {
        # ... (all RU strings including added ones) ...
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
        'tbl_files_label': "Работа с TBL файлами",
        'button_open_parser': "Открыть папку парсинга",
        'button_tbl_edit': "Запустить XLIFF редактор",
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
        'error_no_dat_path': "ОШИБКА: Невозможно извлечь строки. Сначала выполните Шаг 1 (Дизассемблировать DAT) или выберите папку DAT сейчас.", # Modified message
        'error_orig_folder_missing': "Предупреждение: Исходная папка '{path}' не найдена. Пропуск начального переименования.",
        'error_temp_folder_missing_del': "Предупреждение: Временная папка '{path}' не найдена для удаления.",
        'error_temp_folder_missing_restore': "ОШИБКА: Невозможно восстановить исходную папку. Временная копия '{path}' не найдена.",
        'error_restore_failed': "КРИТИЧЕСКАЯ ОШИБКА: Не удалось восстановить исходную папку '{orig}' из '{temp}': {e}. Может потребоваться ручное восстановление.",
        'extract_prompt_dat_folder_title': "Извлечь строки - Выберите папку DAT", # New string
        'extract_prompt_dat_folder_log': "Путь к папке DAT не задан. Запрос у пользователя...", # New string
    }
}

# --- ANSI Color Parsing ---
ANSI_ESCAPE_REGEX = re.compile(r'\x1B\[[0-?]*[ -/]*[@-~]')
ANSI_COLOR_REGEX = re.compile(r'\x1B\[(\d+(?:;\d+)*)m')
ANSI_CODE_TO_TAG = {
    '0': 'reset', '1': 'bold', '4': 'underline',
    '30': 'fg_black', '31': 'fg_red', '32': 'fg_green', '33': 'fg_yellow', '34': 'fg_blue', '35': 'fg_magenta', '36': 'fg_cyan', '37': 'fg_white',
    '90': 'fg_bright_black', '91': 'fg_bright_red', '92': 'fg_bright_green', '93': 'fg_bright_yellow', '94': 'fg_bright_blue', '95': 'fg_bright_magenta', '96': 'fg_bright_cyan', '97': 'fg_bright_white',
    '40': 'bg_black', '41': 'bg_red', '42': 'bg_green', '43': 'bg_yellow', '44': 'bg_blue', '45': 'bg_magenta', '46': 'bg_cyan', '47': 'bg_white',
    '100': 'bg_bright_black', '101': 'bg_bright_red', '102': 'bg_bright_green', '103': 'bg_bright_yellow', '104': 'bg_bright_blue', '105': 'bg_bright_magenta', '106': 'bg_bright_cyan', '107': 'bg_bright_white',
}

class App(customtkinter.CTk):
    def __init__(self):
        super().__init__()

        # --- Language & Path Setup ---
        self.current_lang = "ru"
        self.languages_map = {"Русский": "ru", "English": "en"}
        if not os.path.isdir(MAIN_PATH) or not os.path.isdir(START_DIR):
             title = LANGUAGES[self.current_lang].get('startup_error_title', "Startup Error")
             msg = LANGUAGES[self.current_lang].get('startup_error_main_path_not_found', "Main project directory ({main_path}) or Start directory ({start_path}) not found.").format(main_path=MAIN_PATH, start_path=START_DIR)
             tkinter.messagebox.showerror(title, msg)
             sys.exit(1)

        # --- Define Script Commands ---
        xliff_file_path = os.path.join(MAIN_PATH, "data_game_strings.xliff")
        self.script_definitions = {
            # DAT scripts
            '1_disassemble': ("dat2py_batch.py", []), # Base args are empty, path added dynamically
            '2_extract': ("py_to_xliff.py", []),   # This ID is now mainly a trigger for the sequence
            '3_edit': ("xliff_editor_gui.py", [xliff_file_path]),
            '4_create_map': ("inject_translations.py", []),
            '5_compile': ("py2dat_batch.py", []), # Base args empty, mode added dynamically
            # The TBL editor button will reuse '3_edit' definition but override args
        }
        self.dat_button_order = ['1_disassemble', '2_extract', '3_edit', '4_create_map', '5_compile']

        # --- Window Setup ---
        self.title(self.get_string('title'))
        self.geometry(f"{1100}x650")
        self.grid_columnconfigure(0, weight=3)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=0)

        # --- Output Textbox (with bold font) ---
        default_font_obj = customtkinter.CTkFont()
        bold_font = customtkinter.CTkFont(
            family=default_font_obj.cget("family"),
            size=default_font_obj.cget("size"),
            weight="bold"
        )
        self.output_textbox = customtkinter.CTkTextbox(
            self,
            width=700,
            corner_radius=5,
            font=bold_font
        )
        self.output_textbox.grid(row=0, column=0, padx=(20, 10), pady=(20, 20), sticky="nsew")
        self.output_textbox.configure(state="disabled", wrap="word")
        self._configure_text_tags() # Configure tags AFTER textbox creation

        # --- Button Frame ---
        self.button_frame = customtkinter.CTkFrame(self, width=250, corner_radius=5)
        self.button_frame.grid(row=0, column=1, padx=(10, 20), pady=(20, 20), sticky="nsew")
        num_dat_buttons = len(self.dat_button_order)
        current_row = 0

        # --- DAT Section ---
        self.dat_label = customtkinter.CTkLabel(
            self.button_frame,
            text=self.get_string('dat_files_label'),
            font=customtkinter.CTkFont(weight="bold")
        )
        self.dat_label.grid(row=current_row, column=0, columnspan=2, padx=20, pady=(10, 10), sticky="ew")
        current_row += 1

        self.buttons = {} # Holds all script-running buttons
        for i, script_id in enumerate(self.dat_button_order):
            button_key = f"button_{script_id}"
            button_text = self.get_string(button_key, default=script_id.replace("_"," ").title())
            button = customtkinter.CTkButton(
                self.button_frame,
                text=button_text
            )
            button.grid(row=current_row + i, column=0, columnspan=2, padx=20, pady=(5, 5), sticky="ew")
            # --- MODIFIED: Assign command based on script_id ---
            if script_id == '1_disassemble':
                button.configure(command=self.prompt_for_dat_path_and_run)
            elif script_id == '2_extract':
                button.configure(command=self.run_extract_strings_sequence) # <<< Use new sequence function
            elif script_id == '5_compile':
                button.configure(command=lambda sid=script_id: self.prompt_compile_mode_and_run(sid))
            else: # Covers 3_edit, 4_create_map
                button.configure(command=lambda sid=script_id: self.run_script_thread(sid))
            # --- END MODIFICATION ---
            self.buttons[script_id] = button
        current_row += num_dat_buttons

        # --- TBL Section ---
        self.tbl_label = customtkinter.CTkLabel(
            self.button_frame,
            text=self.get_string('tbl_files_label'),
            font=customtkinter.CTkFont(weight="bold")
        )
        self.tbl_label.grid(row=current_row, column=0, columnspan=2, padx=20, pady=(15, 10), sticky="ew")
        current_row += 1

        self.open_parser_button = customtkinter.CTkButton(
            self.button_frame,
            text=self.get_string('button_open_parser'),
            command=self.open_parser_folder
        )
        self.open_parser_button.grid(row=current_row, column=0, columnspan=2, padx=20, pady=(5, 5), sticky="ew")
        current_row += 1

        self.tbl_xliff_edit_button = customtkinter.CTkButton(
            self.button_frame,
            text=self.get_string('button_tbl_edit'),
            # Use '3_edit' script def, but pass empty args override
            command=lambda: self.run_script_thread('3_edit', extra_args=[])
        )
        self.tbl_xliff_edit_button.grid(row=current_row, column=0, columnspan=2, padx=20, pady=(5, 5), sticky="ew")
        self.buttons['tbl_xliff_edit'] = self.tbl_xliff_edit_button # Track for enable/disable
        current_row += 1

        # --- Language Selector ---
        self.lang_label = customtkinter.CTkLabel(self.button_frame, text=self.get_string('lang_select_label'), anchor="w")
        self.lang_label.grid(row=current_row, column=0, padx=(20, 5), pady=(15, 5), sticky="w")
        self.lang_combo = customtkinter.CTkComboBox(
            self.button_frame,
            values=list(self.languages_map.keys()),
            command=self.change_language
        )
        self.lang_combo.set(list(self.languages_map.keys())[list(self.languages_map.values()).index(self.current_lang)])
        self.lang_combo.grid(row=current_row, column=1, padx=(5, 20), pady=(15, 5), sticky="ew")
        current_row += 1

        # --- Terminate Button ---
        self.terminate_button = customtkinter.CTkButton(
            self.button_frame, text=self.get_string('terminate_button'),
            command=self.terminate_process, state="disabled",
            fg_color="red", hover_color="darkred"
        )
        self.terminate_button.grid(row=current_row, column=0, columnspan=2, padx=20, pady=(10, 10), sticky="ew")
        current_row += 1

        # --- XLIFF Editor Note ---
        self.xliff_note_label = customtkinter.CTkLabel(
            self.button_frame,
            text=self.get_string('xliff_editor_note'),
            font=customtkinter.CTkFont(size=10),
            text_color="gray50"
        )
        self.xliff_note_label.grid(row=current_row, column=0, columnspan=2, padx=20, pady=(0, 10), sticky="ew")
        current_row += 1

        # --- Author Note ---
        self.author_label = customtkinter.CTkLabel(
            self.button_frame,
            text="Developer Launcher: Stamir\nРабота основана на форке: nnguyen259/KuroTools",
            font=customtkinter.CTkFont(size=10),
            text_color="gray50"
        )
        self.author_label.grid(row=current_row, column=0, columnspan=2, padx=20, pady=(0, 10), sticky="ew")
        current_row += 1

        # --- Spacer Row ---
        self.button_frame.grid_rowconfigure(current_row, weight=1)

        # --- Status Label ---
        self.status_label = customtkinter.CTkLabel(self, text=self.get_string('status_idle'), anchor="w")
        self.status_label.grid(row=1, column=0, columnspan=2, padx=20, pady=(0, 10), sticky="ew")

        # --- Threading & State ---
        self.process = None
        self.message_queue = queue.Queue()
        self.is_running = False
        self.current_tags = set()
        self.last_dat_input_dir = None # <<< Stores path from Step 1 (or Step 2 prompt)
        self.current_process_pid = None # Store PID for termination
        self.initial_check_done = False # <<< ADDED: Flag for initial script check logging

        # --- Init ---
        self.update_ui_language()
        self.check_scripts_exist() # Initial check
        self.after(100, self.process_queue)

    # --- _configure_text_tags --- (MODIFIED: Suppress errors)
    def _configure_text_tags(self):
        """Defines Tkinter tags for ANSI colors."""
        try:
            base_font_obj = self.output_textbox.cget("font")
            if isinstance(base_font_obj, customtkinter.CTkFont):
                family = base_font_obj.cget("family")
                size = base_font_obj.cget("size")
                bold_font_tuple = (family, int(size), "bold")
            else: # Fallback
                family = "Consolas"
                size = 12
                bold_font_tuple = (family, int(size), "bold")
                # print("Warning: Could not get CTkFont object, using default font for tags.") # Suppressed

            self.output_textbox.tag_config("bold", font=bold_font_tuple)
            self.output_textbox.tag_config("underline", underline=True)

            # Colors (same as before)
            self.output_textbox.tag_config("fg_black", foreground="black")
            self.output_textbox.tag_config("fg_red", foreground="red")
            self.output_textbox.tag_config("fg_green", foreground="green")
            self.output_textbox.tag_config("fg_yellow", foreground="#B8860B") # Dark Yellow
            self.output_textbox.tag_config("fg_blue", foreground="blue")
            self.output_textbox.tag_config("fg_magenta", foreground="magenta")
            self.output_textbox.tag_config("fg_cyan", foreground="cyan")
            self.output_textbox.tag_config("fg_white", foreground="white") # Use theme bg?
            self.output_textbox.tag_config("fg_bright_black", foreground="gray50")
            self.output_textbox.tag_config("fg_bright_red", foreground="#FF5555")
            self.output_textbox.tag_config("fg_bright_green", foreground="#55FF55")
            self.output_textbox.tag_config("fg_bright_yellow", foreground="#FFFF55")
            self.output_textbox.tag_config("fg_bright_blue", foreground="#5555FF")
            self.output_textbox.tag_config("fg_bright_magenta", foreground="#FF55FF")
            self.output_textbox.tag_config("fg_bright_cyan", foreground="#55FFFF")
            self.output_textbox.tag_config("fg_bright_white", foreground="#FFFFFF") # Use theme bg?

            self.output_textbox.tag_config("bg_black", background="black")
            self.output_textbox.tag_config("bg_red", background="red")
            self.output_textbox.tag_config("bg_green", background="green")
            self.output_textbox.tag_config("bg_yellow", background="yellow")
            self.output_textbox.tag_config("bg_blue", background="blue")
            self.output_textbox.tag_config("bg_magenta", background="magenta")
            self.output_textbox.tag_config("bg_cyan", background="cyan")
            self.output_textbox.tag_config("bg_white", background="gray90") # Light bg

            # Add specific tags if needed, e.g., for error highlighting
            self.output_textbox.tag_config("error_log", foreground="red")
            self.output_textbox.tag_config("warning_log", foreground="#FFA500") # Orange
            self.output_textbox.tag_config("success_log", foreground="green")
            self.output_textbox.tag_config("info_log", foreground="gray50") # For less critical info

        except Exception as e:
            # --- MODIFICATION: Suppress error output ---
            # print(f"Error configuring text tags: {e}")
            # try:
            #     self.output_textbox.configure(state="normal")
            #     self.output_textbox.insert("end", f"\nCRITICAL: Error configuring text colors: {e}\n", ("error_log",))
            #     self.output_textbox.configure(state="disabled")
            # except: pass
            pass # Silently ignore tag configuration errors
            # --- END MODIFICATION ---

    # --- get_string --- (Keep existing code)
    def get_string(self, key, default="", **kwargs):
        try:
            template = LANGUAGES[self.current_lang].get(key, default)
            if not template and default == "": # If default is not provided, try English
                 template = LANGUAGES['en'].get(key, f"<{key}>")
            elif not template and default != "":
                 template = default # Use provided default if lang key missing
            elif not template: # Should not happen if default logic above works
                 template = f"<{key}>"

            template = template.replace("\\n", "\n")
            return template.format(**kwargs)
        except KeyError: # Fallback to English if current lang doesn't exist at all
            try:
                template = LANGUAGES['en'].get(key, default)
                if not template:
                    template = f"<Missing Key: {key}>"
                template = template.replace("\\n", "\n")
                print(f"Warning: Language '{self.current_lang}' not found, using English fallback for key '{key}'.")
                return template.format(**kwargs)
            except Exception as e:
                 print(f"Error formatting string for key '{key}' in English fallback: {e}")
                 return f"<Lang Error: {key}>"
        except Exception as e:
            print(f"Error formatting string for key '{key}': {e}")
            return f"<Format Error: {key}>"

    # --- change_language --- (Keep existing code)
    def change_language(self, selected_language_name):
        new_lang_code = self.languages_map.get(selected_language_name)
        if new_lang_code and new_lang_code != self.current_lang:
            self.current_lang = new_lang_code
            self.update_ui_language()

    # --- update_ui_language --- (Keep existing code)
    def update_ui_language(self):
        """Updates all UI elements with text from the current language."""
        self.title(self.get_string('title'))

        # Update status based on current state
        current_status_text = self.status_label.cget("text") # Get the raw text
        if self.is_running:
            running_script_name = "script" # Default
            if self.get_string('status_extract_running') in current_status_text:
                 running_script_name = self.get_string('button_2_extract') # Use button text for sequence
            else:
                 # Find which button is disabled (could be improved)
                 for sid, btn in self.buttons.items():
                    if btn.cget("state") == "disabled" and sid != 'terminate_button':
                        script_def_id = '3_edit' if sid == 'tbl_xliff_edit' else sid
                        script_def = self.script_definitions.get(script_def_id)
                        if script_def:
                            running_script_name = script_def[0] # Use script filename
                            break
            self.set_status(self.get_string('status_running', script_name=running_script_name))
        elif self.get_string('status_terminated') in current_status_text:
            self.set_status(self.get_string('status_terminated'))
        elif self.get_string('status_error') in current_status_text:
            self.set_status(self.get_string('status_error'))
        else: # Otherwise, set to Idle
             self.set_status(self.get_string('status_idle'))

        # Update Labels
        if hasattr(self, 'dat_label'):
            self.dat_label.configure(text=self.get_string('dat_files_label'))
        if hasattr(self, 'tbl_label'):
            self.tbl_label.configure(text=self.get_string('tbl_files_label'))
        if hasattr(self, 'lang_label'):
            self.lang_label.configure(text=self.get_string('lang_select_label'))
        if hasattr(self, 'xliff_note_label'):
            self.xliff_note_label.configure(text=self.get_string('xliff_editor_note'))
        # self.author_label.configure(text=...) # If needs translation

        # Update Buttons
        for script_id in self.dat_button_order:
             button_key = f"button_{script_id}"
             default_text = script_id.replace("_"," ").title()
             button_text = self.get_string(button_key, default=default_text)
             if script_id in self.buttons:
                 self.buttons[script_id].configure(text=button_text)

        if hasattr(self, 'open_parser_button'):
             self.open_parser_button.configure(text=self.get_string('button_open_parser'))
        if hasattr(self, 'tbl_xliff_edit_button'):
             self.tbl_xliff_edit_button.configure(text=self.get_string('button_tbl_edit'))
        if hasattr(self, 'terminate_button'):
            self.terminate_button.configure(text=self.get_string('terminate_button'))

    # --- check_scripts_exist --- (MODIFIED: Log readiness only once)
    def check_scripts_exist(self):
        """Checks if defined script files exist, logs status only on first run."""
        all_exist = True
        should_log = not self.initial_check_done # <<< Only log if initial check not done

        if not os.path.isdir(MAIN_PATH):
             # Always log this critical error
             self.log_message(self.get_string('error_dir_not_found', path=MAIN_PATH), tags=("error_log",))
             self.disable_all_buttons()
             return False

        found_scripts_log = []
        missing_scripts_log = []
        checked_scripts = set()

        # Check TBL/DAT XLIFF Edit script first ('3_edit')
        script_3_def = self.script_definitions.get('3_edit')
        if script_3_def:
            script_3_rel_path, args_template = script_3_def
            script_3_abs_path = os.path.join(MAIN_PATH, script_3_rel_path)
            script_3_exists = os.path.isfile(script_3_abs_path)
            checked_scripts.add(script_3_rel_path)

            if not script_3_exists:
                if should_log: # <<< Log only on initial check
                    missing_scripts_log.append(self.get_string('error_script_not_found', path=script_3_abs_path))
                all_exist = False
                if '3_edit' in self.buttons: self.buttons['3_edit'].configure(state="disabled", fg_color="gray")
                if 'tbl_xliff_edit' in self.buttons: self.buttons['tbl_xliff_edit'].configure(state="disabled", fg_color="gray")
            else:
                if should_log: # <<< Log only on initial check
                    found_scripts_log.append(self.get_string('info_found_script', script_name=script_3_rel_path))
                # Check argument file existence for DAT button ('3_edit')
                xliff_path = args_template[0] if args_template else None
                arg_exists_or_not_needed = (not xliff_path) or os.path.exists(xliff_path)

                if xliff_path and not arg_exists_or_not_needed and should_log: # <<< Log warning only on initial check
                    warning_msg = self.get_string('warning_arg_file_not_found', script=script_3_rel_path, arg_path=xliff_path)
                    self.log_message(f"WARNING: {warning_msg}", tags=("warning_log",))

                # Enable/Disable based on script existence (and arg for DAT one)
                if '3_edit' in self.buttons:
                    self.buttons['3_edit'].configure(state="normal" if arg_exists_or_not_needed else "disabled")
                if 'tbl_xliff_edit' in self.buttons:
                    self.buttons['tbl_xliff_edit'].configure(state="normal") # TBL button doesn't depend on arg file

        # Check remaining scripts
        for script_id, (script_rel_path, args_template) in self.script_definitions.items():
            if script_rel_path in checked_scripts: continue

            script_abs_path = os.path.join(MAIN_PATH, script_rel_path)
            script_exists = os.path.isfile(script_abs_path)
            checked_scripts.add(script_rel_path)
            button = self.buttons.get(script_id)

            if not script_exists:
                if should_log: # <<< Log only on initial check
                    missing_scripts_log.append(self.get_string('error_script_not_found', path=script_abs_path))
                all_exist = False
                if button: button.configure(state="disabled", fg_color="gray")
            else:
                if should_log: # <<< Log only on initial check
                    found_scripts_log.append(self.get_string('info_found_script', script_name=script_rel_path))
                if button: button.configure(state="normal") # Enable if script exists

        # Log results only on the first check
        if should_log:
            for msg in missing_scripts_log:
                self.log_message(msg, tags=("error_log",))
            if found_scripts_log:
                 self.log_message("\n".join(found_scripts_log), tags=("success_log",))
            if all_exist and found_scripts_log:
                self.log_message(self.get_string('info_scripts_found', path=MAIN_PATH))

        # Mark initial check as done AFTER potential logging
        self.initial_check_done = True # <<< Set flag

        # Final button state update based on running state (redundant with enable/disable logic?)
        if self.is_running:
             self.disable_all_buttons()
        # No need to explicitly call enable_all_buttons here, states are set above.

        return all_exist

    # --- log_message --- (Keep existing code)
    def log_message(self, raw_message, tags=None):
        """Logs a message to the output textbox, parsing ANSI codes and applying optional tags."""
        try:
            self.output_textbox.configure(state="normal")
            message = str(raw_message)
            last_index = 0
            current_line_tags_set = set(tags) if tags else set()
            current_line_tags_set.update(self.current_tags)
            current_line_tags_tuple = tuple(sorted(list(current_line_tags_set)))

            for match in ANSI_COLOR_REGEX.finditer(message):
                start, end = match.span()
                if start > last_index:
                    self.output_textbox.insert("end", message[last_index:start], current_line_tags_tuple)

                codes = match.group(1).split(';')
                active_tags_set = set(current_line_tags_tuple)

                for code in codes:
                    tag = ANSI_CODE_TO_TAG.get(code)
                    if tag == 'reset':
                        active_tags_set = set(tags) if tags else set()
                        self.current_tags.clear()
                    elif tag:
                        if tag.startswith("fg_"):
                            active_tags_set = {t for t in active_tags_set if not t.startswith("fg_")}
                            self.current_tags = {t for t in self.current_tags if not t.startswith("fg_")}
                        if tag.startswith("bg_"):
                            active_tags_set = {t for t in active_tags_set if not t.startswith("bg_")}
                            self.current_tags = {t for t in self.current_tags if not t.startswith("bg_")}
                        active_tags_set.add(tag)
                        self.current_tags.add(tag)

                current_line_tags_tuple = tuple(sorted(list(active_tags_set)))
                last_index = end

            if last_index < len(message):
                self.output_textbox.insert("end", message[last_index:], current_line_tags_tuple)

            self.output_textbox.insert("end", "\n")

            if ANSI_COLOR_REGEX.search(message) and message.rstrip().endswith('\x1B[0m'):
                 self.current_tags.clear()

            self.output_textbox.configure(state="disabled")
            self.output_textbox.see("end")

        except Exception as e:
             print(f"Error logging message to GUI: {e}\nMessage was: {raw_message}")
             try:
                  self.output_textbox.configure(state="normal")
                  if "text doesn't contain characters" not in str(e):
                       self.output_textbox.insert("end", str(raw_message) + "\n", ("error_log",))
                  self.output_textbox.configure(state="disabled")
                  self.output_textbox.see("end")
             except: pass

    # --- set_status --- (Keep existing code)
    def set_status(self, message):
        """Updates the status label text."""
        self.status_label.configure(text=str(message))

    # --- disable_all_buttons --- (Keep existing code)
    def disable_all_buttons(self, terminating=False):
        """Disables script-running buttons. Leaves 'Open Folder' enabled."""
        for script_id, button in self.buttons.items():
            button.configure(state="disabled")

        if self.is_running and self.current_process_pid and not terminating:
             self.terminate_button.configure(state="normal")
        else:
             self.terminate_button.configure(state="disabled")

        if hasattr(self, 'open_parser_button'):
             self.open_parser_button.configure(state="normal")

    # --- enable_all_buttons --- (Keep existing code, relies on check_scripts_exist)
    def enable_all_buttons(self):
        """Enables buttons based on script existence and running state."""
        if self.is_running:
            self.disable_all_buttons() # Keep disabled if running
            return

        # Re-run the check to set states based on file existence (will not log again)
        self.check_scripts_exist()

        # Ensure terminate button is disabled when not running
        if hasattr(self, 'terminate_button'):
            self.terminate_button.configure(state="disabled")
        # Ensure open folder button is enabled
        if hasattr(self, 'open_parser_button'):
            self.open_parser_button.configure(state="normal")

    # --- prompt_for_dat_path_and_run --- (Keep existing code - Step 1)
    def prompt_for_dat_path_and_run(self):
        """Prompts user for DAT folder and runs disassemble script."""
        if self.is_running:
            tkinter.messagebox.showwarning(self.get_string('warn_already_running'), self.get_string('warn_already_running_msg'))
            return

        script_id = '1_disassemble'
        script_def = self.script_definitions.get(script_id)
        script_path = os.path.join(MAIN_PATH, script_def[0]) if script_def else ''
        if not script_def or not os.path.isfile(script_path):
            self.log_message(self.get_string('error_script_not_found_run', path=script_path), tags=("error_log",))
            return

        self.log_message(self.get_string('dat_folder_prompt_log'))
        button_text = self.get_string(f'button_{script_id}', default="Select Folder")
        dialog_title = self.get_string('dat_folder_prompt_title', button_text=button_text)

        initial_dir = self.last_dat_input_dir if self.last_dat_input_dir and os.path.isdir(self.last_dat_input_dir) else MAIN_PATH

        folder_path = tkinter.filedialog.askdirectory(
            title=dialog_title,
            initialdir=initial_dir
        )

        if folder_path:
            self.log_message(self.get_string('dat_folder_selected_log', path=folder_path))
            self.last_dat_input_dir = folder_path # <<< STORE THE PATH
            # Run with DECOMPILE_MODE=True (default)
            self.run_script_thread(script_id, extra_args=['-i', folder_path])
        else:
            self.log_message(self.get_string('dat_folder_cancel_log'))

    # --- prompt_compile_mode_and_run --- (Keep existing code - Step 5)
    def prompt_compile_mode_and_run(self, script_id):
        """Prompts for compile mode and runs the compile script."""
        if self.is_running:
             tkinter.messagebox.showwarning(self.get_string('warn_already_running'), self.get_string('warn_already_running_msg'))
             return

        script_def = self.script_definitions.get(script_id)
        script_path = os.path.join(MAIN_PATH, script_def[0]) if script_def else ''
        if not script_def or not os.path.isfile(script_path):
             self.log_message(self.get_string('error_script_not_found_run', path=script_path), tags=("error_log",))
             return

        dialog = customtkinter.CTkInputDialog(
            title=self.get_string('compile_mode_title'),
            text=f"{self.get_string('compile_mode_prompt')}\n\n{self.get_string('compile_mode_1')}\n{self.get_string('compile_mode_2')}"
        )
        choice = dialog.get_input()

        compile_arg = None
        if choice == "1":
            compile_arg = "--only-translated=true" # Assuming py2dat uses this arg
        elif choice == "2":
            compile_arg = "--only-translated=false" # Assuming py2dat uses this arg
        else:
            if choice is not None and choice.strip() != "":
                 tkinter.messagebox.showwarning(self.get_string('compile_mode_title'), self.get_string('compile_mode_invalid'))
            return # Cancelled or invalid input

        self.run_script_thread(script_id, extra_args=[compile_arg])

    # --- open_parser_folder --- (Keep existing code)
    def open_parser_folder(self):
        """Opens the MAIN_PATH/Parser folder in the system's file explorer."""
        if not os.path.isdir(PARSER_FOLDER_PATH):
            try:
                os.makedirs(PARSER_FOLDER_PATH)
                self.log_message(f"Created missing folder: {PARSER_FOLDER_PATH}", tags=("info_log",))
            except OSError as e:
                error_msg = self.get_string('error_open_folder', path=PARSER_FOLDER_PATH, e=f"Could not create directory: {e}")
                self.log_message(error_msg, tags=("error_log",))
                tkinter.messagebox.showerror(self.get_string('warning_title'), f"Could not create folder:\n{PARSER_FOLDER_PATH}\n\n{e}")
                return

        self.log_message(self.get_string('info_opening_folder', path=PARSER_FOLDER_PATH))
        try:
            if platform.system() == "Windows":
                os.startfile(os.path.normpath(PARSER_FOLDER_PATH))
            elif platform.system() == "Darwin": # macOS
                subprocess.run(['open', PARSER_FOLDER_PATH], check=True)
            else: # Linux and other Unix-like
                subprocess.run(['xdg-open', PARSER_FOLDER_PATH], check=True)
        except FileNotFoundError:
             error_msg = self.get_string('error_open_folder', path=PARSER_FOLDER_PATH, e="Required command (e.g., xdg-open or open) not found.")
             self.log_message(error_msg, tags=("error_log",))
             tkinter.messagebox.showerror(self.get_string('error_unexpected', e=''), error_msg)
        except Exception as e:
            error_msg = self.get_string('error_open_folder', path=PARSER_FOLDER_PATH, e=e)
            self.log_message(error_msg, tags=("error_log",))
            tkinter.messagebox.showerror(self.get_string('error_unexpected', e=''), error_msg)

    # --- run_script_thread --- (Keep existing code - used by 1, 3, 4, 5, TBL edit)
    def run_script_thread(self, script_id, extra_args=None):
        """Starts a thread to execute a *single* defined script."""
        if self.is_running:
            print(f"Attempted to run script '{script_id}' while another is running.")
            tkinter.messagebox.showwarning(self.get_string('warn_already_running'), self.get_string('warn_already_running_msg'))
            return

        actual_script_id = '3_edit' if script_id == 'tbl_xliff_edit' else script_id
        script_def = self.script_definitions.get(actual_script_id)
        if not script_def:
            self.log_message(f"ERROR: Script definition not found for ID: {actual_script_id} (requested: {script_id})", tags=("error_log",))
            return

        script_rel_path, base_args = script_def
        script_abs_path = os.path.join(MAIN_PATH, script_rel_path)

        if not os.path.isfile(script_abs_path):
            self.log_message(self.get_string('error_script_not_found_run', path=script_abs_path), tags=("error_log",))
            return

        final_args = extra_args if extra_args is not None else base_args
        final_args_str = [str(arg) for arg in final_args if arg is not None]
        command = [PYTHON_EXECUTABLE, "-u", script_abs_path] + final_args_str

        self.is_running = True
        self.process = None
        self.current_process_pid = None
        self.disable_all_buttons()
        self.set_status(self.get_string('status_running', script_name=script_rel_path))
        log_args_display = " ".join(f'"{arg}"' if " " in arg else arg for arg in final_args_str)
        self.log_message(self.get_string('log_running', script_name=script_rel_path, args=log_args_display))

        thread = threading.Thread(target=self.execute_script, args=(command, script_rel_path), daemon=True)
        thread.start()

    # --- execute_script --- (Keep existing code - runs ONE script)
    def execute_script(self, command_list, script_name_for_logging):
        """Executes the script command in a subprocess and reads output. (Runs in a thread)"""
        try:
            process_env = os.environ.copy()
            process_env["PYTHONIOENCODING"] = "utf-8"
            python_path = os.pathsep.join(sys.path + [MAIN_PATH])
            process_env["PYTHONPATH"] = python_path

            self.process = subprocess.Popen(
                command_list,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.PIPE,
                shell=False,
                cwd=MAIN_PATH,
                encoding='utf-8',
                errors='replace',
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0,
                bufsize=1,
                env=process_env
            )
            self.current_process_pid = self.process.pid

            for line in iter(self.process.stdout.readline, ''):
                if not line: break
                self.message_queue.put({"type": "output", "data": line.rstrip('\r\n')})

            self.process.stdout.close()
            return_code = self.process.wait()
            pid_ended = self.current_process_pid # Capture PID before clearing
            self.current_process_pid = None

            current_status = self.status_label.cget("text") # Check current status text
            is_terminated_status = self.get_string('status_terminated') in current_status

            if is_terminated_status:
                 self.message_queue.put({"type": "output", "data": f"(Process {pid_ended} ended with code: {return_code} after termination request)"})
                 # Status already set to Terminated
            elif return_code == 0:
                status_msg = self.get_string('status_finished', script_name=script_name_for_logging)
                self.message_queue.put({"type": "status", "data": status_msg})
                # Let process_queue log the finish status
            else:
                 termination_codes_win = (1, -1, 0xC000013A, -1073741510, 0xFFFFFFFF)
                 termination_codes_unix = (signal.SIGTERM * -1, signal.SIGINT * -1, 130) # 130 is common for Ctrl+C (SIGINT)

                 is_termination_code = False
                 if sys.platform == "win32" and return_code in termination_codes_win:
                      is_termination_code = True
                 elif sys.platform != "win32" and return_code in termination_codes_unix:
                      is_termination_code = True

                 if is_termination_code:
                      status_msg = self.get_string('status_terminated')
                      self.message_queue.put({"type": "status", "data": status_msg})
                      self.message_queue.put({"type": "output", "data": f"({script_name_for_logging} likely terminated by signal - Exit code: {return_code})"})
                 else:
                      error_base_msg = f"{script_name_for_logging} failed"
                      exit_code_msg = f" (Exit code: {return_code})"
                      self.message_queue.put({"type": "error", "data": error_base_msg + exit_code_msg})

        except FileNotFoundError:
             self.message_queue.put({"type": "error", "data": f"ERROR: File not found. Command: {' '.join(command_list)}"})
        except Exception as e:
             error_msg = self.get_string('error_unexpected', e=e)
             self.message_queue.put({"type": "error", "data": error_msg})
             import traceback
             traceback.print_exc()
        finally:
            self.message_queue.put({"type": "done"})
            self.process = None
            if self.current_process_pid == pid_ended: # Avoid clearing if a new process started quickly
                 self.current_process_pid = None

    # --- _run_command_and_wait --- (Keep existing code - helper for sequence)
    def _run_command_and_wait(self, command_list, script_name_for_logging):
        """Executes a command, logs output via queue, and returns exit code. (BLOCKING)"""
        process = None
        try:
            process_env = os.environ.copy()
            process_env["PYTHONIOENCODING"] = "utf-8"
            python_path = os.pathsep.join(sys.path + [MAIN_PATH])
            process_env["PYTHONPATH"] = python_path

            # Log start of this specific command within the sequence
            log_args_display = " ".join(f'"{arg}"' if " " in arg else arg for arg in command_list[2:])
            self.message_queue.put({"type": "output", "data": f"--- Running step: {script_name_for_logging} {log_args_display} ---"})

            process = subprocess.Popen(
                command_list,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.PIPE,
                shell=False,
                cwd=MAIN_PATH,
                encoding='utf-8',
                errors='replace',
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0,
                bufsize=1,
                env=process_env
            )
            local_pid = process.pid

            for line in iter(process.stdout.readline, ''):
                if not line: break
                self.message_queue.put({"type": "output", "data": line.rstrip('\r\n')})

            process.stdout.close()
            return_code = process.wait()
            # Log completion of this step
            self.message_queue.put({"type": "output", "data": f"--- Step finished: {script_name_for_logging} (Exit code: {return_code}) ---"})
            return return_code

        except FileNotFoundError:
             self.message_queue.put({"type": "error", "data": f"ERROR: File not found for step {script_name_for_logging}. Command: {' '.join(command_list)}"})
             return -1 # Indicate failure
        except Exception as e:
             error_msg = f"Unexpected error running step {script_name_for_logging}: {e}"
             self.message_queue.put({"type": "error", "data": error_msg})
             import traceback
             traceback.print_exc()
             return -1 # Indicate failure
        finally:
             if process and process.poll() is None:
                  try: process.kill()
                  except Exception: pass

    # --- run_extract_strings_sequence --- (MODIFIED: Prompt for DAT path if needed - Step 2 start)
    def run_extract_strings_sequence(self):
        """Starts the multi-step string extraction process in a thread, prompting for DAT path if necessary."""
        if self.is_running:
            tkinter.messagebox.showwarning(self.get_string('warn_already_running'), self.get_string('warn_already_running_msg'))
            return

        # --- MODIFIED CHECK: Prompt if path is missing ---
        if not self.last_dat_input_dir or not os.path.isdir(self.last_dat_input_dir):
            self.log_message(self.get_string('extract_prompt_dat_folder_log'), tags=("warning_log",))
            # Use specific title for this prompt
            dialog_title = self.get_string('extract_prompt_dat_folder_title')
            folder_path = tkinter.filedialog.askdirectory(
                title=dialog_title,
                initialdir=MAIN_PATH # Suggest base path
            )

            if folder_path and os.path.isdir(folder_path):
                self.log_message(self.get_string('dat_folder_selected_log', path=folder_path))
                self.last_dat_input_dir = folder_path # Store the path
            else:
                self.log_message(self.get_string('dat_folder_cancel_log'))
                # Show the error message if selection was cancelled or invalid
                tkinter.messagebox.showerror(self.get_string('warning_title'), self.get_string('error_no_dat_path'))
                return # Stop if no valid path is provided
        # --- END MODIFIED CHECK ---

        # --- Proceed if self.last_dat_input_dir is now valid ---
        self.is_running = True
        self.process = None
        self.current_process_pid = None
        self.disable_all_buttons()
        self.set_status(self.get_string('status_extract_running'))
        self.log_message(self.get_string('log_extract_start'))

        thread = threading.Thread(target=self._execute_extract_sequence, daemon=True)
        thread.start()

    # --- _execute_extract_sequence --- (Keep existing code - runs in thread for Step 2)
    def _execute_extract_sequence(self):
        """Performs the string extraction steps: rename, run false, run extract, delete, rename back."""
        sequence_success = True
        error_occurred = False
        orig_py_path = os.path.join(MAIN_PATH, DATA_TO_PY_FOLDER)
        temp_py_path = os.path.join(MAIN_PATH, DATA_TO_PY_DECOMPILE_TEMP_FOLDER)
        orig_py_exists_at_start = os.path.isdir(orig_py_path)

        # Defensive check - should have been handled by caller, but double-check
        if not self.last_dat_input_dir or not os.path.isdir(self.last_dat_input_dir):
             self.message_queue.put({"type": "error", "data": "CRITICAL: DAT input directory is missing in sequence thread."})
             self.message_queue.put({"type": "done"})
             return

        try:
            # 1. Rename original data_to_py to data_to_py_DECOMPILE
            if orig_py_exists_at_start:
                self.message_queue.put({"type": "output", "data": self.get_string('log_rename_orig_to_temp', orig=DATA_TO_PY_FOLDER, temp=DATA_TO_PY_DECOMPILE_TEMP_FOLDER)})
                try:
                    if os.path.exists(temp_py_path):
                         shutil.rmtree(temp_py_path)
                         self.message_queue.put({"type": "output", "data": f"  (Note: Removed pre-existing temp folder '{DATA_TO_PY_DECOMPILE_TEMP_FOLDER}')", "tags":("info_log",)})
                    shutil.move(orig_py_path, temp_py_path)
                except Exception as e:
                    self.message_queue.put({"type": "error", "data": self.get_string('log_rename_failed', orig=DATA_TO_PY_FOLDER, temp=DATA_TO_PY_DECOMPILE_TEMP_FOLDER, e=e)})
                    error_occurred = True
                    sequence_success = False
                    return # Jumps to finally block
            else:
                self.message_queue.put({"type": "output", "data": self.get_string('error_orig_folder_missing', path=DATA_TO_PY_FOLDER), "tags": ("warning_log",)})

            # 2. Run dat2py_batch.py with DECOMPILE_MODE = False
            # self.message_queue.put({"type": "output", "data": self.get_string('log_run_disasm_extract')}) # Handled by _run_command_and_wait
            script_def_d2p = self.script_definitions.get('1_disassemble')
            script_path_d2p = os.path.join(MAIN_PATH, script_def_d2p[0])
            cmd_d2p = [PYTHON_EXECUTABLE, "-u", script_path_d2p, "-i", self.last_dat_input_dir, "--decompile-mode", "false"]
            exit_code_d2p = self._run_command_and_wait(cmd_d2p, f"{script_def_d2p[0]} (Extract Mode)") # Pass descriptive name

            if exit_code_d2p != 0:
                self.message_queue.put({"type": "error", "data": self.get_string('log_run_disasm_extract_fail')})
                error_occurred = True
                sequence_success = False
                return # Jumps to finally block

            # 3. Run py_to_xliff.py
            if not os.path.isdir(orig_py_path):
                 self.message_queue.put({"type": "error", "data": f"ERROR: Folder '{DATA_TO_PY_FOLDER}' was not created by disassembly (extract mode). Cannot run extraction."})
                 error_occurred = True
                 sequence_success = False
                 return # Jumps to finally block

            # self.message_queue.put({"type": "output", "data": self.get_string('log_run_pytoxliff')}) # Handled by _run_command_and_wait
            script_def_p2x = self.script_definitions.get('2_extract')
            script_path_p2x = os.path.join(MAIN_PATH, script_def_p2x[0])
            cmd_p2x = [PYTHON_EXECUTABLE, "-u", script_path_p2x]
            exit_code_p2x = self._run_command_and_wait(cmd_p2x, script_def_p2x[0]) # Pass script name

            if exit_code_p2x != 0:
                self.message_queue.put({"type": "error", "data": self.get_string('log_run_pytoxliff_fail')})
                error_occurred = True
                sequence_success = False # Mark failure but continue to cleanup

        except Exception as e:
            self.message_queue.put({"type": "error", "data": f"Unexpected error during extraction sequence logic: {e}"})
            error_occurred = True
            sequence_success = False
            import traceback
            traceback.print_exc()
        finally:
            # --- Cleanup Phase ---
            try:
                # 4. Delete the temporary data_to_py (created with DECOMPILE_MODE=False)
                if os.path.isdir(orig_py_path):
                    self.message_queue.put({"type": "output", "data": self.get_string('log_delete_temp_py', path=DATA_TO_PY_FOLDER)})
                    try:
                        shutil.rmtree(orig_py_path)
                    except Exception as e:
                        self.message_queue.put({"type": "error", "data": self.get_string('log_delete_failed', path=DATA_TO_PY_FOLDER, e=e)})
                        error_occurred = True
                # else: # Log if it wasn't there (might indicate earlier failure)
                #    if sequence_success: # Only warn if sequence was otherwise ok so far
                #        self.message_queue.put({"type": "output", "data": self.get_string('error_temp_folder_missing_del', path=DATA_TO_PY_FOLDER), "tags":("warning_log",)})


                # 5. Rename data_to_py_DECOMPILE back to data_to_py
                if orig_py_exists_at_start and os.path.isdir(temp_py_path):
                    self.message_queue.put({"type": "output", "data": self.get_string('log_rename_temp_to_orig', temp=DATA_TO_PY_DECOMPILE_TEMP_FOLDER, orig=DATA_TO_PY_FOLDER)})
                    try:
                        if os.path.exists(orig_py_path):
                             shutil.rmtree(orig_py_path)
                             self.message_queue.put({"type": "output", "data": f"  (Note: Removed existing target '{DATA_TO_PY_FOLDER}' before restore)", "tags":("info_log",)})
                        shutil.move(temp_py_path, orig_py_path)
                    except Exception as e:
                        self.message_queue.put({"type": "error", "data": self.get_string('error_restore_failed', temp=DATA_TO_PY_DECOMPILE_TEMP_FOLDER, orig=DATA_TO_PY_FOLDER, e=e)})
                        error_occurred = True
                elif orig_py_exists_at_start and not os.path.isdir(temp_py_path):
                     self.message_queue.put({"type": "error", "data": self.get_string('error_temp_folder_missing_restore', path=DATA_TO_PY_DECOMPILE_TEMP_FOLDER)})
                     error_occurred = True

            except Exception as final_e:
                 self.message_queue.put({"type": "error", "data": f"CRITICAL error during cleanup phase: {final_e}"})
                 error_occurred = True

            # --- Final Status Update ---
            if error_occurred:
                final_log_msg = self.get_string('log_extract_complete_errors')
                final_status = self.get_string('status_error')
            else:
                final_log_msg = self.get_string('log_extract_complete')
                # Decide final status: finished (specific) or idle? Let's use idle.
                final_status = self.get_string('status_idle')

            self.message_queue.put({"type": "output", "data": final_log_msg})
            # Set final status only if it's not already an error set during the process
            # Let 'done' signal handle the final status unless it was an error.
            if error_occurred:
                self.message_queue.put({"type": "status", "data": final_status})

            self.message_queue.put({"type": "done"}) # Signal thread completion

    # --- process_queue --- (Keep existing code)
    def process_queue(self):
        """Processes messages from the execution thread queue."""
        try:
            while True:
                message = self.message_queue.get_nowait()
                msg_type = message.get("type")
                msg_data = message.get("data")
                msg_tags = message.get("tags") # Get optional tags

                if msg_type == "output":
                    self.log_message(msg_data, tags=msg_tags)
                elif msg_type == "status":
                    self.set_status(msg_data)
                    # Log significant status changes (Finished, Terminated, Error?)
                    if self.get_string('status_finished', script_name='') in msg_data or \
                       self.get_string('status_terminated') in msg_data or \
                       self.get_string('status_error') in msg_data:
                         self.log_message(f"--- {msg_data} ---", tags=msg_tags) # Log status change clearly
                elif msg_type == "error":
                    # Set status and log with error tag
                    self.set_status(self.get_string('status_error'))
                    self.log_message(self.get_string('log_error', error_message=msg_data), tags=("error_log",))
                elif msg_type == "input_request":
                     # Not currently used
                     self.prompt_for_input(msg_data)
                elif msg_type == "done":
                    was_running = self.is_running # Check state before changing
                    self.is_running = False
                    self.process = None
                    # Don't clear PID here, execute_script/sequence handles it upon completion/termination
                    current_status = self.status_label.cget("text")

                    # Set status to Idle ONLY if it wasn't explicitly set to Error or Terminated
                    if was_running and not (self.get_string('status_terminated') in current_status or
                                           self.get_string('status_error') in current_status):
                         self.set_status(self.get_string('status_idle'))
                         # Optionally log transition to idle if coming from success
                         if self.get_string('status_finished', script_name='') in current_status:
                              self.log_message("--- Status: Ожидание ---") # Or use idle string

                    self.enable_all_buttons() # Re-enable buttons

        except queue.Empty:
            pass
        except Exception as e:
             print(f"Error processing queue: {e}")
             self.log_message(f"Error processing message queue: {e}", tags=("error_log",))
             # Try to recover state if possible
             if self.is_running: # If queue error happens while running, try to reset state
                  self.is_running = False
                  self.enable_all_buttons()
                  self.set_status(self.get_string('status_error') + " (Queue Error)")
        finally:
            self.after(100, self.process_queue)

    # --- prompt_for_input --- (Keep existing code - UNUSED)
    def prompt_for_input(self, prompt_message=None):
        """Prompts user for input to send to the running script's stdin (UNUSED)."""
        if not self.process or not self.process.stdin or self.process.poll() is not None:
             self.log_message(self.get_string('error_input_fail'), tags=("warning_log",))
             return

        if not prompt_message:
             prompt_message = self.get_string('input_prompt_default')

        dialog = customtkinter.CTkInputDialog(text=prompt_message, title=self.get_string('input_prompt_title'))
        user_input = dialog.get_input()

        if user_input is not None:
            self.log_message(self.get_string('log_input_sent', user_input=user_input))
            try:
                if not self.process.stdin.closed:
                    self.process.stdin.write((user_input + '\n').encode('utf-8'))
                    self.process.stdin.flush()
                else:
                     self.log_message("ERROR: Process stdin is closed.", tags=("error_log",))
            except Exception as e:
                self.log_message(self.get_string('error_send_input_fail', e=e), tags=("error_log",))
        else:
            self.log_message(self.get_string('log_input_cancelled'))

    # --- terminate_process --- (Keep existing code - uses PID)
    def terminate_process(self):
        """Attempts to terminate the running script process using the stored PID."""
        pid_to_terminate = self.current_process_pid

        if self.is_running and pid_to_terminate:
            self.log_message(self.get_string('log_terminate_attempt') + f" (PID: {pid_to_terminate})")
            self.set_status(self.get_string('status_terminated')) # Set status immediately
            self.disable_all_buttons(terminating=True) # Disable terminate button too

            terminated_ok = False
            try:
                if sys.platform == "win32":
                    # Using taskkill /T /F to terminate process tree forcefully
                    result = subprocess.run(['taskkill', '/F', '/T', '/PID', str(pid_to_terminate)],
                                            capture_output=True, text=True, check=False, creationflags=subprocess.CREATE_NO_WINDOW)
                    if result.returncode == 0:
                        self.log_message(f"Taskkill successful for PID tree {pid_to_terminate}.")
                        terminated_ok = True
                    # Error code 128 means process not found (already terminated)
                    elif result.returncode == 128 or ("not found" in result.stderr.lower()):
                        self.log_message(f"Process (PID: {pid_to_terminate}) already ended.")
                        terminated_ok = True # Treat as ok, it's gone
                    else:
                         self.log_message(f"Taskkill failed (Code: {result.returncode}): {result.stderr.strip()}", tags=("warning_log",))

                else: # Linux/macOS
                    try:
                        # Send SIGTERM to process group
                        pgid = os.getpgid(pid_to_terminate)
                        os.killpg(pgid, signal.SIGTERM)
                        self.log_message(f"SIGTERM sent to process group (PGID: {pgid}).")
                        terminated_ok = True # Assume signal sent is ok for now
                    except ProcessLookupError:
                        self.log_message(f"Process group for PID {pid_to_terminate} not found (already ended).")
                        terminated_ok = True
                    except AttributeError: # Fallback if getpgid fails
                         try:
                              os.kill(pid_to_terminate, signal.SIGTERM)
                              self.log_message(f"SIGTERM sent to process (PID: {pid_to_terminate}).")
                              terminated_ok = True
                         except ProcessLookupError:
                              self.log_message(f"Process (PID: {pid_to_terminate}) not found (already ended).")
                              terminated_ok = True
                         except Exception as e_kill:
                              self.log_message(f"Fallback kill failed: {e_kill}", tags=("error_log",))

            except Exception as e:
                self.log_message(self.get_string('log_terminate_error', e=e), tags=("error_log",))

            # Final state update
            self.is_running = False # Mark as not running
            self.process = None # Clear process handle
            # Clear PID only if termination seemed successful or process was already gone
            # Otherwise, leave it in case execute_script thread finds it ended with error code
            # if terminated_ok:
            #     self.current_process_pid = None # Let execute_script clear it on natural exit/error
            # Enable buttons after a short delay to allow queue processing? Or let 'done' signal handle it.
            # Let process_queue handle enabling buttons via the 'done' signal from the thread.
            # Keep status as Terminated.
            self.set_status(self.get_string('status_terminated'))

        else:
            self.log_message("No running process with known PID to terminate.", tags=("warning_log",))
            if not self.is_running:
                 self.enable_all_buttons() # Ensure buttons are correct if state was wrong

    # --- on_closing --- (Keep existing code)
    def on_closing(self):
        """Handles the window close event."""
        if self.is_running:
            if tkinter.messagebox.askyesno(self.get_string('confirm_exit_title'), self.get_string('confirm_exit_msg')):
                self.terminate_process()
                # Give a moment for cleanup attempts before destroying window
                self.after(500, self.destroy) # Increased delay slightly
            else:
                return # User cancelled exit
        else:
            self.destroy() # Exit immediately if nothing is running

if __name__ == "__main__":
    # --- Initial Startup Checks ---
    lang = "ru" # Use RU for startup errors initially
    errors = []
    if not PYTHON_EXECUTABLE or not os.path.isfile(PYTHON_EXECUTABLE):
         msg = LANGUAGES[lang].get('startup_error_python_not_found', 'Python executable error').format(path=PYTHON_EXECUTABLE)
         errors.append(msg)
    if not os.path.isdir(MAIN_PATH) or not os.path.isdir(START_DIR):
         msg = LANGUAGES[lang].get('startup_error_main_path_not_found', "Path error.").format(main_path=MAIN_PATH, start_path=START_DIR)
         errors.append(msg)

    if errors:
         title = LANGUAGES[lang].get('startup_error_title', 'Startup Error')
         full_error_msg = "\n\n".join(errors)
         root = tkinter.Tk()
         root.withdraw()
         tkinter.messagebox.showerror(title, full_error_msg)
         root.destroy()
         sys.exit(1)
    # --- End Startup Checks ---

    app = App()
    app.protocol("WM_DELETE_WINDOW", app.on_closing)
    app.mainloop()
# --- END OF FILE launcher.py ---