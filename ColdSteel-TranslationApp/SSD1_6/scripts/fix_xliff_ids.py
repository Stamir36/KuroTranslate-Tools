import os
import sys
import hashlib
import lxml.etree as ET

def fix_ids_in_xliff_final(filepath):
    """
    Читает XLIFF файл, генерирует 100% уникальные ID для КАЖДОГО элемента <trans-unit>
    и сохраняет результат в новый файл.
    ID генерируется на основе: содержимого <source>, атрибута resname,
    содержимого <note> и уникального порядкового номера.
    """
    print(f"--- Начало исправления файла: {os.path.basename(filepath)} ---")
    
    LXML_NS_MAP = {'xliff': 'urn:oasis:names:tc:xliff:document:1.2'}

    try:
        # Используем парсер, который сохраняет комментарии и форматирование
        parser = ET.XMLParser(remove_blank_text=False, strip_cdata=False, resolve_entities=False)
        tree = ET.parse(filepath, parser=parser)
        
        # Находим все элементы <trans-unit>
        trans_units = tree.xpath('//xliff:trans-unit', namespaces=LXML_NS_MAP)
        
        if not trans_units:
            print("Ошибка: В файле не найдены элементы <trans-unit>.")
            return

        print(f"Найдено {len(trans_units)} элементов <trans-unit> для обработки.")
        processed_count = 0
        counter = 0  # Инициализируем счётчик для 100% уникальности
        
        # Проходим по каждому элементу
        for unit in trans_units:
            source_node = unit.find('xliff:source', namespaces=LXML_NS_MAP)
            note_node = unit.find('xliff:note', namespaces=LXML_NS_MAP)
            resname = unit.get('resname')

            # Убеждаемся, что все необходимые части на месте
            if source_node is None or resname is None:
                print(f"Предупреждение: Пропущен <trans-unit> без <source> или resname.")
                continue

            source_text = source_node.text if source_node.text is not None else ""
            # Добавляем текст из <note> в хэш
            note_text = note_node.text if note_node is not None and note_node.text is not None else ""
            
            # Генерируем новый, гарантированно уникальный ID
            unique_string_for_hash = f"{source_text}|{resname}|{note_text}|{counter}"
            new_id = hashlib.sha1(unique_string_for_hash.encode('utf-8')).hexdigest()[:12]
            
            # Устанавливаем новый ID
            unit.set('id', new_id)
            processed_count += 1
            counter += 1 # Увеличиваем счётчик для следующей строки

        print(f"Обработано {processed_count} элементов.")

        # Сохраняем результат в новый файл
        output_path = os.path.splitext(filepath)[0] + '_FIXED.xliff'
        
        tree.write(
            output_path,
            pretty_print=True,
            encoding='utf-8',
            xml_declaration=True
        )
        
        print("\n--- ИСПРАВЛЕНИЕ ЗАВЕРШЕНО УСПЕШНО! ---")
        print(f"Ваш исправленный файл сохранен как: {os.path.basename(output_path)}")
        print("Теперь ID для КАЖДОЙ строки гарантированно уникален.")
        print("Пожалуйста, откройте этот новый файл ('_FIXED.xliff') в вашем редакторе.")

    except ET.XMLSyntaxError as e:
        print(f"\nКРИТИЧЕСКАЯ ОШИБКА: Не удалось прочитать XML файл. Он может быть поврежден.")
        print(f"Детали ошибки: {e}")
    except Exception as e:
        print(f"\nПроизошла непредвиденная ошибка: {e}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        file_path = sys.argv[1]
        if file_path.lower().endswith('.xliff'):
            fix_ids_in_xliff_final(file_path)
        else:
            print("Ошибка: Пожалуйста, перетащите на этот скрипт файл с расширением .xliff")
    else:
        print("Инструкция: Перетащите ваш проблемный .xliff файл на иконку этого скрипта.")
    
    input("\nНажмите Enter для выхода.")