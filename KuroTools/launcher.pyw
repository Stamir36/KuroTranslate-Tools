import tkinter
import tkinter.messagebox
import tkinter.filedialog # Added for askdirectory
import customtkinter # type: ignore
import subprocess
import threading
import queue
import os
import sys
import signal
import re # Для парсинга ANSI кодов
import time # Added for potential future use, like delays
import platform # Для открытия папки

# --- Configuration ---
customtkinter.set_appearance_mode("System")
customtkinter.set_default_color_theme("blue")

script_dir = os.path.dirname(os.path.abspath(__file__))
# --- Path Detection Logic ---
# More robust detection of MAIN_PATH and START_DIR
if os.path.basename(script_dir).lower() == "start":
     # If launcher is *inside* the Start folder
     MAIN_PATH = os.path.dirname(script_dir)
     START_DIR = script_dir
elif os.path.isdir(os.path.join(script_dir, "Start")):
     # If 'Start' folder is a subdirectory of where the launcher is
     MAIN_PATH = script_dir
     START_DIR = os.path.join(script_dir, "Start")
else:
     # Fallback: Assume launcher is in MAIN_PATH, and Start is a sibling
     MAIN_PATH = script_dir
     START_DIR = os.path.join(MAIN_PATH, "Start")
     print(f"Warning: Could not find 'Start' directory conventionally. Assuming MAIN_PATH='{MAIN_PATH}' and START_DIR='{START_DIR}'")
# --- End Path Detection ---

# --- Constants ---
PARSER_FOLDER_NAME = "Parser" # Имя папки для парсера TBL
PARSER_FOLDER_PATH = os.path.join(MAIN_PATH, PARSER_FOLDER_NAME)

# --- Python Executable ---
PYTHON_EXECUTABLE = sys.executable

# --- Encoding ---
CONSOLE_ENCODING = 'utf-8'

# --- Language Strings --- (Без изменений, как в предыдущей версии)
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
        'dat_files_label': "Work with DAT files", # Added
        'button_1_disassemble': "1. Disassemble DAT",
        'button_2_extract': "2. Extract Strings",
        'button_3_edit': "3. Edit Translation (DAT XLIFF)", # Clarified purpose
        'button_4_create_map': "4. Create Translation Map",
        'button_5_compile': "5. Compile DAT",
        'tbl_files_label': "Work with TBL files", # Added
        'button_open_parser': "Open Parsing Folder", # Added
        'button_tbl_edit': "Launch XLIFF Editor", # Added (Generic name)
        'xliff_editor_note': "XLIFF editor has auto-translation features.", # Added
        'lang_select_label': "Language:",
        'terminate_button': "Terminate Script",
        'startup_error_title': "Startup Error",
        'startup_error_python_not_found': "Python executable not found or invalid: {path}\nPlease ensure Python is installed and accessible.",
        'startup_error_main_path_not_found': "Main project directory ({main_path}) or Start directory ({start_path}) not found.\nPlease ensure the folder structure is correct. Exiting.", # Improved message
        'warning_title': "Warning",
        'warning_arg_file_not_found': "Argument file not found for {script}: {arg_path}",
        'dat_folder_prompt_title': "{button_text} - Select Folder",
        'dat_folder_prompt_log': "Prompting for DAT folder path...",
        'dat_folder_selected_log': "Selected DAT folder: {path}",
        'dat_folder_cancel_log': "Folder selection cancelled.",
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
        'dat_files_label': "Работа с DAT файлами", # Added
        'button_1_disassemble': "1. Дизассемблировать DAT",
        'button_2_extract': "2. Извлечь строки",
        'button_3_edit': "3. Редактировать перевод (DAT XLIFF)", # Clarified purpose
        'button_4_create_map': "4. Создать карту перевода",
        'button_5_compile': "5. Скомпилировать DAT",
        'tbl_files_label': "Работа с TBL файлами", # Added
        'button_open_parser': "Открыть папку парсинга", # Added
        'button_tbl_edit': "Запустить XLIFF редактор", # Added (Generic name)
        'xliff_editor_note': "XLIFF редактор имеет функции автоматического перевода.", # Added
        'lang_select_label': "Язык:",
        'terminate_button': "Прервать Скрипт",
        'startup_error_title': "Ошибка Запуска",
        'startup_error_python_not_found': "Исполняемый файл Python не найден или неверен: {path}\nУбедитесь, что Python установлен и доступен.",
        'startup_error_main_path_not_found': "Основная директория проекта ({main_path}) или папка Start ({start_path}) не найдена.\nУбедитесь в правильности структуры папок. Выход.", # Improved message
        'warning_title': "Предупреждение",
        'warning_arg_file_not_found': "Файл аргумента не найден для {script}: {arg_path}",
        'dat_folder_prompt_title': "{button_text} - Выберите папку",
        'dat_folder_prompt_log': "Запрос пути к папке с DAT...",
        'dat_folder_selected_log': "Выбрана папка DAT: {path}",
        'dat_folder_cancel_log': "Выбор папки отменен.",
    }
}


# --- ANSI Color Parsing --- (Без изменений)
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
            '1_disassemble': ("dat2py_batch.py", []),
            '2_extract': ("py_to_xliff.py", []),
            '3_edit': ("xliff_editor_gui.py", [xliff_file_path]), # Used by DAT button 3
            '4_create_map': ("inject_translations.py", []),
            '5_compile': ("py2dat_batch.py", []),
            # The TBL editor button will reuse '3_edit' definition but override args
        }
        self.dat_button_order = ['1_disassemble', '2_extract', '3_edit', '4_create_map', '5_compile']

        # --- Window Setup ---
        self.title(self.get_string('title'))
        # --- ИЗМЕНЕНИЕ 1: Уменьшена высота окна ---
        self.geometry(f"{1100}x650") # Было 680
        # --- КОНЕЦ ИЗМЕНЕНИЯ 1 ---
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
        self._configure_text_tags()

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
            # Assign command based on script_id
            if script_id == '1_disassemble':
                button.configure(command=self.prompt_for_dat_path_and_run)
            elif script_id == '5_compile':
                button.configure(command=lambda sid=script_id: self.prompt_compile_mode_and_run(sid))
            else: # Covers 2_extract, 3_edit, 4_create_map
                button.configure(command=lambda sid=script_id: self.run_script_thread(sid))
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
            # --- ИЗМЕНЕНИЕ 2: Запуск скрипта редактора БЕЗ аргументов ---
            # Используем ID '3_edit' для нахождения пути к скрипту,
            # но передаем пустой extra_args, чтобы НЕ использовать xliff_file_path
            command=lambda: self.run_script_thread('3_edit', extra_args=[])
            # --- КОНЕЦ ИЗМЕНЕНИЯ 2 ---
        )
        self.tbl_xliff_edit_button.grid(row=current_row, column=0, columnspan=2, padx=20, pady=(5, 5), sticky="ew")
        # Добавляем эту кнопку в словарь self.buttons для управления состоянием enable/disable
        self.buttons['tbl_xliff_edit'] = self.tbl_xliff_edit_button
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
        self.current_tags = set() # Keep track of active ANSI tags for log_message

        # --- Init ---
        self.update_ui_language()
        self.check_scripts_exist()
        self.after(100, self.process_queue)

    # --- Методы _configure_text_tags, get_string, change_language, update_ui_language ---
    # --- check_scripts_exist, log_message, set_status ---
    # --- disable_all_buttons, enable_all_buttons ---
    # --- prompt_for_dat_path_and_run, prompt_compile_mode_and_run ---
    # --- open_parser_folder, run_script_thread, execute_script ---
    # --- process_queue, prompt_for_input, terminate_process, on_closing ---
    # --- (Остаются БЕЗ ИЗМЕНЕНИЙ по сравнению с предыдущей версией) ---
    # (Вставьте сюда код всех этих методов из предыдущего ответа)
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
                print("Warning: Could not get CTkFont object, using default font for tags.")


            self.output_textbox.tag_config("bold", font=bold_font_tuple)
            self.output_textbox.tag_config("underline", underline=True)

            # Colors (same as before)
            self.output_textbox.tag_config("fg_black", foreground="black")
            self.output_textbox.tag_config("fg_red", foreground="red")
            self.output_textbox.tag_config("fg_green", foreground="green")
            self.output_textbox.tag_config("fg_yellow", foreground="#B8860B")
            self.output_textbox.tag_config("fg_blue", foreground="blue")
            self.output_textbox.tag_config("fg_magenta", foreground="magenta")
            self.output_textbox.tag_config("fg_cyan", foreground="cyan")
            self.output_textbox.tag_config("fg_white", foreground="white")
            self.output_textbox.tag_config("fg_bright_black", foreground="gray50")
            self.output_textbox.tag_config("fg_bright_red", foreground="#FF5555")
            self.output_textbox.tag_config("fg_bright_green", foreground="#55FF55")
            self.output_textbox.tag_config("fg_bright_yellow", foreground="#FFFF55")
            self.output_textbox.tag_config("fg_bright_blue", foreground="#5555FF")
            self.output_textbox.tag_config("fg_bright_magenta", foreground="#FF55FF")
            self.output_textbox.tag_config("fg_bright_cyan", foreground="#55FFFF")
            self.output_textbox.tag_config("fg_bright_white", foreground="#FFFFFF")
            self.output_textbox.tag_config("bg_black", background="black")
            self.output_textbox.tag_config("bg_red", background="red")
            self.output_textbox.tag_config("bg_green", background="green")
            self.output_textbox.tag_config("bg_yellow", background="yellow")
            self.output_textbox.tag_config("bg_blue", background="blue")
            self.output_textbox.tag_config("bg_magenta", background="magenta")
            self.output_textbox.tag_config("bg_cyan", background="cyan")
            self.output_textbox.tag_config("bg_white", background="white")

        except Exception as e:
            #print(f"Error configuring text tags: {e}")
            try:
                self.output_textbox.configure(state="normal")
                #self.output_textbox.insert("end", f"\nERROR: Could not configure text colors: {e}\n")
                self.output_textbox.configure(state="disabled")
            except: pass

    def get_string(self, key, default="", **kwargs):
        try:
            template = LANGUAGES[self.current_lang].get(key, default)
            if not template:
                template = f"<{key}>"
            template = template.replace("\\n", "\n")
            return template.format(**kwargs)
        except KeyError:
            try:
                template = LANGUAGES['en'].get(key, default)
                if not template:
                    template = f"<Missing Key: {key}>"
                template = template.replace("\\n", "\n")
                print(f"Warning: Language string '{key}' not found for '{self.current_lang}', using English fallback.")
                return template.format(**kwargs)
            except Exception:
                 return f"<Lang Error: {key}>"
        except Exception as e:
            print(f"Error formatting string for key '{key}': {e}")
            return f"<Format Error: {key}>"

    def change_language(self, selected_language_name):
        new_lang_code = self.languages_map.get(selected_language_name)
        if new_lang_code and new_lang_code != self.current_lang:
            self.current_lang = new_lang_code
            self.update_ui_language()

    def update_ui_language(self):
        """Updates all UI elements with text from the current language."""
        self.title(self.get_string('title'))
        if self.is_running:
             running_script_name = "script"
             for sid, btn in self.buttons.items():
                 if btn.cget("state") == "disabled":
                      script_def = self.script_definitions.get(sid)
                      if not script_def and sid == 'tbl_xliff_edit':
                          script_def = self.script_definitions.get('3_edit')
                      if script_def:
                           running_script_name = script_def[0]
                           break
             self.set_status(self.get_string('status_running', script_name=running_script_name))
        elif self.status_label.cget("text") == self.get_string('status_terminated'):
            self.set_status(self.get_string('status_terminated'))
        elif self.status_label.cget("text") == self.get_string('status_error'):
            self.set_status(self.get_string('status_error'))
        else:
             self.set_status(self.get_string('status_idle'))

        if hasattr(self, 'dat_label'):
            self.dat_label.configure(text=self.get_string('dat_files_label'))
        if hasattr(self, 'tbl_label'):
            self.tbl_label.configure(text=self.get_string('tbl_files_label'))
        if hasattr(self, 'lang_label'):
            self.lang_label.configure(text=self.get_string('lang_select_label'))
        if hasattr(self, 'xliff_note_label'):
            self.xliff_note_label.configure(text=self.get_string('xliff_editor_note'))

        for script_id in self.dat_button_order:
             button_key = f"button_{script_id}"
             button_text = self.get_string(button_key, default=script_id.replace("_"," ").title())
             if script_id in self.buttons:
                 self.buttons[script_id].configure(text=button_text)

        if hasattr(self, 'open_parser_button'):
             self.open_parser_button.configure(text=self.get_string('button_open_parser'))
        if hasattr(self, 'tbl_xliff_edit_button'):
             self.tbl_xliff_edit_button.configure(text=self.get_string('button_tbl_edit'))

        if hasattr(self, 'terminate_button'):
            self.terminate_button.configure(text=self.get_string('terminate_button'))

    def check_scripts_exist(self):
        """Checks if defined script files exist and logs their status."""
        all_exist = True
        if not os.path.isdir(MAIN_PATH):
             self.log_message(self.get_string('error_dir_not_found', path=MAIN_PATH))
             self.disable_all_buttons()
             return False

        found_scripts_log = []
        missing_scripts_log = []
        checked_scripts = set()
        for script_id, (script_rel_path, args_template) in self.script_definitions.items():
            if script_rel_path in checked_scripts:
                continue
            script_abs_path = os.path.join(MAIN_PATH, script_rel_path)
            script_exists = os.path.isfile(script_abs_path)
            checked_scripts.add(script_rel_path)

            if not script_exists:
                missing_scripts_log.append(self.get_string('error_script_not_found', path=script_abs_path))
                all_exist = False
            else:
                 found_scripts_log.append(self.get_string('info_found_script', script_name=script_rel_path))
                 if script_id == '3_edit':
                      xliff_path = args_template[0] if args_template else None
                      if xliff_path and not os.path.exists(xliff_path):
                           warning_msg = self.get_string('warning_arg_file_not_found', script=script_rel_path, arg_path=xliff_path)
                           #self.log_message(f"WARNING: {warning_msg}")

        for msg in missing_scripts_log:
            self.log_message(msg)
        if found_scripts_log:
             self.log_message("\n".join(found_scripts_log))
        if all_exist and found_scripts_log:
            self.log_message(self.get_string('info_scripts_found', path=MAIN_PATH))

        self.enable_all_buttons()
        return all_exist

    def log_message(self, raw_message):
        """Logs a message to the output textbox, parsing ANSI codes."""
        try:
            self.output_textbox.configure(state="normal")
            message = str(raw_message)
            last_index = 0
            current_line_tags = tuple(self.current_tags)

            for match in ANSI_COLOR_REGEX.finditer(message):
                start, end = match.span()
                if start > last_index:
                    self.output_textbox.insert("end", message[last_index:start], current_line_tags)

                codes = match.group(1).split(';')
                active_tags = set(current_line_tags)

                for code in codes:
                    tag = ANSI_CODE_TO_TAG.get(code)
                    if tag == 'reset':
                        active_tags.clear()
                    elif tag:
                        if tag.startswith("fg_"): active_tags = {t for t in active_tags if not t.startswith("fg_")}
                        if tag.startswith("bg_"): active_tags = {t for t in active_tags if not t.startswith("bg_")}
                        if tag in ['bold', 'underline'] and tag in active_tags:
                            pass
                        active_tags.add(tag)

                current_line_tags = tuple(sorted(list(active_tags)))
                last_index = end

            if last_index < len(message):
                self.output_textbox.insert("end", message[last_index:], current_line_tags)

            self.output_textbox.insert("end", "\n")
            self.current_tags = set(current_line_tags)
            if ANSI_COLOR_REGEX.search(message) and message.endswith('\x1B[0m'):
                 self.current_tags.clear()

            self.output_textbox.configure(state="disabled")
            self.output_textbox.see("end")

        except Exception as e:
             print(f"Error logging message: {e}\nMessage was: {raw_message}")
             try:
                  self.output_textbox.configure(state="normal")
                  if "text doesn't contain characters" not in str(e):
                       self.output_textbox.insert("end", str(raw_message) + "\n")
                  self.output_textbox.configure(state="disabled")
                  self.output_textbox.see("end")
             except: pass

    def set_status(self, message):
        """Updates the status label text."""
        self.status_label.configure(text=str(message))

    def disable_all_buttons(self, terminating=False):
        """Disables script-running buttons. Leaves 'Open Folder' enabled."""
        for script_id, button in self.buttons.items():
            button.configure(state="disabled")

        if self.is_running and not terminating:
             self.terminate_button.configure(state="normal")
        else:
             self.terminate_button.configure(state="disabled")

        if hasattr(self, 'open_parser_button'):
             self.open_parser_button.configure(state="normal")


    def enable_all_buttons(self):
        """Enables buttons based on script existence and running state."""
        if self.is_running:
            self.disable_all_buttons()
            return

        for script_id, button in self.buttons.items():
            # Determine the actual script definition ID to check
            # ('tbl_xliff_edit' button uses the definition of '3_edit')
            actual_script_id = '3_edit' if script_id == 'tbl_xliff_edit' else script_id
            script_def = self.script_definitions.get(actual_script_id)

            enable = False
            if script_def:
                 script_path = os.path.join(MAIN_PATH, script_def[0])
                 if os.path.isfile(script_path):
                      enable = True
                      # Special check for editor buttons (both DAT and TBL)
                      if actual_script_id == '3_edit':
                           xliff_path = script_def[1][0] if len(script_def[1]) > 0 else None
                           # Check applies only if the definition *expects* a file (DAT version)
                           if xliff_path and not os.path.exists(xliff_path) and script_id != 'tbl_xliff_edit':
                               # Warning logged previously, button stays enabled for DAT version too
                               pass

            if enable:
                button.configure(state="normal", fg_color=customtkinter.ThemeManager.theme["CTkButton"]["fg_color"])
            else:
                 button.configure(state="disabled", fg_color="gray")

        if hasattr(self, 'open_parser_button'):
            self.open_parser_button.configure(state="normal")
        if hasattr(self, 'terminate_button'):
            self.terminate_button.configure(state="disabled")


    def prompt_for_dat_path_and_run(self):
        """Prompts user for DAT folder and runs disassemble script."""
        if self.is_running:
            tkinter.messagebox.showwarning(self.get_string('warn_already_running'), self.get_string('warn_already_running_msg'))
            return

        script_id = '1_disassemble'
        script_def = self.script_definitions.get(script_id)
        script_path = os.path.join(MAIN_PATH, script_def[0]) if script_def else ''
        if not script_def or not os.path.isfile(script_path):
            self.log_message(self.get_string('error_script_not_found_run', path=script_path))
            return

        self.log_message(self.get_string('dat_folder_prompt_log'))
        button_text = self.get_string(f'button_{script_id}', default="Select Folder")
        dialog_title = self.get_string('dat_folder_prompt_title', button_text=button_text)

        folder_path = tkinter.filedialog.askdirectory(
            title=dialog_title,
            initialdir=MAIN_PATH
        )

        if folder_path:
            self.log_message(self.get_string('dat_folder_selected_log', path=folder_path))
            self.run_script_thread(script_id, extra_args=['-i', folder_path])
        else:
            self.log_message(self.get_string('dat_folder_cancel_log'))

    def prompt_compile_mode_and_run(self, script_id):
        """Prompts for compile mode and runs the compile script."""
        if self.is_running:
             tkinter.messagebox.showwarning(self.get_string('warn_already_running'), self.get_string('warn_already_running_msg'))
             return

        script_def = self.script_definitions.get(script_id)
        script_path = os.path.join(MAIN_PATH, script_def[0]) if script_def else ''
        if not script_def or not os.path.isfile(script_path):
             self.log_message(self.get_string('error_script_not_found_run', path=script_path))
             return

        dialog = customtkinter.CTkInputDialog(
            title=self.get_string('compile_mode_title'),
            text=f"{self.get_string('compile_mode_prompt')}\n\n{self.get_string('compile_mode_1')}\n{self.get_string('compile_mode_2')}"
        )
        choice = dialog.get_input()

        compile_arg = None
        if choice == "1":
            compile_arg = "--only-translated=true"
        elif choice == "2":
            compile_arg = "--only-translated=false"
        else:
            if choice is not None and choice.strip() != "":
                 tkinter.messagebox.showwarning(self.get_string('compile_mode_title'), self.get_string('compile_mode_invalid'))
            return

        self.run_script_thread(script_id, extra_args=[compile_arg])

    def open_parser_folder(self):
        """Opens the MAIN_PATH/Parser folder in the system's file explorer."""
        if not os.path.isdir(PARSER_FOLDER_PATH):
            try:
                os.makedirs(PARSER_FOLDER_PATH)
                self.log_message(f"Created missing folder: {PARSER_FOLDER_PATH}")
            except OSError as e:
                self.log_message(self.get_string('error_open_folder', path=PARSER_FOLDER_PATH, e=f"Could not create directory: {e}"))
                tkinter.messagebox.showerror(self.get_string('warning_title'), f"Could not create folder:\n{PARSER_FOLDER_PATH}\n\n{e}")
                return

        self.log_message(self.get_string('info_opening_folder', path=PARSER_FOLDER_PATH))
        try:
            if platform.system() == "Windows":
                os.startfile(PARSER_FOLDER_PATH)
            elif platform.system() == "Darwin": # macOS
                subprocess.run(['open', PARSER_FOLDER_PATH], check=True)
            else: # Linux and other Unix-like
                subprocess.run(['xdg-open', PARSER_FOLDER_PATH], check=True)
        except FileNotFoundError:
             error_msg = self.get_string('error_open_folder', path=PARSER_FOLDER_PATH, e="Required command (e.g., xdg-open) not found.")
             self.log_message(error_msg)
             tkinter.messagebox.showerror(self.get_string('error_unexpected', e=''), error_msg)
        except Exception as e:
            error_msg = self.get_string('error_open_folder', path=PARSER_FOLDER_PATH, e=e)
            self.log_message(error_msg)
            tkinter.messagebox.showerror(self.get_string('error_unexpected', e=''), error_msg)


    def run_script_thread(self, script_id, extra_args=None):
        """Starts a thread to execute a defined script."""
        if self.is_running:
            print(f"Attempted to run script '{script_id}' while another is running.")
            return

        # Determine the actual script definition ID.
        # 'tbl_xliff_edit' button uses the definition of '3_edit'.
        actual_script_id = '3_edit' if script_id == 'tbl_xliff_edit' else script_id

        script_def = self.script_definitions.get(actual_script_id)
        if not script_def:
            self.log_message(f"ERROR: Script definition not found for ID: {actual_script_id} (requested: {script_id})")
            return

        script_rel_path, base_args = script_def
        script_abs_path = os.path.join(MAIN_PATH, script_rel_path)

        if not os.path.isfile(script_abs_path):
            self.log_message(self.get_string('error_script_not_found_run', path=script_abs_path))
            return

        # Determine final arguments: Use extra_args IF PROVIDED (overrides base_args).
        # Otherwise, use base_args from definition.
        # This allows passing extra_args=[] to run '3_edit' without the file path.
        final_args = extra_args if extra_args is not None else base_args

        final_args_str = [str(arg) for arg in final_args]
        command = [PYTHON_EXECUTABLE, "-u", script_abs_path] + final_args_str

        self.is_running = True
        self.disable_all_buttons()
        self.set_status(self.get_string('status_running', script_name=script_rel_path))
        log_args_display = " ".join(f'"{arg}"' if " " in arg else arg for arg in final_args_str)
        self.log_message(self.get_string('log_running', script_name=script_rel_path, args=log_args_display))

        thread = threading.Thread(target=self.execute_script, args=(command, script_rel_path), daemon=True)
        thread.start()

    def execute_script(self, command_list, script_name_for_logging):
        """Executes the script command in a subprocess and reads output."""
        try:
            process_env = os.environ.copy()
            process_env["PYTHONIOENCODING"] = "utf-8"

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

            for line in iter(self.process.stdout.readline, ''):
                if not line: break
                self.message_queue.put({"type": "output", "data": line.rstrip('\r\n')})

            self.process.stdout.close()
            return_code = self.process.wait()

            if return_code == 0:
                status_msg = self.get_string('status_finished', script_name=script_name_for_logging)
                self.message_queue.put({"type": "status", "data": status_msg})
            else:
                 termination_codes = (1, -1, 0xC000013A, -1073741510, 0xFFFFFFFF, signal.SIGTERM * -1)
                 if (sys.platform == "win32" and return_code in termination_codes) or \
                    (sys.platform != "win32" and return_code == signal.SIGTERM * -1):
                      status_msg = self.get_string('status_terminated')
                      self.message_queue.put({"type": "status", "data": status_msg})
                      self.message_queue.put({"type": "output", "data": f"(Termination detected - Exit code: {return_code})"})
                 else:
                      error_base_msg = f"{script_name_for_logging}"
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

    def process_queue(self):
        """Processes messages from the execution thread queue."""
        try:
            while True:
                message = self.message_queue.get_nowait()
                msg_type = message.get("type")
                msg_data = message.get("data")

                if msg_type == "output":
                    self.log_message(msg_data)
                elif msg_type == "status":
                    self.set_status(msg_data)
                    if self.get_string('status_terminated') not in msg_data and \
                       self.get_string('status_idle') not in msg_data :
                        self.log_message(self.get_string('log_finished', status_message=msg_data))
                elif msg_type == "error":
                    self.set_status(self.get_string('status_error'))
                    self.log_message(self.get_string('log_error', error_message=msg_data))
                elif msg_type == "input_request":
                     self.prompt_for_input(msg_data)
                elif msg_type == "done":
                    was_running = self.is_running
                    self.is_running = False
                    current_status = self.status_label.cget("text")
                    if was_running and not (self.get_string('status_terminated') in current_status or \
                                           self.get_string('status_error') in current_status):
                         self.set_status(self.get_string('status_idle'))
                    self.enable_all_buttons()

        except queue.Empty:
            pass
        finally:
            self.after(100, self.process_queue)

    def prompt_for_input(self, prompt_message=None):
        """Prompts user for input to send to the running script's stdin (UNUSED)."""
        if not self.process or not self.process.stdin or self.process.poll() is not None:
             self.log_message(self.get_string('error_input_fail'))
             return
        if not prompt_message: prompt_message = self.get_string('input_prompt_default')
        dialog = customtkinter.CTkInputDialog(text=prompt_message, title=self.get_string('input_prompt_title'))
        user_input = dialog.get_input()
        if user_input is not None:
            self.log_message(self.get_string('log_input_sent', user_input=user_input))
            try:
                self.process.stdin.write((user_input + '\n').encode('utf-8'))
                self.process.stdin.flush()
            except Exception as e:
                self.log_message(self.get_string('error_send_input_fail', e=e))
        else:
            self.log_message(self.get_string('log_input_cancelled'))

    def terminate_process(self):
        """Attempts to terminate the running script process."""
        if self.process and self.is_running:
            pid_to_terminate = self.process.pid
            self.log_message(self.get_string('log_terminate_attempt') + f" (PID: {pid_to_terminate})")
            self.set_status(self.get_string('status_terminated'))
            self.disable_all_buttons(terminating=True)

            try:
                if sys.platform == "win32":
                    result = subprocess.run(['taskkill', '/F', '/T', '/PID', str(pid_to_terminate)],
                                            capture_output=True, text=True, check=False, creationflags=subprocess.CREATE_NO_WINDOW)
                    if result.returncode != 0 and "process with PID" in result.stderr.lower() and "not found" in result.stderr.lower():
                         self.log_message(f"Process (PID: {pid_to_terminate}) likely already finished.")
                    elif result.returncode != 0:
                         self.log_message(f"Taskkill command failed (Code: {result.returncode}): {result.stderr.strip()}")
                else:
                    os.kill(pid_to_terminate, signal.SIGTERM)
            except ProcessLookupError:
                 self.log_message(f"Process (PID: {pid_to_terminate}) already terminated.")
            except Exception as e:
                self.log_message(self.get_string('log_terminate_error', e=e))
                try: self.process.kill()
                except: pass

            self.is_running = False
            self.process = None
            self.enable_all_buttons()
            self.set_status(self.get_string('status_terminated'))


    def on_closing(self):
        """Handles the window close event."""
        if self.is_running:
            if tkinter.messagebox.askyesno(self.get_string('confirm_exit_title'), self.get_string('confirm_exit_msg')):
                self.terminate_process()
                self.after(200, self.destroy)
            else:
                return
        else:
            self.destroy()


if __name__ == "__main__":
    # --- Initial Startup Checks --- (Без изменений)
    lang = "ru"
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