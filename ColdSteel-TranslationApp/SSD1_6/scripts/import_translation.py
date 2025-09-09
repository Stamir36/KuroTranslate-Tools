import xlwings as xw
from lxml import etree
import sys
import os
import shutil

def import_translation_via_excel(xliff_path):
    xlsx_path = os.path.splitext(xliff_path)[0] + '.xlsx'
    if not os.path.exists(xlsx_path):
        print(f"Ошибка: Не найден соответствующий XLSX файл: {xlsx_path}")
        input("Нажмите Enter для выхода.")
        return

    # 1. Создание резервной копии - это по-прежнему хорошая идея
    backup_path = xlsx_path + '.bak'
    try:
        print(f"1. Создаю резервную копию: {os.path.basename(backup_path)}...")
        shutil.copy(xlsx_path, backup_path)
    except Exception as e:
        print(f"Не удалось создать резервную копию: {e}")
        input("Нажмите Enter для выхода.")
        return

    # 2. Чтение переводов из XLIFF (эта часть не меняется)
    print("2. Читаю переводы из XLIFF файла...")
    try:
        parser = etree.XMLParser(remove_blank_text=True)
        tree = etree.parse(xliff_path, parser)
        root = tree.getroot()
        ns = {'xliff': 'urn:oasis:names:tc:xliff:document:1.2'}
        
        translations = {}
        for trans_unit in root.findall('.//xliff:trans-unit', namespaces=ns):
            target_tag = trans_unit.find('xliff:target', namespaces=ns)
            resname = trans_unit.get('resname')
            
            if target_tag is not None and target_tag.text and resname:
                target_text = target_tag.text.strip()
                if target_text:
                    translations[resname] = target_text

        if not translations:
            print("\nВ файле XLIFF не найдено заполненных переводов. Изменений не будет.")
            os.remove(backup_path)
            input("Нажмите Enter для выхода.")
            return
            
    except Exception as e:
        print(f"\nОшибка при чтении XLIFF файла: {e}")
        input("Нажмите Enter для выхода.")
        return

    # 3. --- ГЛАВНОЕ ИЗМЕНЕНИЕ: Используем Excel для внесения правок ---
    app = None
    try:
        print("3. Запускаю Excel в фоновом режиме для безопасного редактирования...")
        # Запускаем Excel невидимо для пользователя
        app = xw.App(visible=False)
        # Отключаем любые предупреждения от Excel (например, "сохранить?")
        app.display_alerts = False
        
        # Открываем книгу
        book = app.books.open(xlsx_path)
        
        print(f"4. Вношу {len(translations)} изменений в файл...")
        updated_count = 0
        
        for cell_address, translated_text in translations.items():
            try:
                sheet_name, cell_coord = cell_address.split('!', 1)
                sheet = book.sheets[sheet_name]
                # Напрямую меняем значение ячейки
                sheet.range(cell_coord).value = translated_text
                updated_count += 1
            except Exception as e:
                print(f"\nПредупреждение: не удалось обновить ячейку {cell_address}. Ошибка: {e}")

        # 5. Сохраняем и закрываем
        if updated_count > 0:
            print("5. Сохраняю изменения через Excel...")
            book.save()
            book.close()
            print(f"\nУспешно обновлено {updated_count} строк.")
            print(f"Файл '{os.path.basename(xlsx_path)}' изменен без повреждения структуры.")
        else:
            book.close()
            print("\nНе найдено ячеек для обновления.")
            os.remove(backup_path)

    except Exception as e:
        print(f"\nПроизошла критическая ошибка: {e}")
        print("Возможно, у вас не установлен Excel, или файл защищен от записи.")
    finally:
        # Гарантированно закрываем процесс Excel, чтобы он не завис
        if app:
            app.quit()
    
    input("\nРабота завершена. Нажмите Enter для выхода.")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        file_path = sys.argv[1]
        if file_path.endswith('.xliff'):
            import_translation_via_excel(file_path)
        else:
            print("Ошибка: Пожалуйста, перетащите файл с расширением .xliff на этот скрипт.")
            input("Нажмите Enter для выхода.")
    else:
        print("Инструкция: Пожалуйста, перетащите .xliff файл с переводами на этот скрипт.")
        input("Нажмите Enter для выхода.")