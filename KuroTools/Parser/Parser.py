import json
import xml.etree.ElementTree as ET
import os
import random
import string

def generate_random_id(length=10):
    """Генерирует случайный ID из букв и цифр."""
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

def find_and_replace_text(json_filepath, text_fields):
    """
    Находит текст в JSON по указанным ключам, создает XLIFF и заменяет текст на ID.

    Args:
        json_filepath: Путь к JSON файлу.
        text_fields: Список ключей, по которым осуществляется поиск текста.

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

    # Создаем корневой элемент XLIFF
    xliff_root = ET.Element("xliff", version="1.2", xmlns="urn:oasis:names:tc:xliff:document:1.2")
    file_element = ET.SubElement(xliff_root, "file", original=os.path.basename(json_filepath), source_language="en", target_language="ru")
    body_element = ET.SubElement(file_element, "body")

    # Словарь для хранения соответствия ID и исходного текста
    id_map = {}

    def recursive_search_and_replace(obj):
        """Рекурсивно ищет текст в JSON и заменяет его на ID."""
        if isinstance(obj, dict):
            for key, value in obj.items():
                if key in text_fields and isinstance(value, str) and value:  # Проверяем, что значение - строка и не пустая
                    text_id = generate_random_id()
                    id_map[text_id] = value  # Сохраняем соответствие ID и текста
                    obj[key] = text_id  # Заменяем текст на ID

                    # Добавляем текст в XLIFF
                    trans_unit = ET.SubElement(body_element, "trans-unit", id=text_id)
                    source = ET.SubElement(trans_unit, "source")
                    source.text = value.replace("\n", "\\n")  # Сохраняем \n как текст
                    target = ET.SubElement(trans_unit, "target")
                    target.text = ""  # Пустой target
                elif isinstance(value, (dict, list)):  # Рекурсивный вызов для вложенных объектов
                    recursive_search_and_replace(value)
        elif isinstance(obj, list):
            for item in obj:
                if isinstance(item, (dict, list)):  # Рекурсивный вызов для вложенных объектов
                    recursive_search_and_replace(item)

    # Запуск рекурсивного поиска и замены
    recursive_search_and_replace(data)

    # Записываем измененный JSON
    try:
        with open(json_filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
    except IOError as e:
        print(f"Ошибка при записи измененного JSON: {e}")
        return False

    # Создаем XLIFF файл
    xliff_filepath = os.path.splitext(json_filepath)[0] + ".xliff"
    try:
        tree = ET.ElementTree(xliff_root)
        tree.write(xliff_filepath, encoding="utf-8", xml_declaration=True)
    except IOError as e:
        print(f"Ошибка при записи XLIFF файла: {e}")
        return False

    print(f"Обработка завершена. JSON перезаписан, XLIFF файл создан: {xliff_filepath}")
    return True


# Пример использования
json_file = 't_text.json'  # Замените на путь к вашему JSON файлу
text_fields_to_translate = ["value"]

# Запуск программы
if find_and_replace_text(json_file, text_fields_to_translate):
    print("Программа успешно завершила работу.")
else:
    print("Произошла ошибка при выполнении программы.")