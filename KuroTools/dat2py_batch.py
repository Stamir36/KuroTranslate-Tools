# --- START OF FILE dat2py_batch.py ---

import sys
import os
import traceback
import disasm.ED9Disassembler as ED9Disassembler
import disasm.ED9InstructionsSet as ED9InstructionsSet # Импортируем для сброса состояния
import shutil # Для копирования файлов
import time # Для статистики времени
import argparse

# --- УБРАН импорт tqdm ---

try:
    import colorama
    colorama.init(autoreset=True)
    Fore = colorama.Fore
    Style = colorama.Style
except ImportError:
    print("Предупреждение: Библиотека colorama не найдена (pip install colorama). Цветной вывод будет отключен.")
    class DummyStyle:
        def __getattr__(self, name): return ""
    Fore = DummyStyle(); Style = DummyStyle()

# --- Конфигурация ---
INPUT_DAT_DIR = None
OUTPUT_PY_SUBDIR = "data_to_py"
LOG_FILE = "LogDisassembler.txt"
DECOMPILE_MODE = True
SHOW_MARKERS = False
# --------------------

# --- Код для добавления sys.path ---
PYTHON_PATH_PREPEND_CODE = """\
# ... (код sys.path) ...
"""
# --- Конец кода ---

# --- УБРАНА функция safe_print ---

def prepend_code_to_file(filepath, code_to_prepend): # Убран use_tqdm_flag
    """Добавляет строку кода в начало файла."""
    try:
        abs_filepath = os.path.abspath(filepath)
        if not os.path.exists(abs_filepath):
            return # Молча выходим, если файла нет
        with open(abs_filepath, 'r', encoding='utf-8') as f_read:
            original_content = f_read.read()
        with open(abs_filepath, 'w', encoding='utf-8') as f_write:
            f_write.write(code_to_prepend)
            f_write.write(original_content)
    except Exception as e:
         # Используем обычный print
        print(f"\n{Fore.YELLOW}Предупреждение: Ошибка при добавлении кода sys.path в файл {os.path.basename(filepath)}: {e}{Style.RESET_ALL}")


def process_directory(input_dir_path, current_decompile_mode):
    """Обрабатывает все .dat файлы в указанной директории."""
    # global tqdm_available - больше не нужен

    if not os.path.isdir(input_dir_path):
        print(f"{Fore.RED}Ошибка: Указанный путь '{input_dir_path}' не является директорией или не существует.{Style.RESET_ALL}")
        return False

    script_dir = os.path.dirname(os.path.abspath(__file__))
    output_py_dir_path = os.path.join(script_dir, OUTPUT_PY_SUBDIR)
    log_file_path = os.path.join(script_dir, LOG_FILE)

    os.makedirs(output_py_dir_path, exist_ok=True)
    print(f"{Fore.CYAN}Выходная директория для .py файлов: {Style.BRIGHT}{output_py_dir_path}{Style.RESET_ALL}")

    failed_files_list = []
    log_entries = []
    success_count = 0
    original_cwd = os.getcwd()
    start_time = time.time()

    mode_str = "ДИЗАССЕМБЛИРОВАНИЕ (Режим компиляции)" if current_decompile_mode else "ДИЗАССЕМБЛИРОВАНИЕ (Режим извлечения строк)"

    dat_files = sorted([f for f in os.listdir(input_dir_path) if f.lower().endswith(".dat")])
    total_files = len(dat_files)
    print(f"{Fore.CYAN}Всего найдено .dat файлов: {total_files}{Style.RESET_ALL}")

    if total_files == 0:
         print(f"{Fore.YELLOW}В папке '{input_dir_path}' не найдено .dat файлов для обработки.{Style.RESET_ALL}")
         # ... (логика записи пустого лога) ...
         return True

    # --- ИЗМЕНЕНИЕ: Просто выводим сообщение о начале ---
    print(f"\n{Fore.CYAN}Начинаю обработку .dat файлов в: {Style.BRIGHT}{input_dir_path}{Style.RESET_ALL} (Режим: {mode_str})")
    # --- КОНЕЦ ИЗМЕНЕНИЯ ---

    current_file_output_path = None
    try:
        print(f"{Fore.CYAN}Переход в рабочую директорию: {output_py_dir_path}{Style.RESET_ALL}")
        os.chdir(output_py_dir_path)

        # --- ИЗМЕНЕНИЕ: Цикл всегда с enumerate ---
        for i, filename in enumerate(dat_files):

            # Определяем пути
            full_dat_path_abs = os.path.abspath(os.path.join(original_cwd, input_dir_path, filename))
            base_name = os.path.splitext(filename)[0]
            output_py_filename = f"{base_name}.py"
            current_file_output_path = output_py_filename
            output_py_path_abs = os.path.abspath(output_py_filename)

            # --- ИЗМЕНЕНИЕ: Условный вывод прогресса ---
            if not current_decompile_mode: # Режим извлечения строк
                percent_complete = int(((i + 1) / total_files) * 100)
                # Выводим в одну строку с перезаписью (\r)
                print(f"\r[{Style.BRIGHT}Обработка {filename} для извлечения строк{Style.RESET_ALL}] | Прогресс: {percent_complete}% ({i+1}/{total_files})", end="")
            else: # Режим компиляции (детальный вывод)
                print(f"\n--- [{i+1}/{total_files}] Обработка файла: {Style.BRIGHT}{filename}{Style.RESET_ALL} ---")
            # --- КОНЕЦ ИЗМЕНЕНИЯ ---

            # Сброс состояния
            ED9InstructionsSet.locations_dict = {}
            ED9InstructionsSet.location_counter = 0
            ED9InstructionsSet.smallest_data_ptr = sys.maxsize

            disasm = ED9Disassembler.ED9Disassembler(markers=SHOW_MARKERS, decomp=current_decompile_mode)
            parse_successful = False
            error_details = None

            try:
                disasm.parse(full_dat_path_abs)
                parse_successful = True

                if os.path.exists(current_file_output_path):
                    if current_decompile_mode: # Только в режиме компиляции
                        print(f"{Fore.GREEN}  Успешно дизассемблировано: {filename} -> {output_py_filename}{Style.RESET_ALL}")
                    # Вызываем prepend БЕЗ флага use_tqdm
                    prepend_code_to_file(output_py_path_abs, PYTHON_PATH_PREPEND_CODE)
                    success_count += 1
                else:
                    parse_successful = False
                    # --- ИЗМЕНЕНИЕ: Вывод ошибки с новой строки, если был режим извлечения ---
                    error_prefix = "\n" if not current_decompile_mode else ""
                    print(f"{error_prefix}{Fore.RED}Ошибка [{filename}]: Дизассемблирование OK, но выходной файл {output_py_filename} не найден в {os.getcwd()}.{Style.RESET_ALL}")
                    # --- КОНЕЦ ИЗМЕНЕНИЯ ---
                    failed_files_list.append(filename)
                    error_details = f"{filename}: Output file missing in CWD after parse() succeeded.\n"
                    log_entries.append(error_details.strip())

            # Обработка исключений
            except KeyError as e:
                parse_successful = False
                error_key = e.args[0] if e.args else 'Unknown Key'
                error_prefix = "\n" if not current_decompile_mode else ""
                print(f"{error_prefix}{Fore.RED}Ошибка KeyError в [{filename}]: {e} (Ключ: {error_key}){Style.RESET_ALL}")
                failed_files_list.append(filename)
                # ... (логирование traceback) ...
                error_details = f"{filename}: KeyError {e}\n"
                error_details += "--- Traceback для ошибки ---\n"
                error_details += traceback.format_exc()
                error_details += "---------------------------\n"
                log_entries.append(error_details.strip())


            except Exception as e:
                parse_successful = False
                error_prefix = "\n" if not current_decompile_mode else ""
                print(f"{error_prefix}{Fore.RED}Не удалось дизассемблировать [{filename}]. Ошибка: {e}{Style.RESET_ALL}")
                failed_files_list.append(filename)
                # ... (логирование traceback) ...
                error_details = f"{filename}: {type(e).__name__} - {e}\n"
                error_details += "--- Traceback для ошибки ---\n"
                error_details += traceback.format_exc()
                error_details += "---------------------------\n"
                log_entries.append(error_details.strip())


            finally:
                 if not parse_successful and current_file_output_path and os.path.exists(current_file_output_path):
                    try:
                        os.remove(current_file_output_path)
                        if current_decompile_mode: # Только в режиме компиляции
                            print(f"  Удален частично созданный или некорректный .py файл: {output_py_filename}")
                    except Exception as remove_e:
                        error_prefix = "\n" if not current_decompile_mode else ""
                        print(f"{error_prefix}{Fore.YELLOW}Предупреждение [{filename}]: Не удалось удалить {output_py_filename}: {remove_e}{Style.RESET_ALL}")
                 current_file_output_path = None
        # --- КОНЕЦ ЦИКЛА ---

        # --- ИЗМЕНЕНИЕ: Добавляем перевод строки после цикла, если был режим извлечения ---
        if not current_decompile_mode:
            print() # Перевод строки для чистоты вывода
        # --- КОНЕЦ ИЗМЕНЕНИЯ ---

    finally:
        print(f"{Fore.CYAN}Возврат в рабочую директорию: {original_cwd}{Style.RESET_ALL}")
        os.chdir(original_cwd)

    # --- Запись лога и Итоги ---
    # ... (без изменений) ...
    try:
        # ... (запись лога) ...
        with open(log_file_path, 'w', encoding='utf-8') as f:
            f.write(f"Лог дизассемблирования (Режим: {'Компиляция' if current_decompile_mode else 'Извлечение строк'})\n")
            f.write(f"Входная директория: {os.path.abspath(input_dir_path)}\n")
            f.write(f"Выходная директория: {os.path.abspath(output_py_dir_path)}\n")
            f.write("="*40 + "\n\n")
            f.write("Файлы, которые не удалось дизассемблировать:\n")
            if failed_files_list:
                unique_failed = sorted(list(set(failed_files_list)))
                for fname in unique_failed: f.write(f"- {fname}\n")
            else: f.write("(Ошибок дизассемблирования не было)\n")
            f.write("\nДетали ошибок:\n")
            if log_entries:
                for log_entry in log_entries:
                    f.write(f"\n===================================\n")
                    f.write(f"{log_entry}\n")
                    f.write(f"===================================\n")
            else: f.write("(Конкретные ошибки не записаны)\n")
        print(f"\n{Fore.CYAN}Лог дизассемблирования сохранен в: {Style.BRIGHT}{log_file_path}{Style.RESET_ALL}")
    except Exception as e:
        print(f"\n{Fore.RED}Не удалось записать лог в {log_file_path}: {e}{Style.RESET_ALL}")

    end_time = time.time()
    total_time = end_time - start_time
    print(f"\n--- {Style.BRIGHT}Дизассемблирование завершено{Style.RESET_ALL} ---")
    print(f"{Fore.GREEN}Успешно обработано: {success_count} / {total_files} файлов{Style.RESET_ALL}")
    failed_count = len(set(failed_files_list))
    if failed_count > 0: print(f"{Fore.RED}Файлов с ошибками:  {failed_count}{Style.RESET_ALL}")
    else: print(f"{Fore.GREEN}Файлов с ошибками:  0{Style.RESET_ALL}")
    print(f"{Fore.CYAN}Затраченное время:   {total_time:.2f} сек.{Style.RESET_ALL}")
    if failed_files_list: print(f"{Fore.YELLOW}Подробности ошибок см. в файле: {LOG_FILE}{Style.RESET_ALL}")
    print("------------------------------------")
    return failed_count == 0


if __name__ == "__main__":
    # --- УБРАНО предупреждение о tqdm ---

    parser = argparse.ArgumentParser(description="Дизассемблирует .dat файлы из указанной папки в .py файлы.")
    # ... (аргументы без изменений) ...
    parser.add_argument("-i", "--input", dest="input_dir", required=True,
                        help="Путь к папке, содержащей .dat файлы.")
    parser.add_argument("--decompile-mode", dest="decompile_mode_arg", type=str, choices=['true', 'false'], default=None,
                        help="Установить режим DECOMPILE_MODE ('true' для компиляции, 'false' для извлечения строк). По умолчанию используется значение из скрипта (True).")


    args = parser.parse_args()

    current_decompile_mode = DECOMPILE_MODE
    # ... (определение режима без изменений) ...
    if args.decompile_mode_arg is not None:
        current_decompile_mode = args.decompile_mode_arg.lower() == 'true'
        print(f"{Fore.CYAN}Режим DECOMPILE_MODE установлен из аргумента командной строки: {current_decompile_mode}{Style.RESET_ALL}")
    else:
         print(f"{Fore.CYAN}Режим DECOMPILE_MODE используется по умолчанию: {current_decompile_mode}{Style.RESET_ALL}")


    input_directory = args.input_dir
    # ... (проверка input_directory без изменений) ...
    if not os.path.isdir(input_directory):
        print(f"{Fore.RED}Ошибка: Путь из аргумента '-i' '{input_directory}' не найден или не является папкой.{Style.RESET_ALL}")
        sys.exit(1)


    success = process_directory(input_directory, current_decompile_mode)
    sys.exit(0 if success else 1)

# --- END OF FILE dat2py_batch.py ---