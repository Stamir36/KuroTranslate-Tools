import os
import ast
import traceback
import uuid
import xml.etree.ElementTree as ET
import shutil
import sys
import time
import json # Для карты строк
try:
    import colorama
    colorama.init(autoreset=True)
    Fore = colorama.Fore
    Style = colorama.Style
except ImportError:
    class DummyStyle:
        def __getattr__(self, name): return ""
    Fore = Style = DummyStyle()

# --- Конфигурация ---
PY_FILES_DIR = "data_to_py"           # Папка с .py файлами
OUTPUT_XLIFF_FILE = "data_game_strings.xliff" # Имя выходного XLIFF файла
OUTPUT_STRMAP_FILE = "strings_map.json" # Файл для карты строк (пока пустой)
MIN_STRING_LENGTH = 3               # Минимальная длина строки для извлечения
REQUIRE_SPACE = True                # Требовать ли наличие пробела в строке
IGNORE_UNDERSCORE_ONLY = True       # Игнорировать строки только с '_' и буквами/цифрами
IGNORE_NUMERIC_PUNCT = True         # Игнорировать строки только из цифр/пунктуации
SOURCE_LANGUAGE = "en"              # Исходный язык
TARGET_LANGUAGE = "ru"              # Целевой язык
# --------------------

# { original_string: text_id } - для проверки уникальности и связи с ID
string_to_id_map = {}
# { text_id: {"source": original_string, "file": filename} } - для записи в XLIFF
xliff_data = {}

def is_translatable_string(s):
    """Применяет фильтры для определения переводимой строки."""
    if not isinstance(s, str) or not s:
        return False
    if len(s) < MIN_STRING_LENGTH:
        return False
    if REQUIRE_SPACE and ' ' not in s and '\n' not in s:
        # Разрешаем строки без пробелов, если они содержат не-ASCII символы (например, японский/корейский)
        if all(ord(c) < 128 for c in s):
            return False
    # Пропускаем строки типа "AniReset", "chr001", "effect_xxx" и т.д.
    # (Начинается с буквы, содержит '_', нет пробелов, есть цифры ИЛИ только буквы/цифры/'_')
    if IGNORE_UNDERSCORE_ONLY and '_' in s and ' ' not in s and '\n' not in s:
         # Проверяем, что строка не содержит символов кроме букв, цифр, '_'
         if all(c.isalnum() or c == '_' for c in s):
              # Дополнительно проверяем, начинается ли с буквы (чтобы не отсечь что-то вроде "_START_")
              if s[0].isalpha():
                   # print(f"    Пропуск (похоже на ID): '{s}'")
                   return False
    # Пропускаем строки только из цифр, пунктуации и пробелов
    if IGNORE_NUMERIC_PUNCT:
        import string as string_module
        allowed_chars = string_module.digits + string_module.punctuation + string_module.whitespace
        if all(c in allowed_chars for c in s):
             # print(f"    Пропуск (цифры/пунктуация): '{s}'")
             return False

    # Считаем строку переводимой, если она прошла все проверки
    return True

class PushStringVisitor(ast.NodeVisitor):
    """Обходит AST и извлекает строки из PUSHSTRING."""
    def __init__(self, filename):
        self.filename = filename
        self.count = 0

    def visit_Call(self, node):
        func_name = ""
        if isinstance(node.func, ast.Name):
            func_name = node.func.id

        if func_name == "PUSHSTRING":
            if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                original_string = node.args[0].value
                if is_translatable_string(original_string):
                    if original_string not in string_to_id_map:
                        text_id = f"py_{uuid.uuid4().hex[:12]}"
                        string_to_id_map[original_string] = text_id
                        xliff_data[text_id] = {"source": original_string, "file": self.filename}
                        self.count += 1
                    # else: ID уже есть для этой строки
            elif node.args and isinstance(node.args[0], ast.Str): # Совместимость с Python < 3.8
                 original_string = node.args[0].s
                 if is_translatable_string(original_string):
                    if original_string not in string_to_id_map:
                        text_id = f"py_{uuid.uuid4().hex[:12]}"
                        string_to_id_map[original_string] = text_id
                        xliff_data[text_id] = {"source": original_string, "file": self.filename}
                        self.count += 1

        # Продолжаем обход дерева, чтобы найти все вызовы PUSHSTRING
        self.generic_visit(node)

def create_xliff_and_map(xliff_filepath, strmap_filepath):
    """Создает XLIFF и пустой JSON для карты строк."""
    global xliff_data
    if not xliff_data:
        print(f"{Fore.YELLOW}Не найдено строк для перевода, файлы не созданы.{Style.RESET_ALL}")
        return False, 0

    xliff_root = ET.Element("xliff", version="1.2", xmlns="urn:oasis:names:tc:xliff:document:1.2")
    file_element = ET.SubElement(xliff_root, "file",
                                 original="combined_python_scripts",
                                 datatype="plaintext", # Используем plaintext, т.к. строки из разных файлов
                                 source_language=SOURCE_LANGUAGE,
                                 target_language=TARGET_LANGUAGE)
    body_element = ET.SubElement(file_element, "body")

    sorted_ids = sorted(xliff_data.keys())
    string_map_data = {} # Для JSON

    for text_id in sorted_ids:
        data = xliff_data[text_id]
        original_string = data["source"]
        filename = data["file"]

        trans_unit = ET.SubElement(body_element, "trans-unit", id=text_id)
        # Добавляем имя файла как примечание (note)
        ET.SubElement(trans_unit, "note").text = f"File: {filename}"
        source = ET.SubElement(trans_unit, "source")
        source.text = original_string.replace("\n", "\\n")
        target = ET.SubElement(trans_unit, "target")
        # target.text = "" # Пустой таргет

        # Добавляем в карту строк для JSON (ключ - оригинал, значение - пока тоже оригинал)
        string_map_data[original_string] = original_string

    # Запись XLIFF
    try:
        xliff_tree = ET.ElementTree(xliff_root)
        import xml.dom.minidom
        xml_str = ET.tostring(xliff_root, encoding='utf-8')
        dom = xml.dom.minidom.parseString(xml_str)
        pretty_xml_as_string = dom.toprettyxml(indent="  ", encoding='utf-8')
        with open(xliff_filepath, "wb") as f: f.write(pretty_xml_as_string)
        print(f"{Fore.GREEN}XLIFF файл успешно создан: {xliff_filepath}{Style.RESET_ALL}")
    except Exception as e:
        print(f"{Fore.RED}Ошибка при записи XLIFF файла '{xliff_filepath}': {e}{Style.RESET_ALL}")
        return False, len(xliff_data)

    # Запись JSON карты строк (с исходным текстом в качестве значения по умолчанию)
    try:
        with open(strmap_filepath, 'w', encoding='utf-8') as f:
            json.dump(string_map_data, f, indent=4, ensure_ascii=False, sort_keys=True)
        print(f"{Fore.GREEN}JSON карта строк создана: {strmap_filepath}{Style.RESET_ALL}")
    except IOError as e:
        print(f"{Fore.RED}Ошибка при записи JSON карты строк '{strmap_filepath}': {e}{Style.RESET_ALL}")
        return False, len(xliff_data)

    return True, len(xliff_data)

def process_py_files(py_dir):
    """Основная функция обработки."""
    script_location = os.path.dirname(os.path.abspath(__file__))
    py_dir_path = os.path.join(script_location, py_dir)

    if not os.path.isdir(py_dir_path):
        print(f"{Fore.RED}Ошибка: Директория '{py_dir_path}' не найдена.{Style.RESET_ALL}")
        return

    processed_files = 0
    total_strings_found_in_files = 0
    start_time = time.time()

    print(f"{Fore.CYAN}Поиск строк для перевода в файлах *.py в '{py_dir_path}'...{Style.RESET_ALL}")

    all_py_files = sorted([f for f in os.listdir(py_dir_path) if f.lower().endswith(".py")])
    total_files_to_process = len(all_py_files)

    for i, filename in enumerate(all_py_files):
        filepath = os.path.join(py_dir_path, filename)
        print(f"--- [{i+1}/{total_files_to_process}] Обработка файла: {Style.BRIGHT}{filename}{Style.RESET_ALL} ---")
        try:
            with open(filepath, 'r', encoding='utf-8') as f_read:
                source_code = f_read.read()

            tree = ast.parse(source_code, filename=filename)
            visitor = PushStringVisitor(filename)
            visitor.visit(tree)
            if visitor.count > 0:
                 print(f"  Найдено новых уникальных строк: {visitor.count}")
            processed_files += 1
            total_strings_found_in_files += visitor.count

        except SyntaxError as e:
            print(f"    {Fore.RED}СИНТАКСИЧЕСКАЯ ОШИБКА в файле {filename}: {e}. Файл пропущен.{Style.RESET_ALL}")
        except Exception as e:
            print(f"    {Fore.RED}Неожиданная ошибка при обработке файла {filename}: {e}{Style.RESET_ALL}")
            print(traceback.format_exc())

    end_time = time.time()
    total_time = end_time - start_time

    print(f"\n--- {Style.BRIGHT}Обработка файлов завершена{Style.RESET_ALL} ---")
    print(f"Обработано файлов: {processed_files} / {total_files_to_process}")
    print(f"Найдено уникальных строк для перевода (всего): {len(xliff_data)}")
    print(f"Затраченное время: {total_time:.2f} сек.")

    # Создаем XLIFF и JSON карту
    output_xliff_path = os.path.join(script_location, OUTPUT_XLIFF_FILE)
    output_strmap_path = os.path.join(script_location, OUTPUT_STRMAP_FILE)
    create_xliff_and_map(output_xliff_path, output_strmap_path)

if __name__ == "__main__":
    # --- Резервное копирование НЕ ТРЕБУЕТСЯ, т.к. файлы не изменяются ---
    process_py_files(PY_FILES_DIR)
    print("\nГотово.")