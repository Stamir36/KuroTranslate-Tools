import xml.etree.ElementTree as ET
import pandas as pd # type: ignore
import argparse
import re
import os

def extract_filename_from_note(note_text):
    """Извлекает имя файла из текста заметки (например, 'File: a0601.py')."""
    if not note_text:
        return ""
    # Используем регулярное выражение для надежного извлечения
    match = re.search(r"File:\s*(\S+)", note_text, re.IGNORECASE)
    if match:
        return match.group(1)
    # Запасной вариант - простое разделение строки
    if ':' in note_text:
         parts = note_text.split(':', 1)
         if len(parts) > 1:
             return parts[1].strip()
    return note_text # Возвращаем исходный текст, если формат не распознан

def xliff_to_excel(xliff_path, excel_path):
    """
    Конвертирует XLIFF файл в Excel таблицу.

    Args:
        xliff_path (str): Путь к входному XLIFF файлу.
        excel_path (str): Путь для сохранения выходного Excel файла.
    """
    try:
        # Регистрируем пространство имен XLIFF для корректного поиска элементов
        # Это важно, т.к. XLIFF использует default namespace
        namespaces = {'xliff': 'urn:oasis:names:tc:xliff:document:1.2'}
        ET.register_namespace('', namespaces['xliff']) # Регистрируем как default namespace

        tree = ET.parse(xliff_path)
        root = tree.getroot()

        data = []

        # Ищем все элементы trans-unit внутри body
        # Используем пространство имен при поиске
        body = root.find('.//xliff:body', namespaces)
        if body is None:
             print(f"Ошибка: Тег <body> не найден в файле {xliff_path}. Возможно, это невалидный XLIFF 1.2.")
             return

        for trans_unit in body.findall('xliff:trans-unit', namespaces):
            unit_id = trans_unit.get('id', '') # Безопасно получаем id

            note_element = trans_unit.find('xliff:note', namespaces)
            note_text = note_element.text if note_element is not None else ""
            filename = extract_filename_from_note(note_text)

            source_element = trans_unit.find('xliff:source', namespaces)
            source_text = source_element.text if source_element is not None else ""
            # Важно: Сохраняем переносы строк как есть
            source_text = source_text.replace('\\n', '\n') if source_text else ""


            target_element = trans_unit.find('xliff:target', namespaces)
            target_text = target_element.text if target_element is not None else ""
             # Важно: Сохраняем переносы строк как есть
            target_text = target_text.replace('\\n', '\n') if target_text else ""

            data.append({
                'ID': unit_id,
                'FILE': filename,
                'ENGLISH': source_text,
                'RUSSIAN': target_text
            })

        if not data:
            print(f"Предупреждение: Не найдено элементов <trans-unit> в файле {xliff_path}.")
            # Создаем пустой DataFrame с нужными колонками, чтобы не было ошибки при сохранении
            df = pd.DataFrame(columns=['ID', 'FILE', 'ENGLISH', 'RUSSIAN'])
        else:
            df = pd.DataFrame(data)

        # Сохраняем в Excel
        df.to_excel(excel_path, index=False, engine='openpyxl')
        print(f"Файл Excel успешно сохранен в: {excel_path}")

    except ET.ParseError:
        print(f"Ошибка: Не удалось разобрать XML файл: {xliff_path}. Проверьте его валидность.")
    except FileNotFoundError:
        print(f"Ошибка: XLIFF файл не найден по пути: {xliff_path}")
    except Exception as e:
        print(f"Произошла непредвиденная ошибка: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Конвертировать XLIFF файл в Excel таблицу.")
    parser.add_argument("xliff_file", help="Путь к входному XLIFF файлу.")
    parser.add_argument("excel_file", help="Путь для сохранения выходного Excel файла (.xlsx).")

    args = parser.parse_args()

    # Добавляем .xlsx, если не указано
    if not args.excel_file.lower().endswith(".xlsx"):
        args.excel_file += ".xlsx"

    xliff_to_excel(args.xliff_file, args.excel_file)