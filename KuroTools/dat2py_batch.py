import sys
import os
import traceback
import disasm.ED9Disassembler as ED9Disassembler
import disasm.ED9InstructionsSet as ED9InstructionsSet # Импортируем для сброса состояния
import shutil # Для копирования файлов
from processcle import processCLE # Убедитесь, что этот импорт есть
import time # Для статистики времени
import argparse

try:
    import colorama
    colorama.init(autoreset=True) # Инициализация colorama с автосбросом цвета
    Fore = colorama.Fore
    Style = colorama.Style
except ImportError:
    print("Предупреждение: Библиотека colorama не найдена (pip install colorama). Цветной вывод будет отключен.")
    # Создаем заглушки, чтобы код не падал
    class DummyStyle:
        def __getattr__(self, name):
            return ""
    Fore = DummyStyle()
    Style = DummyStyle()


# --- Конфигурация ---
INPUT_DAT_DIR = None # Будет запрошен у пользователя
OUTPUT_PY_SUBDIR = "data_to_py" # Имя подпапки для .py файлов
LOG_FILE = "LogDisassembler.txt" # Имя файла для логов
DECOMPILE_MODE = False      # Режим дизассемблирования
SHOW_MARKERS = False      # Показывать ли маркеры строк (0x26)
# --------------------

# --- Код для добавления sys.path ---
PYTHON_PATH_PREPEND_CODE = """\
import sys
import os
script_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(script_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

# --- Original file content starts below ---
"""
# --- Конец кода ---

def prepend_code_to_file(filepath, code_to_prepend):
    """Добавляет строку кода в начало файла."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f_read:
            original_content = f_read.read()

        with open(filepath, 'w', encoding='utf-8') as f_write:
            f_write.write(code_to_prepend)
            f_write.write(original_content)
    except Exception as e:
        print(f"{Fore.YELLOW}  Предупреждение: Ошибка при добавлении кода sys.path в файл {os.path.basename(filepath)}: {e}{Style.RESET_ALL}")

def process_directory(input_dir_path):
    """Обрабатывает все .dat файлы в указанной директории."""
    if not os.path.isdir(input_dir_path):
        print(f"{Fore.RED}Ошибка: Указанный путь '{input_dir_path}' не является директорией или не существует.{Style.RESET_ALL}")
        return

    script_dir = os.path.dirname(os.path.abspath(__file__))
    output_py_dir_path = os.path.join(script_dir, OUTPUT_PY_SUBDIR)
    log_file_path = os.path.join(script_dir, LOG_FILE)

    os.makedirs(output_py_dir_path, exist_ok=True)
    print(f"{Fore.CYAN}Выходная директория для .py файлов: {Style.BRIGHT}{output_py_dir_path}{Style.RESET_ALL}")

    failed_files_list = []
    log_entries = []
    success_count = 0 # Счетчик успешных операций
    original_cwd = os.getcwd()
    start_time = time.time() # Засекаем время начала

    print(f"\n{Fore.CYAN}Начинаю обработку .dat файлов в: {Style.BRIGHT}{input_dir_path}{Style.RESET_ALL} (Режим: ДИЗАССЕМБЛИРОВАНИЕ)")

    # Получаем список файлов для подсчета общего количества
    dat_files = [f for f in os.listdir(input_dir_path) if f.lower().endswith(".dat")]
    total_files = len(dat_files)
    print(f"{Fore.CYAN}Всего найдено .dat файлов: {total_files}{Style.RESET_ALL}")

    for i, filename in enumerate(sorted(dat_files)): # Используем отсортированный список
        full_dat_path = os.path.join(input_dir_path, filename)
        base_name = os.path.splitext(filename)[0]
        output_py_filename = f"{base_name}.py"
        output_py_path = os.path.join(output_py_dir_path, output_py_filename)

        print(f"\n--- [{i+1}/{total_files}] Обработка файла: {Style.BRIGHT}{filename}{Style.RESET_ALL} ---")

        ED9InstructionsSet.locations_dict = {}
        ED9InstructionsSet.location_counter = 0
        ED9InstructionsSet.smallest_data_ptr = sys.maxsize

        disasm = None
        disasm = ED9Disassembler.ED9Disassembler(markers=SHOW_MARKERS, decomp=DECOMPILE_MODE)
        parse_successful = False
        error_details = None

        try:
            os.chdir(output_py_dir_path)
            disasm.parse(full_dat_path)
            parse_successful = True
            print(f"{Fore.GREEN}  Успешно дизассемблировано: {filename} -> {output_py_filename}{Style.RESET_ALL}")
            prepend_code_to_file(output_py_path, PYTHON_PATH_PREPEND_CODE)
            success_count += 1 # Увеличиваем счетчик успеха

        except KeyError as e:
            error_key = e.args[0]
            print(f"{Fore.RED}  Ошибка KeyError: {e}{Style.RESET_ALL}")
            failed_files_list.append(filename)
            error_details = f"{filename}: KeyError {e}\n"
            log_entries.append(error_details.strip())

        except Exception as e:
            print(f"{Fore.RED}  Не удалось дизассемблировать {filename}. Ошибка: {e}{Style.RESET_ALL}")
            failed_files_list.append(filename)
            error_details = f"{filename}: {type(e).__name__} - {e}\n"
            error_details += "--- Traceback для ошибки ---\n"
            error_details += traceback.format_exc()
            error_details += "---------------------------\n"
            log_entries.append(error_details.strip())

        finally:
            os.chdir(original_cwd)
            if not parse_successful and os.path.exists(output_py_path):
                try:
                    os.remove(output_py_path)
                    print(f"  Удален частично созданный .py файл: {output_py_filename}")
                except Exception as remove_e:
                    print(f"{Fore.YELLOW}  Предупреждение: Не удалось удалить {output_py_filename}: {remove_e}{Style.RESET_ALL}")


    # Записываем лог ошибок
    try:
        with open(log_file_path, 'w', encoding='utf-8') as f:
            f.write("Files not disassembled:\n")
            if failed_files_list:
                unique_failed = sorted(list(set(failed_files_list)))
                for fname in unique_failed:
                    f.write(f"- {fname}\n")
            else:
                f.write("(No files failed disassembly)\n")

            f.write("\nError Log Details:\n")
            if log_entries:
                for log_entry in log_entries:
                    f.write(f"\n===================================\n")
                    f.write(f"{log_entry}\n")
                    f.write(f"===================================\n")
            else:
                f.write("(No specific error logs recorded)\n")
        print(f"\n{Fore.CYAN}Лог дизассемблирования сохранен в: {Style.BRIGHT}{log_file_path}{Style.RESET_ALL}")
    except Exception as e:
        print(f"\n{Fore.RED}Не удалось записать лог в {log_file_path}: {e}{Style.RESET_ALL}")

    # --- Итоги ---
    end_time = time.time()
    total_time = end_time - start_time
    print(f"\n--- {Style.BRIGHT}Дизассемблирование завершено{Style.RESET_ALL} ---")
    print(f"{Fore.GREEN}Успешно обработано: {success_count} / {total_files} файлов{Style.RESET_ALL}")
    if failed_files_list:
        print(f"{Fore.RED}Файлов с ошибками:  {len(set(failed_files_list))}{Style.RESET_ALL}")
    else:
        print(f"{Fore.GREEN}Файлов с ошибками:  0{Style.RESET_ALL}")
    print(f"{Fore.CYAN}Затраченное время:   {total_time:.2f} сек.{Style.RESET_ALL}")
    if failed_files_list:
        print(f"{Fore.YELLOW}Подробности ошибок см. в файле: {LOG_FILE}{Style.RESET_ALL}")
    print("------------------------------------")


if __name__ == "__main__":
    # Настройка парсера аргументов
    parser = argparse.ArgumentParser(description="Дизассемблирует .dat файлы из указанной папки в .py файлы.")
    parser.add_argument("-i", "--input", dest="input_dir", 
                        help="Путь к папке, содержащей .dat файлы (опционально).")
    # parser.add_argument("--decomp", action="store_true", help="Включить режим декомпиляции.")

    args = parser.parse_args()

    INPUT_DAT_DIR = None # Инициализируем переменную

    if args.input_dir:
        INPUT_DAT_DIR = args.input_dir
    else:
        while True:
            try:
                folder_path = input(f"{Fore.YELLOW}Введите путь к папке с .dat файлами: {Style.RESET_ALL}")
                # Проверяем путь сразу после ввода
                if os.path.isdir(folder_path):
                    INPUT_DAT_DIR = folder_path
                    break # Выход из цикла если путь корректен
                else:
                     # Используем colorama для вывода ошибки
                    print(f"{Fore.RED}Путь '{folder_path}' не найден или не является папкой. Попробуйте снова.{Style.RESET_ALL}")
            except EOFError: # Обработка Ctrl+D/Ctrl+Z
                 print("\nВвод прерван.")
                 sys.exit(0)
            except KeyboardInterrupt: # Обработка Ctrl+C
                 print("\nОперация прервана пользователем.")
                 sys.exit(0)

    # Финальная проверка пути (на всякий случай, если логика выше даст сбой)
    if not INPUT_DAT_DIR or not os.path.isdir(INPUT_DAT_DIR):
        print(f"{Fore.RED}Ошибка: Не удалось получить корректный путь к папке с .dat файлами.{Style.RESET_ALL}", file=sys.stderr)
        sys.exit(1)

    # Запуск основной функции обработки
    process_directory(INPUT_DAT_DIR)