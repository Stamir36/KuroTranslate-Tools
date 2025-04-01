import os
import xml.etree.ElementTree as ET
import json
import sys
try:
    import colorama
    colorama.init(autoreset=True)
    Fore = colorama.Fore
    Style = colorama.Style
except ImportError:
    print("Предупреждение: Библиотека colorama не найдена (pip install colorama). Цветной вывод будет отключен.")
    class DummyStyle:
        def __getattr__(self, name): return ""
    Fore = Style = DummyStyle()

# --- Конфигурация ---
INPUT_XLIFF_FILE = "data_game_strings.xliff" # Входной XLIFF с переводами
OUTPUT_STRMAP_FILE = "strings_map.json"    # Выходной JSON для компилятора
SOURCE_LANGUAGE = "en" # На случай, если target пуст
# --------------------

def create_string_map_from_xliff(xliff_filepath, strmap_filepath):
    """Читает XLIFF и создает JSON карту {"source": "target" (или "source")}."""
    translation_map_for_json = {}

    print(f"{Fore.CYAN}Чтение XLIFF файла: {Style.BRIGHT}{xliff_filepath}{Style.RESET_ALL}...")
    try:
        tree = ET.parse(xliff_filepath)
        root = tree.getroot()
    except (FileNotFoundError, ET.ParseError) as e:
        print(f"{Fore.RED}Ошибка при чтении XLIFF файла: {e}{Style.RESET_ALL}")
        return False

    namespaces = {'xliff': 'urn:oasis:names:tc:xliff:document:1.2'}
    loaded_count = 0
    skipped_no_target = 0

    for trans_unit in root.findall(".//xliff:trans-unit", namespaces):
        id_attr = trans_unit.get("id")
        source_element = trans_unit.find("xliff:source", namespaces)
        target_element = trans_unit.find("xliff:target", namespaces)

        if source_element is None or source_element.text is None:
            print(f"{Fore.YELLOW}Предупреждение: Пропущен trans-unit с ID '{id_attr}', т.к. отсутствует <source>.{Style.RESET_ALL}")
            continue

        # Получаем исходный текст, заменяя \\n на \n
        source_text = source_element.text.replace("\\n", "\n")

        # Получаем текст перевода, если он есть, иначе используем исходный
        target_text = None
        if target_element is not None and target_element.text:
             target_text = target_element.text.replace("\\n", "\n")
        else:
             skipped_no_target +=1

        text_to_use = target_text if target_text else source_text

        # Добавляем в словарь для JSON
        translation_map_for_json[source_text] = text_to_use
        loaded_count += 1

    print(f"Загружено строк из XLIFF: {loaded_count}")
    if skipped_no_target > 0:
        print(f"{Fore.YELLOW}Строк без перевода (использован <source>): {skipped_no_target}{Style.RESET_ALL}")

    # Запись JSON карты строк
    print(f"{Fore.CYAN}Запись JSON карты строк в: {Style.BRIGHT}{strmap_filepath}{Style.RESET_ALL}...")
    try:
        with open(strmap_filepath, 'w', encoding='utf-8') as f:
            json.dump(translation_map_for_json, f, indent=4, ensure_ascii=False, sort_keys=True)
        print(f"{Fore.GREEN}JSON карта строк успешно создана.{Style.RESET_ALL}")
        return True
    except IOError as e:
        print(f"{Fore.RED}Ошибка при записи JSON карты строк '{strmap_filepath}': {e}{Style.RESET_ALL}")
        return False

if __name__ == "__main__":
    script_loc = os.path.dirname(os.path.abspath(__file__))
    xliff_abs_path = os.path.join(script_loc, INPUT_XLIFF_FILE)
    strmap_abs_path = os.path.join(script_loc, OUTPUT_STRMAP_FILE)

    if not os.path.exists(xliff_abs_path):
        print(f"{Fore.RED}Ошибка: XLIFF файл '{INPUT_XLIFF_FILE}' не найден.{Style.RESET_ALL}")
        sys.exit(1)

    if create_string_map_from_xliff(xliff_abs_path, strmap_abs_path):
        print("\nГотово.")
    else:
        print("\nЗавершено с ошибками.")