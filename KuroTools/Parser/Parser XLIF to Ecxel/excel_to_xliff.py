import pandas as pd # type: ignore
import xml.etree.ElementTree as ET
from xml.dom import minidom # Для красивого форматирования XML
import argparse
import math # Для проверки на NaN

def prettify_xml(elem):
    """Возвращает красиво отформатированную строку XML."""
    rough_string = ET.tostring(elem, 'utf-8')
    reparsed = minidom.parseString(rough_string)
    # toprettyxml добавляет лишние пустые строки, используем splitlines/join для их удаления
    return '\n'.join([line for line in reparsed.toprettyxml(indent="  ").splitlines() if line.strip()])


def excel_to_xliff(excel_path, xliff_path, source_lang='en', target_lang='ru', original_filename='combined_python_scripts'):
    """
    Конвертирует Excel таблицу обратно в XLIFF файл.

    Args:
        excel_path (str): Путь к входному Excel файлу.
        xliff_path (str): Путь для сохранения выходного XLIFF файла.
        source_lang (str): Исходный язык (например, 'en').
        target_lang (str): Целевой язык (например, 'ru').
        original_filename (str): Значение для атрибута 'original' в теге <file>.
    """
    try:
        # Читаем Excel, убеждаемся, что пустые ячейки читаются как пустые строки, а не NaN
        df = pd.read_excel(excel_path, engine='openpyxl', dtype=str)
        # Дополнительная обработка NaN на случай, если dtype=str не сработал идеально
        df.fillna('', inplace=True)


        # Проверяем наличие необходимых столбцов
        required_columns = ['ID', 'FILE', 'ENGLISH', 'RUSSIAN']
        if not all(col in df.columns for col in required_columns):
            missing = [col for col in required_columns if col not in df.columns]
            print(f"Ошибка: В Excel файле отсутствуют необходимые столбцы: {', '.join(missing)}")
            return

        # --- Создаем структуру XLIFF ---
        xliff_ns = 'urn:oasis:names:tc:xliff:document:1.2'
        ET.register_namespace('', xliff_ns) # Регистрируем как default namespace

        # Корневой элемент <xliff>
        root = ET.Element('xliff', version='1.2', xmlns=xliff_ns)

        # Элемент <file>
        file_elem = ET.SubElement(root, 'file',
                                  original=original_filename,
                                  datatype='plaintext',
                                  source_language=source_lang,
                                  target_language=target_lang)

        # Элемент <body>
        body_elem = ET.SubElement(file_elem, 'body')

        # --- Заполняем данными из DataFrame ---
        for index, row in df.iterrows():
            # Получаем данные из строки, гарантируем строковый тип
            unit_id = str(row['ID'])
            filename = str(row['FILE'])
            source_text = str(row['ENGLISH'])
            target_text = str(row['RUSSIAN'])

            # Создаем <trans-unit>
            trans_unit = ET.SubElement(body_elem, 'trans-unit', id=unit_id)

            # Создаем <note> (если имя файла есть)
            if filename:
                note = ET.SubElement(trans_unit, 'note')
                note.text = f"File: {filename}"

            # Создаем <source>
            source = ET.SubElement(trans_unit, 'source')
            # Заменяем символы новой строки обратно на \n если нужно для совместимости с каким-то инструментом
            # НО обычно ElementTree сам правильно экранирует XML
            # source.text = source_text.replace('\n', '\\n') # Оставляем как есть, ET сам обработает
            source.text = source_text

            # Создаем <target>
            target = ET.SubElement(trans_unit, 'target')
            # target.text = target_text.replace('\n', '\\n') # Оставляем как есть
            target.text = target_text


        # --- Сохраняем XLIFF файл ---
        # Используем minidom для красивого вывода
        pretty_xml_string = prettify_xml(root)

        with open(xliff_path, 'w', encoding='utf-8') as f:
            # Добавляем XML декларацию вручную, т.к. prettify_xml её не всегда добавляет
            f.write('<?xml version=\'1.0\' encoding=\'UTF-8\'?>\n')
            f.write(pretty_xml_string)

        # Альтернативный способ без красивого форматирования:
        # tree = ET.ElementTree(root)
        # tree.write(xliff_path, encoding='utf-8', xml_declaration=True, default_namespace=xliff_ns)
        # print("Внимание: файл сохранен без дополнительного форматирования (отступов).")


        print(f"XLIFF файл успешно сохранен в: {xliff_path}")

    except FileNotFoundError:
        print(f"Ошибка: Excel файл не найден по пути: {excel_path}")
    except Exception as e:
        print(f"Произошла непредвиденная ошибка: {e}")
        import traceback
        traceback.print_exc() # Печатаем traceback для отладки

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Конвертировать Excel таблицу обратно в XLIFF файл.")
    parser.add_argument("excel_file", help="Путь к входному Excel файлу (.xlsx).")
    parser.add_argument("xliff_file", help="Путь для сохранения выходного XLIFF файла.")
    parser.add_argument("-sl", "--source_language", default="en", help="Исходный язык (атрибут source-language). По умолчанию: en")
    parser.add_argument("-tl", "--target_language", default="ru", help="Целевой язык (атрибут target-language). По умолчанию: ru")
    parser.add_argument("-o", "--original", default="combined_python_scripts", help="Имя оригинального файла (атрибут original). По умолчанию: combined_python_scripts")

    args = parser.parse_args()

    excel_to_xliff(args.excel_file, args.xliff_file, args.source_language, args.target_language, args.original)