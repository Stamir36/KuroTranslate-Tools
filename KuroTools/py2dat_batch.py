import sys
import os
import subprocess
import shutil
import time
import traceback
import json # Для чтения карты строк
import uuid # Для временных файлов
import argparse # Для аргументов командной строки
import ast # <-- ДОБАВИТЬ ИМПОРТ AST

# Попытка импортировать astunparse (для Python 3.9+) или astor (для < 3.9)
try:
    from ast import unparse # Python 3.9+
except ImportError:
    try:
        import astor as astor_importer # Используем псевдоним, чтобы не конфликтовать с модулем ast
        unparse = astor_importer.to_source
        print(f"{Fore.YELLOW}Примечание: Используется 'astor' для генерации кода из AST (для Python < 3.9).{Style.RESET_ALL}")
    except ImportError:
        print(f"{Fore.RED}ОШИБКА: Не найден ни ast.unparse (Python 3.9+), ни библиотека astor.{Style.RESET_ALL}")
        print(f"{Fore.RED}Пожалуйста, установите astor: pip install astor{Style.RESET_ALL}")
        sys.exit(1)


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
            data = json.load(f)
            # Убедимся, что ключи и значения - строки
            string_translation_map = {str(k): str(v) for k, v in data.items()}
        print(f"Загружено записей в карте строк: {len(string_translation_map)}")
        if not string_translation_map:
             print(f"{Fore.YELLOW}Предупреждение: Загруженная карта строк пуста.{Style.RESET_ALL}")
        return True
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"{Fore.RED}Ошибка при чтении JSON карты строк '{strmap_abs_path}': {e}{Style.RESET_ALL}")
        string_translation_map = {}
        return False
    except Exception as e:
        print(f"{Fore.RED}Неожиданная ошибка при загрузке карты строк: {e}{Style.RESET_ALL}")
        string_translation_map = {}
        return False


# --- НОВЫЙ КЛАСС ДЛЯ ЗАМЕНЫ СТРОК ЧЕРЕЗ AST ---
class StringInjector(ast.NodeTransformer):
    """
    Обходит AST и заменяет строковые константы согласно карте переводов.
    """
    def __init__(self, translation_map):
        super().__init__()
        self.translation_map = translation_map
        self.replacements_done = 0

    # Для Python 3.8+ используем visit_Constant
    def visit_Constant(self, node):
        # Проверяем, что это строковая константа
        if isinstance(node.value, str):
            original_string = node.value
            # Ищем перевод
            if original_string in self.translation_map:
                translated_string = self.translation_map[original_string]
                # Заменяем, только если перевод отличается
                if translated_string != original_string:
                    # Создаем новый узел с переведенной строкой
                    new_node = ast.Constant(value=translated_string)
                    # Копируем информацию о местоположении для unparse
                    ast.copy_location(new_node, node)
                    self.replacements_done += 1
                    return new_node # Возвращаем измененный узел
        # Если не строка или нет перевода/не отличается, возвращаем исходный узел
        return node

    # Для Python < 3.8 используем visit_Str (если нужен)
    # def visit_Str(self, node):
    #     original_string = node.s
    #     if original_string in self.translation_map:
    #         translated_string = self.translation_map[original_string]
    #         if translated_string != original_string:
    #             new_node = ast.Str(s=translated_string)
    #             ast.copy_location(new_node, node)
    #             self.replacements_done += 1
    #             return new_node
    #     return node
# --- КОНЕЦ НОВОГО КЛАССА ---

# --- НОВАЯ ФУНКЦИЯ ДЛЯ СОЗДАНИЯ ВРЕМЕННОГО ФАЙЛА ---
def inject_strings_and_create_temp_ast(original_py_path, temp_py_path):
    """
    Читает оригинальный .py, парсит AST, заменяет строки и пишет во временный файл.
    Возвращает (True, кол-во_замен) или (False, 0) при ошибке.
    """
    global string_translation_map
    try:
        with open(original_py_path, 'r', encoding='utf-8') as f_in:
            source_code = f_in.read()

        # Парсим исходный код в AST
        tree = ast.parse(source_code, filename=original_py_path)

        # Создаем и применяем трансформер
        injector = StringInjector(string_translation_map)
        modified_tree = injector.visit(tree)
        replacements = injector.replacements_done

        # Важно: исправляем отсутствующие атрибуты lineno/col_offset после трансформации
        ast.fix_missing_locations(modified_tree)

        # Генерируем модифицированный код из измененного AST
        modified_code = unparse(modified_tree) # Используем ast.unparse или astor.to_source

        # Записываем модифицированный код во временный файл
        with open(temp_py_path, 'w', encoding='utf-8') as f_out:
            f_out.write(modified_code)

        return True, replacements

    except SyntaxError as se:
        print(f"{Fore.RED}    ОШИБКА СИНТАКСИСА при парсинге {os.path.basename(original_py_path)}:{se.lineno}: {se.text.strip()} -> {se.msg}{Style.RESET_ALL}")
        return False, 0
    except Exception as e:
        print(f"{Fore.RED}    ОШИБКА при обработке AST или записи временного файла {os.path.basename(temp_py_path)}: {e}{Style.RESET_ALL}")
        traceback.print_exc() # Печатаем traceback для детальной диагностики
        return False, 0
# --- КОНЕЦ НОВОЙ ФУНКЦИИ ---


def compile_py_scripts(py_dir_path, dat_dir_path, only_translated):
    """
    Компилирует .py скрипты, предварительно заменяя строки через AST.

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

    print(f"\n{Fore.CYAN}Начинаю компиляцию .py файлов из: {Style.BRIGHT}{py_dir_path}{Style.RESET_ALL} (с внедрением строк через AST)")

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
        # Генерируем уникальное, но предсказуемое временное имя для отладки
        # temp_py_filename = f"{TEMP_PY_PREFIX}{base_name}.py"
        # Используем UUID для предотвращения конфликтов при параллельном запуске (хотя он не параллельный)
        temp_py_filename = f"{TEMP_PY_PREFIX}{base_name}_{uuid.uuid4().hex[:6]}.py"
        temp_py_path = os.path.join(py_dir_path, temp_py_filename)
        source_dat_path = os.path.join(py_dir_path, expected_dat_filename) # Где .dat создается ассемблером
        dest_dat_path = os.path.join(dat_dir_path, expected_dat_filename) # Куда его переместить

        print(f"\n--- [{i+1}/{total_files_to_process}] Обработка: {Style.BRIGHT}{filename}{Style.RESET_ALL} ---")

        # Удаляем старые .dat в обеих папках на всякий случай
        if os.path.exists(dest_dat_path):
            try: os.remove(dest_dat_path)
            except Exception as e: print(f"  Предупреждение: Не удалось удалить {dest_dat_path}: {e}")
        if os.path.exists(source_dat_path):
            try: os.remove(source_dat_path)
            except Exception as e: print(f"  Предупреждение: Не удалось удалить {source_dat_path}: {e}")

        # 1. Создаем временный файл с заменами строк (используем новую функцию)
        print(f"  Создание временного файла с переводами (AST): {temp_py_filename}...")
        # ---- ИЗМЕНЕНИЕ ЗДЕСЬ: вызываем новую функцию ----
        success_create_temp, replacements = inject_strings_and_create_temp_ast(full_py_path, temp_py_path)
        # ----------------------------------------------
        if not success_create_temp:
            failed_files.append(f"{filename} (ошибка создания временного файла/парсинга AST)")
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
            print(f"  Запуск компиляции файла: {temp_py_filename}")
            # Запускаем временный скрипт
            result = subprocess.run(
                [python_executable, temp_py_path],
                capture_output=True, text=True, encoding='utf-8', # Указываем кодировку явно
                cwd=py_dir_path, # Запускаем из папки со скриптами
                check=False # Не выбрасывать исключение при ненулевом коде возврата
            )

            if result.returncode != 0:
                print(f"{Fore.RED}  ОШИБКА КОМПИЛЯЦИИ {temp_py_filename}!{Style.RESET_ALL}")
                print("--- Stderr ---")
                print(result.stderr or "Нет вывода в stderr.")
                print("--- Stdout ---")
                print(result.stdout or "Нет вывода в stdout.")
                print("--------------")
                failed_files.append(f"{filename} (ошибка выполнения скрипта)")
            else:
                compilation_successful = True
                print(f"  Компиляция {temp_py_filename} завершена.")
                # Проверяем, появился ли .dat файл в исходной директории
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
                    # Возможно, ассемблер сохраняет его сразу в папку назначения? Проверим там.
                    if os.path.exists(dest_dat_path):
                        print(f"{Fore.YELLOW}  Примечание: {expected_dat_filename} найден в папке назначения {OUTPUT_DAT_SUBDIR}. Перемещение не требуется.{Style.RESET_ALL}")
                        compiled_count += 1 # Считаем успешным, если он там
                    else:
                        failed_files.append(f"{filename} (.dat не создан)")

        except FileNotFoundError:
             print(f"{Fore.RED}  ОШИБКА: Не удалось найти python '{python_executable}' или скрипт {temp_py_filename}.{Style.RESET_ALL}")
             failed_files.append(f"{filename} (ошибка запуска python)")
             if not shutil.which(python_executable):
                 print(f"{Fore.RED}  Исполняемый файл Python не найден в системе. Прерывание.{Style.RESET_ALL}")
                 break # Нет смысла продолжать, если python не найден
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
        unique_failed = sorted(list(set(failed_files))) # Убираем дубликаты
        for fname in unique_failed: print(f"- {fname}")
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
        nargs='?', # Делает аргумент опциональным флагом
        const=True,  # Значение, если флаг указан без значения (--only-translated)
        default=True, # По умолчанию компилируем только измененные
        help="Компилировать только те .py файлы, в которых были найдены и заменены строки перевода (yes/no, true/false, 1/0). По умолчанию: true."
    )
    args = parser.parse_args()
    # --- Конец парсера аргументов ---

    script_location = os.path.dirname(os.path.abspath(__file__))
    py_directory = os.path.join(script_location, INPUT_PY_SUBDIR)
    dat_directory = os.path.join(script_location, OUTPUT_DAT_SUBDIR)

    # Загружаем карту строк ПЕРЕД компиляцией
    if load_string_map(STRMAP_FILE):
        compile_py_scripts(py_directory, dat_directory, args.only_translated) # Передаем параметр only_translated
    else:
        print(f"{Fore.YELLOW}Карта строк не загружена или пуста. Запуск компиляции без замены строк...{Style.RESET_ALL}")
        # Даже если карта не загружена, пытаемся скомпилировать, но замены не произойдут
        # Установим only_translated в False, чтобы точно попытаться скомпилировать все
        compile_py_scripts(py_directory, dat_directory, False)


    # input("Нажмите Enter для выхода...") # Раскомментируйте, если нужно