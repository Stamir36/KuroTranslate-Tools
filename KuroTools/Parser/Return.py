import json
import xml.etree.ElementTree as ET

def replace_ids_with_translations(json_filepath, xliff_filepath):
    """
    Заменяет идентификаторы в JSON на текст из XLIFF.

    Args:
        json_filepath: Путь к JSON файлу.
        xliff_filepath: Путь к XLIFF файлу.

    Returns:
        True, если успешно, False в противном случае.
    """
    try:
        # Загрузка JSON файла
        with open(json_filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"Ошибка при чтении JSON файла: {e}")
        return False

    try:
        # Загрузка XLIFF файла
        tree = ET.parse(xliff_filepath)
        root = tree.getroot()
    except (FileNotFoundError, ET.ParseError) as e:
        print(f"Ошибка при чтении XLIFF файла: {e}")
        return False

    # Определяем namespace
    namespaces = {'xliff': 'urn:oasis:names:tc:xliff:document:1.2'}

    # Создаем словарь соответствия ID и переведенного текста
    translation_map = {}
    for trans_unit in root.findall(".//xliff:trans-unit", namespaces):
        id = trans_unit.get("id")
        source_element = trans_unit.find("xliff:source", namespaces)
        target_element = trans_unit.find("xliff:target", namespaces)

        # Если target пустой, берем текст из source
        if target_element is not None and target_element.text:
            # Заменяем \\n на \n для корректного переноса строк
            translation_map[id] = target_element.text.replace("\\n", "\n")
        elif source_element is not None and source_element.text:
            # Заменяем \\n на \n для корректного переноса строк
            translation_map[id] = source_element.text.replace("\\n", "\n")

    def recursive_replace(obj):
        """Рекурсивно заменяет ID на переводы."""
        if isinstance(obj, dict):
            for key, value in obj.items():
                if isinstance(value, str) and value in translation_map:
                    obj[key] = translation_map[value]
                elif isinstance(value, (dict, list)):
                    recursive_replace(value)
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                if isinstance(item, str) and item in translation_map:
                    obj[i] = translation_map[item]
                elif isinstance(item, (dict, list)):
                    recursive_replace(item)

    # Заменяем ID на текст
    recursive_replace(data)

    # Записываем измененный JSON
    try:
        with open(json_filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
    except IOError as e:
        print(f"Ошибка при записи измененного JSON: {e}")
        return False

    print("Замена ID на переводы завершена.")
    return True

# Пример использования
json_file = 't_text.json'  # Замените на путь к вашему JSON файлу
xliff_file = 't_text.xliff'  # Замените на путь к вашему XLIFF файлу

if replace_ids_with_translations(json_file, xliff_file):
    print("Файл JSON успешно обновлен.")
else:
    print("Произошла ошибка при обработке файлов.")