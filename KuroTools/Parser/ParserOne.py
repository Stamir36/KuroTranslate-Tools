import json
import xml.etree.ElementTree as ET
import os
import random
import string
import logging
import re # Импортируем модуль для работы с регулярными выражениями
import xml.dom.minidom # Для красивого форматирования XLIFF

# Настройка логирования (опционально)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
# logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s') # Для отладки

def generate_random_id(length=10):
    """Генерирует случайный ID из букв и цифр."""
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

def find_and_replace_text(json_filepath, text_fields):
    """
    Находит текст в JSON по указанным ключам.
    Если значение состоит из одного слова (без пробелов внутри) и НЕ содержит кириллицы:
    - Генерирует ID.
    - Добавляет запись в XLIFF.
    - Заменяет значение в JSON на этот ID.
    В остальных случаях значение остается неизменным в JSON и не добавляется в XLIFF.

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
        logging.info(f"JSON файл '{json_filepath}' успешно загружен.")
    except FileNotFoundError:
        logging.error(f"Ошибка: JSON файл не найден по пути '{json_filepath}'")
        return False
    except json.JSONDecodeError as e:
        logging.error(f"Ошибка декодирования JSON файла '{json_filepath}': {e}")
        return False
    except Exception as e:
        logging.error(f"Непредвиденная ошибка при чтении JSON файла '{json_filepath}': {e}")
        return False

    # Создаем корневой элемент XLIFF
    xliff_root = ET.Element("xliff", version="1.2", xmlns="urn:oasis:names:tc:xliff:document:1.2")
    file_element = ET.SubElement(xliff_root, "file", original=os.path.basename(json_filepath), source_language="en", target_language="ru") # Укажите правильные языки
    body_element = ET.SubElement(file_element, "body")

    # Счетчик добавленных в XLIFF записей
    xliff_count = 0
    # Регулярное выражение для поиска кириллических символов (основной диапазон Unicode)
    cyrillic_pattern = re.compile(r'[\u0400-\u04FF]')

    def recursive_process(obj):
        """
        Рекурсивно обходит JSON. Если находит подходящее однословное значение
        без кириллицы, заменяет его на ID в JSON и добавляет в XLIFF.
        """
        nonlocal xliff_count
        if isinstance(obj, dict):
            keys_to_iterate = list(obj.keys())
            for key in keys_to_iterate:
                value = obj[key]

                # Шаг 1: Проверка ключа и типа значения
                if key in text_fields and isinstance(value, str) and value:
                    # Используем оригинальное значение для XLIFF и ID-генерации,
                    # а обрезанное - для проверок.
                    original_value_for_xliff = value
                    text_for_check = value.strip() # Убираем пробелы по краям для проверок

                    # Шаг 2: Проверка на однословность И на отсутствие кириллицы
                    is_single_word = ' ' not in text_for_check
                    contains_cyrillic = cyrillic_pattern.search(text_for_check) is not None

                    if is_single_word and not contains_cyrillic:
                        # Действия для подходящих значений:
                        text_id = generate_random_id()

                        # 2.1. Заменяем значение в JSON на ID
                        obj[key] = text_id
                        logging.debug(f"Ключ '{key}': значение '{text_for_check}' (одно слово, не кириллица) заменено на ID '{text_id}' в JSON.")

                        # 2.2. Добавляем в XLIFF (используем исходное значение с пробелами по краям, если они были)
                        trans_unit = ET.SubElement(body_element, "trans-unit", id=text_id)
                        source = ET.SubElement(trans_unit, "source")
                        source.text = original_value_for_xliff.replace("\n", "\\n")
                        target = ET.SubElement(trans_unit, "target")
                        target.text = ""
                        xliff_count += 1
                        logging.debug(f"Значение '{original_value_for_xliff}' добавлено в XLIFF с ID '{text_id}'.")
                    else:
                        # Значение не подходит
                        reason = []
                        if not is_single_word:
                            reason.append("много слов")
                        if contains_cyrillic:
                            reason.append("содержит кириллицу")
                        if not reason: # На случай если проверки не сработали как ожидалось
                            reason.append("неизвестная причина")

                        logging.debug(f"Ключ '{key}': значение '{text_for_check[:30]}...' пропущено ({', '.join(reason)}), оставлено без изменений.")

                # Шаг 3: Продолжаем рекурсию для вложенных структур
                elif isinstance(value, (dict, list)):
                    recursive_process(value)

        elif isinstance(obj, list):
            for item in obj:
                if isinstance(item, (dict, list)):
                    recursive_process(item)

    # Запуск рекурсивной обработки
    logging.info("Начало обработки JSON...")
    recursive_process(data)
    logging.info("Обработка JSON завершена.")

    # Записываем измененный JSON
    try:
        with open(json_filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        logging.info(f"Измененный JSON успешно записан в файл '{json_filepath}'.")
    except IOError as e:
        logging.error(f"Ошибка при записи измененного JSON файла '{json_filepath}': {e}")
        return False
    except Exception as e:
        logging.error(f"Непредвиденная ошибка при записи JSON файла '{json_filepath}': {e}")
        return False

    # Создаем XLIFF файл, только если были найдены подходящие записи
    if xliff_count > 0:
        xliff_filepath = os.path.splitext(json_filepath)[0] + ".xliff"
        try:
            rough_string = ET.tostring(xliff_root, encoding='utf-8', method='xml')
            reparsed = xml.dom.minidom.parseString(rough_string)
            with open(xliff_filepath, "w", encoding='utf-8') as f:
                f.write(reparsed.toprettyxml(indent="  "))
            logging.info(f"Создан XLIFF файл '{xliff_filepath}' с {xliff_count} записями (одно слово, не кириллица).")
        except IOError as e:
            logging.error(f"Ошибка при записи XLIFF файла '{xliff_filepath}': {e}")
        except Exception as e:
             logging.error(f"Непредвиденная ошибка при записи XLIFF файла '{xliff_filepath}': {e}")
    else:
        logging.info("Не найдено однословных некириллических значений для добавления в XLIFF. Файл XLIFF не создан.")

    return True



json_file = 't_voice_subtitle.json'

# Укажите список ключей, значения которых нужно проверить.
# В XLIFF попадут только те, что без пробелов в названии ключа.
text_fields_to_translate = [
    "text", "text_2"
]


# Запуск программы
print(f"\n--- Запуск обработки файла: {json_file} ---")
if find_and_replace_text(json_file, text_fields_to_translate):
    print(f"--- Обработка файла {json_file} завершена успешно. ---")
else:
    print(f"--- При обработке файла {json_file} произошла ошибка. ---")