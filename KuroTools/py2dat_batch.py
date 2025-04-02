import sys
import os
import subprocess
import shutil
import time
import traceback
import json # Для чтения карты строк
import uuid # Для временных файлов
import argparse # Для аргументов командной строки
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
    Fore = Style = DummyStyle()

# --- Конфигурация ---
INPUT_PY_SUBDIR = "data_to_py"
OUTPUT_DAT_SUBDIR = "py_to_data"
STRMAP_FILE = "strings_map.json" # Файл с картой переводов
TEMP_PY_PREFIX = "_temp_compile_" # Префикс для временных .py файлов
# --------------------

# Глобальный словарь для карты строк {"source": "target"}
string_translation_map = {}

def load_string_map(strmap_filepath):
    """Загружает карту строк из JSON."""
    global string_translation_map
    script_location = os.path.dirname(os.path.abspath(__file__))
    strmap_abs_path = os.path.join(script_location, strmap_filepath)

    if not os.path.exists(strmap_abs_path):
        print(f"{Fore.YELLOW}Предупреждение: Файл карты строк '{strmap_filepath}' не найден. Компиляция будет без замены строк.{Style.RESET_ALL}")
        string_translation_map = {}
        return False

    print(f"{Fore.CYAN}Загрузка карты строк из: {Style.BRIGHT}{strmap_filepath}{Style.RESET_ALL}...")
    try:
        with open(strmap_abs_path, 'r', encoding='utf-8') as f:
            string_translation_map = json.load(f)
        print(f"Загружено записей в карте строк: {len(string_translation_map)}")
        if not string_translation_map:
             print(f"{Fore.YELLOW}Предупреждение: Загруженная карта строк пуста.{Style.RESET_ALL}")
        return True
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"{Fore.RED}Ошибка при чтении JSON карты строк '{strmap_abs_path}': {e}{Style.RESET_ALL}")
        string_translation_map = {}
        return False

def inject_strings_and_create_temp(original_py_path, temp_py_path):
    """Читает оригинальный .py, заменяет PUSHSTRING и пишет во временный файл.
       Возвращает (True, кол-во_замен) или (False, 0) при ошибке."""
    global string_translation_map
    replacements_done = 0
    import ast # Импорт внутри функции, если не импортирован глобально

    try:
        with open(original_py_path, 'r', encoding='utf-8') as f_in:
            lines = f_in.readlines()

        with open(temp_py_path, 'w', encoding='utf-8') as f_out:
            for line_num, line in enumerate(lines):
                stripped_line = line.strip()
                if stripped_line.startswith("PUSHSTRING(") and stripped_line.endswith(")"):
                    try:
                        arg_content = stripped_line[len("PUSHSTRING("):-1].strip()
                        original_string = ast.literal_eval(arg_content)

                        # Убедимся, что это действительно была строка
                        if isinstance(original_string, str):
                            # Ищем перевод в карте
                            if original_string in string_translation_map:
                                translated_string = string_translation_map[original_string]
                                # Заменяем только если перевод отличается от оригинала
                                if translated_string != original_string:
                                    escaped_translated = translated_string.replace('\\', '\\\\').replace('"', '\\"')
                                    indent = line[:len(line) - len(line.lstrip())] # Сохраняем отступ
                                    new_line = f'{indent}PUSHSTRING({repr(translated_string)})\n'
                                    f_out.write(new_line)
                                    replacements_done += 1
                                else:
                                    f_out.write(line) # Записываем оригинал, если перевод совпадает
                            else:
                                f_out.write(line) # Оставляем как есть, если нет в карте
                        else:
                             # Если ast.literal_eval вернул не строку (маловероятно, но возможно)
                             f_out.write(line)

                    except (ValueError, SyntaxError) as eval_e:
                         f_out.write(line) # Оставляем как есть при ошибке разбора
                    except Exception as e:
                        # Другие неожиданные ошибки
                        print(f"    {Fore.RED}Неожиданная ошибка при обработке строки в {os.path.basename(original_py_path)}:{line_num+1}: {line.strip()} -> {e}{Style.RESET_ALL}")
                        f_out.write(line)
                else:
                    f_out.write(line) # Записываем строки без PUSHSTRING как есть

        return True, replacements_done
    except Exception as e:
        print(f"{Fore.RED}    ОШИБКА при создании временного файла {os.path.basename(temp_py_path)}: {e}{Style.RESET_ALL}")
        return False, 0
    
def compile_py_scripts(py_dir_path, dat_dir_path, only_translated):
    """
    Компилирует .py скрипты, предварительно заменяя строки.

    Args:
        py_dir_path (str): Полный путь к директории с .py файлами.
        dat_dir_path (str): Полный путь к директории для выходных .dat файлов.
        only_translated (bool): Компилировать только файлы с измененными строками.
    """
    if not os.path.isdir(py_dir_path):
        print(f"{Fore.RED}Ошибка: Директория с .py файлами '{py_dir_path}' не найдена.{Style.RESET_ALL}")
        return

    os.makedirs(dat_dir_path, exist_ok=True)
    print(f"{Fore.CYAN}Выходная директория для .dat файлов: {Style.BRIGHT}{dat_dir_path}{Style.RESET_ALL}")
    if only_translated:
        print(f"{Fore.YELLOW}Режим компиляции: Только файлы с переведенными строками.{Style.RESET_ALL}")
    else:
        print(f"{Fore.CYAN}Режим компиляции: Все .py файлы.{Style.RESET_ALL}")


    compiled_count = 0
    failed_files = []
    skipped_files = 0 # Счетчик пропущенных файлов
    total_replacements = 0
    start_time = time.time()

    print(f"\n{Fore.CYAN}Начинаю компиляцию .py файлов из: {Style.BRIGHT}{py_dir_path}{Style.RESET_ALL} (с внедрением строк)")

    python_executable = sys.executable
    if not python_executable:
        print(f"{Fore.RED}Ошибка: Не удалось определить путь к исполняемому файлу Python.{Style.RESET_ALL}")
        return
    print(f"Используемый Python: {python_executable}")

    original_cwd = os.getcwd()

    all_py_files = sorted([f for f in os.listdir(py_dir_path) if f.lower().endswith(".py") and not f.startswith(TEMP_PY_PREFIX)])
    total_files_to_process = len(all_py_files)
    print(f"Найдено .py файлов для обработки: {total_files_to_process}")

    for i, filename in enumerate(all_py_files):
        full_py_path = os.path.join(py_dir_path, filename)
        base_name = os.path.splitext(filename)[0]
        expected_dat_filename = f"{base_name}.dat"
        temp_py_filename = f"{TEMP_PY_PREFIX}{base_name}_{uuid.uuid4().hex[:6]}.py"
        temp_py_path = os.path.join(py_dir_path, temp_py_filename)
        source_dat_path = os.path.join(py_dir_path, expected_dat_filename)
        dest_dat_path = os.path.join(dat_dir_path, expected_dat_filename)

        print(f"\n--- [{i+1}/{total_files_to_process}] Обработка: {Style.BRIGHT}{filename}{Style.RESET_ALL} ---")

        # Удаляем старые .dat
        if os.path.exists(dest_dat_path):
            try: os.remove(dest_dat_path)
            except Exception as e: print(f"  Предупреждение: Не удалось удалить {dest_dat_path}: {e}")
        if os.path.exists(source_dat_path):
            try: os.remove(source_dat_path)
            except Exception as e: print(f"  Предупреждение: Не удалось удалить {source_dat_path}: {e}")

        # 1. Создаем временный файл с заменами строк
        print(f"  Создание временного файла с переводами: {temp_py_filename}...")
        success_create_temp, replacements = inject_strings_and_create_temp(full_py_path, temp_py_path)
        if not success_create_temp:
            failed_files.append(f"{filename} (ошибка создания временного файла)")
            if os.path.exists(temp_py_path): os.remove(temp_py_path) # Чистим мусор
            continue

        total_replacements += replacements
        print(f"  Выполнено замен строк: {replacements}")

        # 2. Проверяем, нужно ли компилировать этот файл
        if only_translated and replacements == 0:
            print(f"{Fore.YELLOW}  Пропуск компиляции: строки не были переведены.{Style.RESET_ALL}")
            skipped_files += 1
            # Удаляем временный .py файл
            if os.path.exists(temp_py_path):
                try: os.remove(temp_py_path)
                except Exception as e: print(f"  Предупреждение: Не удалось удалить временный файл {temp_py_filename}: {e}")
            continue # Переходим к следующему файлу

        # 3. Компилируем временный файл
        compilation_successful = False
        try:
            print(f"  Запуск компиляции: python {temp_py_filename}")
            result = subprocess.run(
                [python_executable, temp_py_path],
                capture_output=True, text=True, encoding='utf-8',
                cwd=py_dir_path,
                check=False
            )

            if result.returncode != 0:
                print(f"{Fore.RED}  ОШИБКА КОМПИЛЯЦИИ {temp_py_filename}!{Style.RESET_ALL}")
                print("--- Вывод ошибки ---")
                print(result.stderr or "Нет вывода в stderr.")
                print("--------------------")
                failed_files.append(filename)
            else:
                compilation_successful = True
                print(f"  Компиляция {temp_py_filename} завершена.")
                if os.path.exists(source_dat_path):
                    try:
                        shutil.move(source_dat_path, dest_dat_path)
                        print(f"{Fore.GREEN}  Файл {expected_dat_filename} перемещен в {OUTPUT_DAT_SUBDIR}{Style.RESET_ALL}")
                        compiled_count += 1
                    except Exception as move_e:
                        print(f"{Fore.RED}  ОШИБКА ПЕРЕМЕЩЕНИЯ {expected_dat_filename}: {move_e}{Style.RESET_ALL}")
                        failed_files.append(f"{filename} (ошибка перемещения .dat)")
                else:
                    print(f"{Fore.RED}  ОШИБКА: {expected_dat_filename} не найден в {INPUT_PY_SUBDIR} после компиляции!{Style.RESET_ALL}")
                    failed_files.append(f"{filename} (.dat не создан)")

        except FileNotFoundError:
             print(f"{Fore.RED}  ОШИБКА: Не удалось найти python или скрипт {temp_py_filename}.{Style.RESET_ALL}")
             failed_files.append(f"{filename} (ошибка запуска)")
             if not shutil.which(python_executable): break
        except Exception as e:
            print(f"{Fore.RED}  НЕПРЕДВИДЕННАЯ ОШИБКА при обработке {filename}: {e}{Style.RESET_ALL}")
            print(traceback.format_exc())
            failed_files.append(f"{filename} (неожиданная ошибка)")
        finally:
            # 4. Удаляем временный файл .py
            if os.path.exists(temp_py_path):
                try:
                    os.remove(temp_py_path)
                except Exception as remove_e:
                    print(f"{Fore.YELLOW}  Предупреждение: Не удалось удалить временный файл {temp_py_filename}: {remove_e}{Style.RESET_ALL}")

    # --- Итоги ---
    end_time = time.time()
    total_time = end_time - start_time
    print(f"\n--- {Style.BRIGHT}Компиляция завершена{Style.RESET_ALL} ---")
    print(f"Обработано .py файлов: {total_files_to_process}")
    print(f"{Fore.GREEN}Успешно скомпилировано: {compiled_count}{Style.RESET_ALL}")
    if only_translated:
        print(f"{Fore.YELLOW}Пропущено (без перевода): {skipped_files}{Style.RESET_ALL}")
    if failed_files:
        print(f"{Fore.RED}Файлов с ошибками:       {len(failed_files)}{Style.RESET_ALL}")
    else:
         print(f"{Fore.GREEN}Файлов с ошибками:       0{Style.RESET_ALL}")
    print(f"{Fore.CYAN}Всего замен строк:      {total_replacements}{Style.RESET_ALL}")
    print(f"{Fore.CYAN}Затраченное время:       {total_time:.2f} сек.{Style.RESET_ALL}")
    if failed_files:
        print(f"\n{Fore.YELLOW}Список файлов с ошибками:{Style.RESET_ALL}")
        for fname in failed_files: print(f"- {fname}")
    print("--------------------------")

def str_to_bool(value):
    """Преобразует строку в булево значение."""
    if isinstance(value, bool):
        return value
    if value.lower() in ('yes', 'true', 't', 'y', '1'):
        return True
    elif value.lower() in ('no', 'false', 'f', 'n', '0'):
        return False
    else:
        raise argparse.ArgumentTypeError('Boolean value expected.')

if __name__ == "__main__":
    # --- Добавляем парсер аргументов ---
    parser = argparse.ArgumentParser(description="Компилирует .py скрипты в .dat, опционально заменяя строки переводами.")
    parser.add_argument(
        '--only-translated',
        type=str_to_bool,
        nargs='?',
        const=True,
        default=True, # По умолчанию компилируем только измененные
        help="Компилировать только те .py файлы, в которых были найдены и заменены строки перевода (default: True)."
    )
    args = parser.parse_args()
    # --- Конец парсера аргументов ---

    script_location = os.path.dirname(os.path.abspath(__file__))
    py_directory = os.path.join(script_location, INPUT_PY_SUBDIR)
    dat_directory = os.path.join(script_location, OUTPUT_DAT_SUBDIR)

    if load_string_map(STRMAP_FILE):
        compile_py_scripts(py_directory, dat_directory, args.only_translated) # Передаем параметр
    else:
         print(f"{Fore.RED}Не удалось загрузить карту строк. Компиляция отменена.{Style.RESET_ALL}")

    # input("Нажмите Enter для выхода...") # Раскомментируйте, если нужно