# --- START OF FILE xliff_editor_gui.py ---

import tkinter as tk
from tkinter import filedialog, messagebox, font as tkfont
import customtkinter as ctk # type: ignore
import lxml.etree as ET # type: ignore
import os
import sys # <--- Добавлено для sys.argv
import shutil
import math
import io
import uuid
import traceback
import time # <--- Добавлено для задержки перевода

'''
    Исходный язык может быть не только английский, но и корейский, или другой. Пусть язык определяется автоматически.
    Далее добавь выбор в дропбокс переводчика Google или MyMemory (но если он используется нужно указывать язык типа ru-RU или как там).
    А так же кнопки размера шрифта.
'''

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

# --- Pygments imports ---
try:
    from pygments.lexers import XmlLexer
    from pygments import lex
    from pygments.token import Token
    PYGMENTS_AVAILABLE = True
except ImportError:
    print("Предупреждение: Библиотека Pygments не найдена (pip install Pygments). Подсветка синтаксиса будет отключена.")
    PYGMENTS_AVAILABLE = False
    XmlLexer = None
    Token = object

# --- Deep Translator imports --- # <--- ДОБАВЛЕНО
try:
    from deep_translator import GoogleTranslator, MyMemoryTranslator # type: ignore
    # Установим Google как сервис по умолчанию, так как он лучше работает с en->ru
    DEFAULT_TRANSLATOR_SERVICE = "Google" # Или "MyMemory"
    TRANSLATION_AVAILABLE = True
    print(f"Библиотека deep-translator найдена. Сервис по умолчанию: {DEFAULT_TRANSLATOR_SERVICE}")
except ImportError:
    print(f"{Fore.YELLOW}Предупреждение: Библиотека deep-translator не найдена (pip install deep-translator). Автоматический перевод будет недоступен.{Style.RESET_ALL}")
    TRANSLATION_AVAILABLE = False
    GoogleTranslator = MyMemoryTranslator = None
    DEFAULT_TRANSLATOR_SERVICE = None
# --- /Deep Translator imports --- # <--- КОНЕЦ ДОБАВЛЕННОГО

# --- Конфигурация ---
XLIFF_FILE_DEFAULT = "data_game_strings.xliff"
BACKUP_SUFFIX = ".bak"
SOURCE_LANG = "en" # Исходный язык (для перевода и XLIFF)
TARGET_LANG = "ru" # Целевой язык (для перевода и XLIFF)
ITEMS_PER_PAGE_DEFAULT = 500
DEFAULT_MODE = "markup"
TRANSLATION_DELAY_SECONDS = 0.15 # Задержка между запросами к API перевода # <--- ДОБАВЛЕНО
# --------------------

# --- Настройки customtkinter ---
ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")

# --- Конфигурация подсветки синтаксиса ---
def get_token_attr(token_base, attr_name, default_value):
    if PYGMENTS_AVAILABLE and hasattr(token_base, attr_name):
        return getattr(token_base, attr_name)
    return default_value

TEXT_HIGHLIGHT_CONFIG = {
    "lexer": XmlLexer() if PYGMENTS_AVAILABLE else None,
    "tags": {
        get_token_attr(Token, 'Comment', 'Token.Comment'): {"foreground": "gray"},
        get_token_attr(Token, 'Keyword', 'Token.Keyword'): {"foreground": "#007020"},
        get_token_attr(Token.Name, 'Tag', 'Token.Name.Tag'): {"foreground": "#0077aa"},
        get_token_attr(Token.Name, 'Attribute', 'Token.Name.Attribute'): {"foreground": "#bb0066"},
        get_token_attr(Token.Literal, 'String', 'Token.Literal.String'): {"foreground": "#dd2200"},
        get_token_attr(Token, 'Punctuation', 'Token.Punctuation'): {"foreground": "#6a6a6a"},
        get_token_attr(Token, 'Operator', 'Token.Operator'): {"foreground": "#6a6a6a"},
    } if PYGMENTS_AVAILABLE else {}
}

# --- Глобальные переменные ---
xliff_tree = None
xliff_root = None
xliff_filepath = ""
all_trans_units = []
untranslated_ids = []
current_page_index = 0
items_per_page = ITEMS_PER_PAGE_DEFAULT
current_page_units_map = {}
is_dirty = False
current_mode = DEFAULT_MODE

main_window = None
editor_textbox = None
save_button = None
open_button = None
markup_mode_button = None
edit_mode_button = None
translate_button = None # <--- Добавлено
status_label = None
page_label = None
prev_button = None
next_button = None
page_entry = None
go_button = None
page_size_entry = None
page_size_button = None
page_var = None
page_size_var = None

LXML_NSMAP = {'xliff': 'urn:oasis:names:tc:xliff:document:1.2'}

# --- Общие функции UI ---

def update_status(message):
    """Обновляет текст в строке статуса."""
    global status_label
    if status_label:
        status_label.configure(text=message)
    # Немедленно обновить GUI для отображения статуса
    if main_window:
        main_window.update_idletasks()

def reset_state():
     """Сбрасывает состояние приложения."""
     global xliff_tree, xliff_root, xliff_filepath, all_trans_units, untranslated_ids
     global current_page_index, is_dirty, current_page_units_map, editor_textbox
     global save_button, status_label, page_label, prev_button, next_button
     global page_entry, go_button, page_size_entry, page_size_button, page_var
     global translate_button # <--- Добавлено

     xliff_tree = xliff_root = None
     xliff_filepath = ""
     all_trans_units = []
     untranslated_ids = []
     current_page_units_map = {}
     current_page_index = 0
     is_dirty = False

     if editor_textbox is not None:
         text_widget = editor_textbox._textbox if hasattr(editor_textbox, '_textbox') else None
         editor_textbox.configure(state=tk.NORMAL)
         editor_textbox.delete("1.0", tk.END)
         editor_textbox.configure(state=tk.DISABLED)
         if text_widget:
             try: text_widget.edit_modified(False)
             except tk.TclError: pass

     if save_button: save_button.configure(state=tk.DISABLED)
     if prev_button: prev_button.configure(state=tk.DISABLED)
     if next_button: next_button.configure(state=tk.DISABLED)
     if page_entry: page_entry.configure(state=tk.DISABLED)
     if go_button: go_button.configure(state=tk.DISABLED)
     if page_size_entry: page_size_entry.configure(state=tk.DISABLED)
     if page_size_button: page_size_button.configure(state=tk.DISABLED)
     if translate_button: translate_button.configure(state=tk.DISABLED) # <--- Добавлено
     if page_var: page_var.set("")
     if page_label: page_label.configure(text="Страница: - / -")

     update_status("Готово к загрузке файла.")
     if main_window: main_window.title("XLIFF Paged Editor")

def _get_inner_text_widget():
    """Вспомогательная функция для получения внутреннего tk.Text виджета."""
    if editor_textbox and hasattr(editor_textbox, '_textbox'):
        return editor_textbox._textbox
    return None

def _check_inner_focus():
    """Проверяет, находится ли фокус на внутреннем tk.Text виджете."""
    inner_widget = _get_inner_text_widget()
    if not inner_widget or not main_window: return False
    try: return main_window.focus_get() == inner_widget
    except Exception: return False

def select_all_text(event=None):
    """Выделяет весь текст в редакторе."""
    target_widget = _get_inner_text_widget()
    if not target_widget: return None
    is_focused = _check_inner_focus()
    if xliff_tree is not None and is_focused:
        try:
            start_index = target_widget.index("1.0")
            end_index = target_widget.index(tk.END + "-1c")
            if start_index != end_index:
                target_widget.tag_remove(tk.SEL, "1.0", tk.END)
                target_widget.tag_add(tk.SEL, start_index, end_index)
                target_widget.mark_set(tk.INSERT, start_index)
                target_widget.see(tk.INSERT)
        except Exception as e: print(f"Ошибка при выделении текста: {e}")
        return 'break'
    return None

def cut_text(event=None):
    """Вырезает выделенный текст."""
    target_widget = _get_inner_text_widget()
    if not target_widget: return None
    is_focused = _check_inner_focus()
    if xliff_tree is not None and is_focused:
        try:
            if target_widget.tag_ranges(tk.SEL):
                target_widget.event_generate("<<Cut>>")
        except Exception as e: print(f"Ошибка при вырезании текста: {e}")
        return 'break'
    return None

def copy_text(event=None):
    """Копирует выделенный текст."""
    target_widget = _get_inner_text_widget()
    if not target_widget: return None
    is_focused = _check_inner_focus()
    if is_focused:
        try:
            if target_widget.tag_ranges(tk.SEL):
                target_widget.event_generate("<<Copy>>")
        except Exception as e: print(f"Ошибка при копировании текста: {e}")
        return 'break'
    return None

def paste_text(event=None):
    """Вставляет текст из буфера обмена."""
    target_widget = _get_inner_text_widget()
    if not target_widget: return None
    is_focused = _check_inner_focus()
    if xliff_tree is not None and is_focused:
        try:
            target_widget.event_generate("<<Paste>>")
        except Exception as e: print(f"Ошибка при вставке текста: {e}")
        return 'break'
    return None

def set_focus_on_editor():
    """Устанавливает фокус на внутренний текстовый виджет."""
    inner_widget = _get_inner_text_widget()
    if inner_widget:
        try: inner_widget.focus_set()
        except tk.TclError as e: print(f"Ошибка при установке фокуса: {e}")

def update_page_size(*args):
    """Обрабатывает изменение размера страницы."""
    global items_per_page, current_page_index, page_size_var, is_dirty, save_button
    inner_widget = _get_inner_text_widget()
    if not all_trans_units: return
    try:
        new_size = int(page_size_var.get())
        if new_size > 0:
            page_modified = False
            if inner_widget:
                 try: page_modified = inner_widget.edit_modified()
                 except tk.TclError: pass

            if page_modified:
                 if not messagebox.askyesno("Несохраненные изменения", "Есть изменения. Сменить размер без сохранения?"):
                     page_size_var.set(str(items_per_page))
                     return
                 else:
                     # Пытаемся сохранить перед сменой размера
                     if not save_current_page_data_if_dirty(prompt_save=False):
                         messagebox.showerror("Ошибка", "Не удалось сохранить изменения. Смена размера отменена.")
                         page_size_var.set(str(items_per_page))
                         return

            current_first_item_global_index = current_page_index * items_per_page
            items_per_page = new_size
            current_page_index = current_first_item_global_index // items_per_page

            if current_mode == 'markup': display_markup_page()
            elif current_mode == 'edit': display_edit_page()
            update_status(f"Размер страницы изменен на {items_per_page}")
            set_focus_on_editor()
        else:
            messagebox.showwarning("Неверный размер", "Размер страницы должен быть > 0.")
            page_size_var.set(str(items_per_page))
    except ValueError:
        messagebox.showwarning("Неверный ввод", "Введите числовое значение размера.")
        page_size_var.set(str(items_per_page))
    except Exception as e:
        messagebox.showerror("Ошибка", f"Ошибка при изменении размера страницы: {e}\n{traceback.format_exc()}")
        page_size_var.set(str(items_per_page))
    update_navigation_buttons_state()

def go_to_page(*args):
    """Переходит на указанную страницу."""
    global current_page_index, page_var, untranslated_ids, items_per_page
    if not untranslated_ids: return
    try:
        page_num_str = page_var.get()
        if not page_num_str: return
        page_num = int(page_num_str)
        num_pages = math.ceil(len(untranslated_ids) / items_per_page) if untranslated_ids else 1

        if 1 <= page_num <= num_pages:
            new_page_index = page_num - 1
            if new_page_index == current_page_index: return
            # Пытаемся сохранить перед переходом
            if not save_current_page_data_if_dirty(prompt_save=True):
                page_var.set(str(current_page_index + 1))
                return
            current_page_index = new_page_index
            if current_mode == 'markup': display_markup_page()
            elif current_mode == 'edit': display_edit_page()
            update_status(f"Переход на страницу {current_page_index + 1}")
            set_focus_on_editor()
        else:
            messagebox.showwarning("Неверный номер", f"Введите номер страницы от 1 до {num_pages}.")
            page_var.set(str(current_page_index + 1))
    except ValueError:
        messagebox.showwarning("Неверный ввод", "Введите числовое значение номера страницы.")
        page_var.set(str(current_page_index + 1))
    except Exception as e:
         messagebox.showerror("Ошибка", f"Ошибка при переходе на страницу: {e}\n{traceback.format_exc()}")
         page_var.set(str(current_page_index + 1))

def go_to_next_page():
    """Переходит на следующую страницу."""
    global current_page_index, untranslated_ids, items_per_page
    num_pages = math.ceil(len(untranslated_ids) / items_per_page) if untranslated_ids else 1
    if current_page_index < num_pages - 1:
        if not save_current_page_data_if_dirty(prompt_save=True): return
        current_page_index += 1
        if current_mode == 'markup': display_markup_page()
        elif current_mode == 'edit': display_edit_page()
        update_status(f"Переход на страницу {current_page_index + 1}")
        set_focus_on_editor()

def go_to_prev_page():
    """Переходит на предыдущую страницу."""
    global current_page_index
    if current_page_index > 0:
        if not save_current_page_data_if_dirty(prompt_save=True): return
        current_page_index -= 1
        if current_mode == 'markup': display_markup_page()
        elif current_mode == 'edit': display_edit_page()
        update_status(f"Переход на страницу {current_page_index + 1}")
        set_focus_on_editor()

def update_navigation_buttons_state():
     """Обновляет состояние кнопок навигации."""
     global prev_button, next_button, go_button, page_entry, page_size_button, page_size_entry
     global translate_button, untranslated_ids, items_per_page, xliff_tree, current_page_units_map # <--- Добавлено translate_button, current_page_units_map
     has_content = bool(untranslated_ids)
     if not xliff_tree: has_content = False
     num_pages = math.ceil(len(untranslated_ids) / items_per_page) if has_content else 1

     prev_state = tk.NORMAL if has_content and current_page_index > 0 else tk.DISABLED
     next_state = tk.NORMAL if has_content and current_page_index < num_pages - 1 else tk.DISABLED
     entry_state = tk.NORMAL if has_content else tk.DISABLED
     # Состояние кнопки перевода
     translate_state = tk.NORMAL if xliff_tree and TRANSLATION_AVAILABLE and current_page_units_map else tk.DISABLED # <--- Добавлено

     if prev_button: prev_button.configure(state=prev_state)
     if next_button: next_button.configure(state=next_state)
     if page_entry: page_entry.configure(state=entry_state)
     if go_button: go_button.configure(state=entry_state)
     if translate_button: translate_button.configure(state=translate_state) # <--- Добавлено

     size_entry_state = tk.NORMAL if xliff_tree else tk.DISABLED
     if page_size_entry: page_size_entry.configure(state=size_entry_state)
     if page_size_button: page_size_button.configure(state=size_entry_state)

# --- Функции для работы с XLIFF ---

def load_xliff(filepath_arg=None): # <--- Добавлено filepath_arg
    """Загружает XLIFF файл."""
    global xliff_tree, xliff_root, xliff_filepath, all_trans_units, untranslated_ids
    global current_page_index, is_dirty, current_mode, save_button, status_label
    global page_label, open_button, items_per_page, page_size_var
    # Не нужно добавлять translate_button здесь, он обновляется в update_navigation_buttons_state

    if is_dirty:
        if not messagebox.askyesno("Несохраненные изменения", "Есть изменения. Загрузить новый файл без сохранения?"):
            return

    if filepath_arg: # <--- Если передан путь файла
        filepath = filepath_arg
    else:
        filepath = filedialog.askopenfilename(
            title="Выберите XLIFF файл",
            filetypes=[("XLIFF files", "*.xliff"), ("All files", "*.*")],
            initialdir=os.path.dirname(xliff_filepath) if xliff_filepath else ".",
            initialfile=os.path.basename(xliff_filepath) if xliff_filepath else XLIFF_FILE_DEFAULT
        )
    if not filepath: return

    reset_state() # Сбрасывает все состояния, включая кнопку перевода
    items_per_page = ITEMS_PER_PAGE_DEFAULT
    if page_size_var: page_size_var.set(str(items_per_page))

    try:
        print(f"Загрузка файла: {filepath}")
        parser = ET.XMLParser(remove_blank_text=False, strip_cdata=False, resolve_entities=False)
        xliff_tree = ET.parse(filepath, parser=parser)
        xliff_root = xliff_tree.getroot()

        expected_ns = LXML_NSMAP['xliff']
        if not xliff_root.tag.startswith(f"{{{expected_ns}}}"):
             if 'xliff' not in xliff_root.tag:
                 raise ValueError(f"Некорректный корневой элемент. Ожидался '{expected_ns}', получен '{xliff_root.tag}'.")
             else:
                 print(f"{Fore.YELLOW}Предупреждение: Пространство имен ('{xliff_root.tag}') отличается от '{expected_ns}'. Попытка продолжить.{Style.RESET_ALL}")

        xliff_filepath = filepath
        all_trans_units = xliff_root.xpath(".//xliff:trans-unit", namespaces=LXML_NSMAP)

        if not all_trans_units:
             print(f"{Fore.YELLOW}Предупреждение: В файле не найдено <trans-unit>.{Style.RESET_ALL}")

        # Определение непереведенных строк (как в исходном коде)
        untranslated_ids = []
        for unit in all_trans_units:
            unit_id = unit.get("id")
            if not unit_id:
                 print(f"{Fore.YELLOW}Предупреждение: <trans-unit> без 'id'. Пропускается.{Style.RESET_ALL}")
                 continue
            target_elements = unit.xpath("./xliff:target", namespaces=LXML_NSMAP)
            if not target_elements or not target_elements[0].xpath("normalize-space(.)"):
                 approved_attr = target_elements[0].get('approved') if target_elements else None
                 if approved_attr != 'yes':
                     untranslated_ids.append(unit_id)
                 # else:
                     # print(f"ID: {unit_id} пустой, но approved='yes'. Не добавлен.") # Debug

        current_page_index = 0
        is_dirty = False
        set_mode(current_mode, force_update=True) # Установка режима

        # Отображение первой страницы (это заполнит current_page_units_map)
        if current_mode == 'markup': display_markup_page()
        elif current_mode == 'edit': display_edit_page()

        update_status(f"Загружен: {os.path.basename(filepath)} | Всего: {len(all_trans_units)} | Без перевода: {len(untranslated_ids)}")
        if main_window: main_window.title(f"XLIFF Paged Editor - {os.path.basename(filepath)}")
        if save_button: save_button.configure(state=tk.DISABLED)
        if editor_textbox:
            editor_textbox.configure(state=tk.NORMAL)
            set_focus_on_editor()
        # Обновляем состояние кнопок ПОСЛЕ отображения первой страницы
        update_navigation_buttons_state()

    except ET.XMLSyntaxError as xe:
         messagebox.showerror("Ошибка парсинга XML", f"Не удалось разобрать XLIFF (синтаксис):\n{xe}")
         reset_state()
    except ValueError as ve:
         messagebox.showerror("Ошибка формата", f"Некорректный формат XLIFF:\n{ve}")
         reset_state()
    except Exception as e:
        messagebox.showerror("Ошибка загрузки", f"Не удалось загрузить XLIFF:\n{e}\n{traceback.format_exc()}")
        reset_state()

def save_current_page_data_if_dirty(prompt_save=False):
    """Сохраняет данные текущей страницы из редактора В ПАМЯТЬ."""
    global is_dirty, save_button
    inner_widget = _get_inner_text_widget()
    textbox_modified = False
    if inner_widget:
        try: textbox_modified = inner_widget.edit_modified()
        except tk.TclError:
            print("Ошибка проверки флага модификации виджета.")
            messagebox.showerror("Ошибка редактора", "Не удалось проверить наличие изменений.")
            return False

    if not textbox_modified: return True # Нет изменений в виджете

    should_save = True
    if prompt_save:
        mode_text = "разметки" if current_mode == 'markup' else "редактирования"
        result = messagebox.askyesnocancel("Сохранить изменения?", f"Сохранить изменения на стр. {current_page_index + 1} (режим {mode_text})?")
        if result is None: return False # Отмена действия
        elif result is False: # Не сохранять
            should_save = False
            if inner_widget:
                try: inner_widget.edit_modified(False) # Сбрасываем флаг, т.к. не сохраняем
                except tk.TclError: pass
            return True # Разрешаем действие без сохранения

    if should_save:
        success = False
        print(f"Сохранение данных страницы {current_page_index + 1}...") # Debug
        if current_mode == 'markup':
            success = save_markup_page_data(force_check=True) # force_check=True т.к. мы уже знаем, что есть изменения
            if not success:
                 messagebox.showerror("Ошибка сохранения", "Не удалось сохранить (разметка). Проверьте XML.")
                 return False
        elif current_mode == 'edit':
            success = save_edit_page_data(force_check=True)
            if not success:
                 messagebox.showerror("Ошибка сохранения", "Не удалось сохранить (редактирование).")
                 return False
        # Если сохранение успешно
        if success:
            if inner_widget:
                try:
                    inner_widget.edit_modified(False) # Сбрасываем флаг после сохранения
                    print(f"Флаг модификации редактора сброшен после сохранения стр. {current_page_index + 1}.") # Debug
                except tk.TclError: pass
            return True
        else:
            # Этого не должно произойти, если код выше отработал
             messagebox.showerror("Ошибка", "Непредвиденная ошибка при сохранении страницы.")
             return False
    else:
         # Сюда попадаем, если пользователь нажал "Нет"
         return True

def save_xliff():
    """Сохраняет все изменения из памяти в XLIFF файл."""
    global xliff_tree, xliff_filepath, is_dirty, save_button, status_label
    if xliff_tree is None or not xliff_filepath:
        messagebox.showwarning("Нет данных", "Сначала загрузите XLIFF файл.")
        return

    # Пытаемся сохранить данные ТЕКУЩЕЙ страницы перед сохранением файла
    if not save_current_page_data_if_dirty(prompt_save=False): # Не спрашиваем, просто пытаемся сохранить
        messagebox.showerror("Ошибка", "Не удалось сохранить изменения текущей страницы. Исправьте ошибки перед сохранением файла.")
        return

    # Проверяем глобальный флаг is_dirty
    if not is_dirty:
        if save_button: save_button.configure(state=tk.DISABLED)
        update_status("Нет изменений для сохранения.")
        return

    backup_filepath = xliff_filepath + BACKUP_SUFFIX
    try:
        if os.path.exists(xliff_filepath):
             print(f"Создание резервной копии: {os.path.basename(backup_filepath)}")
             shutil.copy2(xliff_filepath, backup_filepath)

        print(f"Сохранение изменений в: {xliff_filepath}...")
        # Используем BytesIO для правильной записи UTF-8 с декларацией
        output_buffer = io.BytesIO()
        xliff_tree.write(
            output_buffer,
            pretty_print=True,
            encoding='utf-8',       # Пишем байты UTF-8
            xml_declaration=True,
        )
        xml_content = output_buffer.getvalue()
        with open(xliff_filepath, "wb") as f:
            f.write(xml_content)

        is_dirty = False # Сбрасываем флаг ПОСЛЕ успешной записи
        if save_button: save_button.configure(state=tk.DISABLED)
        update_status(f"Файл сохранен: {os.path.basename(xliff_filepath)}")
        print("Файл успешно сохранен, is_dirty сброшен.")

        # Сбрасываем флаг модификации редактора
        inner_widget = _get_inner_text_widget()
        if inner_widget:
             try: inner_widget.edit_modified(False)
             except tk.TclError: pass

    except Exception as e:
        messagebox.showerror("Ошибка сохранения", f"Не удалось сохранить XLIFF файл:\n{e}\n{traceback.format_exc()}")
        update_status("Ошибка сохранения файла.")


def set_editor_text_highlighted(editor_wrapper, text):
    """Вставляет текст в редактор с подсветкой."""
    target_widget = _get_inner_text_widget()
    if not target_widget:
        print("Ошибка: Внутренний виджет редактора не найден.")
        if editor_wrapper: # Попытка вставить в обертку
             try:
                 editor_wrapper.configure(state=tk.NORMAL)
                 editor_wrapper.delete("1.0", tk.END)
                 editor_wrapper.insert("1.0", text)
                 editor_wrapper.edit_modified(False)
                 editor_wrapper.configure(state=(tk.NORMAL if xliff_tree else tk.DISABLED))
             except Exception as e: print(f"Ошибка вставки в обертку: {e}")
        return

    try:
        # Включаем виджеты для модификации
        editor_wrapper.configure(state=tk.NORMAL)
        target_widget.configure(state=tk.NORMAL)

        target_widget.delete("1.0", tk.END) # Очищаем

        # Подсветка или обычный текст
        if not PYGMENTS_AVAILABLE or TEXT_HIGHLIGHT_CONFIG["lexer"] is None or current_mode != 'markup':
            target_widget.insert("1.0", text)
        else:
            # Применяем подсветку (код остался тем же)
            for tag in target_widget.tag_names():
                if tag.startswith("Token_"):
                    try: target_widget.tag_delete(tag)
                    except tk.TclError: pass
            for token_type_key, config in TEXT_HIGHLIGHT_CONFIG["tags"].items():
                tag_name = "Token_" + str(token_type_key).replace(".", "_").replace("'", "")
                try: target_widget.tag_config(tag_name, **config)
                except tk.TclError: pass
            lexer = TEXT_HIGHLIGHT_CONFIG["lexer"]
            try:
                tokens = lex(text, lexer)
                for token_type, token_value in tokens:
                    tag_config_key = None
                    temp_type = token_type
                    while temp_type is not None:
                        found = False
                        for config_key_obj in TEXT_HIGHLIGHT_CONFIG["tags"].keys():
                            if str(temp_type) == str(config_key_obj):
                                tag_config_key = config_key_obj; found = True; break
                        if found: break
                        temp_type = getattr(temp_type, 'parent', None)
                    if tag_config_key:
                        tag_name = "Token_" + str(tag_config_key).replace(".", "_").replace("'", "")
                        target_widget.insert(tk.END, token_value, tag_name)
                    else:
                        target_widget.insert(tk.END, token_value)
            except Exception as e:
                print(f"{Fore.RED}Ошибка подсветки синтаксиса: {e}{Style.RESET_ALL}")
                target_widget.delete("1.0", tk.END)
                target_widget.insert("1.0", text) # Вставляем без подсветки

        # Сбрасываем флаг модификации ПОСЛЕ вставки
        target_widget.edit_modified(False)

        # Устанавливаем конечное состояние виджетов
        final_state = tk.NORMAL if xliff_tree else tk.DISABLED
        editor_wrapper.configure(state=final_state)
        target_widget.configure(state=final_state)

    except tk.TclError as e:
        print(f"Ошибка Tcl при установке текста редактора: {e}")
    except Exception as e:
        print(f"Общая ошибка при установке текста редактора: {e}")
        traceback.print_exc()


# --- Функция автоматического перевода --- <--- ДОБАВЛЕНО
def translate_current_page():
    """Переводит <source> для всех <trans-unit> на текущей странице."""
    global current_page_units_map, is_dirty, save_button, untranslated_ids
    global translate_button, status_label, all_trans_units

    if not TRANSLATION_AVAILABLE:
        messagebox.showerror("Ошибка", "Функция перевода недоступна. Установите 'deep-translator'.")
        return
    if not current_page_units_map:
        messagebox.showinfo("Информация", "Нет строк для перевода на текущей странице.")
        return
    if not messagebox.askyesno("Подтверждение перевода",
                               f"Перевести {len(current_page_units_map)} строк на стр. {current_page_index + 1} "
                               f"({SOURCE_LANG} -> {TARGET_LANG})?\n\n"
                               f"Существующие переводы будут ЗАМЕНЕНЫ.\n"
                               f"Сервис: {DEFAULT_TRANSLATOR_SERVICE}"):
        return

    print(f"Начало перевода страницы {current_page_index + 1}...")
    if translate_button: translate_button.configure(state=tk.DISABLED) # Выключаем кнопку на время
    original_status = status_label.cget("text") if status_label else "Перевод..."
    update_status(f"Перевод стр. {current_page_index + 1} (0%)...")

    translated_count = 0; error_count = 0; updated_ids_on_page = set(); any_change_made_in_memory = False
    total_units = len(current_page_units_map); units_processed = 0

    # Инициализация переводчика
    try:
        if DEFAULT_TRANSLATOR_SERVICE == "Google":
            translator = GoogleTranslator(source=SOURCE_LANG, target=TARGET_LANG)
        elif DEFAULT_TRANSLATOR_SERVICE == "MyMemory":
            translator = MyMemoryTranslator(source=SOURCE_LANG, target=TARGET_LANG)
        else: raise ValueError(f"Неизвестный сервис: {DEFAULT_TRANSLATOR_SERVICE}")
    except Exception as e:
         messagebox.showerror("Ошибка инициализации переводчика", f"Не удалось создать переводчик:\n{e}")
         update_navigation_buttons_state() # Пытаемся включить кнопку обратно
         update_status(original_status)
         return

    # Карта ID -> unit для быстрого доступа к актуальным элементам
    id_to_unit_map = {unit.get("id"): unit for unit in all_trans_units if unit.get("id")}

    # Итерация по ID юнитов ТЕКУЩЕЙ страницы
    for unit_id in list(current_page_units_map.keys()): # list() для безопасной итерации
        unit = id_to_unit_map.get(unit_id) # Берем актуальный unit из общей карты
        if unit is None: units_processed += 1; continue # Пропускаем, если unit не найден

        source_node = unit.find("xliff:source", namespaces=LXML_NSMAP)
        source_text = source_node.xpath("string(.)") if source_node is not None else None

        if not source_text:
            print(f"  - Пропуск ID {unit_id}: пустой <source>.")
            units_processed += 1; continue

        target_node = unit.find("xliff:target", namespaces=LXML_NSMAP)
        original_target_text = target_node.xpath("string(.)") if target_node is not None else ""

        try:
            # ---> Выполняем перевод <---
            print(f"  - Перевод ID {unit_id} ({units_processed + 1}/{total_units})...")
            translated_text = translator.translate(source_text)
            time.sleep(TRANSLATION_DELAY_SECONDS) # Задержка

            if translated_text and translated_text.strip():
                translated_text = translated_text.strip()
                # Создаем <target>, если его нет
                if target_node is None:
                    target_node = ET.Element(f"{{{LXML_NSMAP['xliff']}}}target")
                    # Вставляем после <source> или <note>
                    note_node = unit.find("xliff:note", namespaces=LXML_NSMAP)
                    insert_point = source_node if source_node is not None else note_node
                    if insert_point is not None: insert_point.addnext(target_node)
                    else: # Если нет ни source, ни note, ищем последний элемент
                         last_element = unit.xpath("./*[last()]")
                         if last_element: last_element[0].addnext(target_node)
                         else: unit.append(target_node) # Вставляем в конец, если unit пуст

                # Обновляем текст, если он изменился
                if original_target_text != translated_text:
                    target_node.clear() # Очищаем содержимое и атрибуты
                    target_node.text = translated_text
                    # Опционально: снять 'approved' при автопереводе
                    if 'approved' in target_node.attrib: del target_node.attrib['approved']
                    any_change_made_in_memory = True
                    updated_ids_on_page.add(unit_id)
                translated_count += 1
            else:
                print(f"  - {Fore.YELLOW}Предупреждение: Пустой перевод для ID {unit_id}.{Style.RESET_ALL}")
                error_count += 1 # Считаем пустой перевод ошибкой
        except Exception as e:
            print(f"  - {Fore.RED}Ошибка перевода ID {unit_id}: {e}{Style.RESET_ALL}")
            error_count += 1
            # Пауза при ошибках сети/лимитах
            if "TooManyRequestsError" in str(e) or "timed out" in str(e):
                 print(f"{Fore.YELLOW}    -> Пауза из-за ошибки сети/лимита...{Style.RESET_ALL}")
                 time.sleep(5)

        units_processed += 1
        progress = int((units_processed / total_units) * 100)
        update_status(f"Перевод стр. {current_page_index + 1} ({progress}%)...")

    # --- Обновление после перевода ---
    final_status = f"Перевод завершен. Успешно: {translated_count}, Ошибки/Пропущено: {error_count}."
    print(final_status)
    update_status(final_status)

    if any_change_made_in_memory:
        print("Изменения внесены в память.")
        is_dirty = True # Устанавливаем глобальный флаг
        if save_button: save_button.configure(state=tk.NORMAL)

        # Обновление списка непереведенных ID
        ids_to_remove = set()
        for unit_id in updated_ids_on_page:
            unit = id_to_unit_map.get(unit_id) # Получаем обновленный unit
            if unit:
                target = unit.find("xliff:target", namespaces=LXML_NSMAP)
                # Считаем переведенным, если есть текст в target
                if target is not None and target.xpath("normalize-space(.)"):
                    ids_to_remove.add(unit_id)

        if ids_to_remove:
            original_count = len(untranslated_ids)
            untranslated_ids = [uid for uid in untranslated_ids if uid not in ids_to_remove]
            removed_count = original_count - len(untranslated_ids)
            print(f"Удалено {removed_count} ID из списка непереведенных после перевода.")

        # Обновляем отображение в редакторе
        print("Обновление редактора...")
        if current_mode == 'markup': display_markup_page()
        elif current_mode == 'edit': display_edit_page()

        # Сбрасываем флаг модификации редактора ПОСЛЕ обновления
        inner_widget = _get_inner_text_widget()
        if inner_widget:
            try: inner_widget.edit_modified(False)
            except tk.TclError: pass

        # Обновляем счетчик страниц и навигацию
        update_navigation_buttons_state()
        num_pages = math.ceil(len(untranslated_ids) / items_per_page) if untranslated_ids else 1
        if page_label: page_label.configure(text=f"Страница: {current_page_index + 1} / {num_pages} (неперев.)")
        if page_var: page_var.set(str(current_page_index + 1))
    else:
        print("Не было внесено изменений в память.")

    # Обновляем состояние кнопок (включая кнопку перевода)
    update_navigation_buttons_state()
# --- /Функция автоматического перевода --- <--- КОНЕЦ ДОБАВЛЕННОГО


# --- Функции отображения страниц ---

def display_markup_page():
    """Отображает текущую страницу в режиме разметки XML."""
    global current_page_units_map, editor_textbox, page_label, page_var, current_page_index
    global untranslated_ids, items_per_page, all_trans_units # Добавлены зависимости
    if editor_textbox is None: return

    editor_textbox.configure(state=tk.NORMAL)
    current_page_units_map.clear() # Очищаем карту ПЕРЕД заполнением

    if not untranslated_ids:
        if page_label: page_label.configure(text="Страница: - / -")
        if page_var: page_var.set("-")
        set_editor_text_highlighted(editor_textbox, "<нет непереведенных строк для отображения>")
        # editor_textbox.configure(state=tk.DISABLED) # set_editor_text_highlighted управляет этим
        update_navigation_buttons_state() # Обновляем кнопки
        return

    num_pages = math.ceil(len(untranslated_ids) / items_per_page)
    current_page_index = max(0, min(current_page_index, num_pages - 1))
    if page_label: page_label.configure(text=f"Страница: {current_page_index + 1} / {num_pages} (неперев.)")
    if page_var: page_var.set(str(current_page_index + 1))

    start_idx = current_page_index * items_per_page
    end_idx = min(start_idx + items_per_page, len(untranslated_ids))
    page_ids = untranslated_ids[start_idx:end_idx]

    page_xml_parts = []
    id_to_unit_map = {unit.get("id"): unit for unit in all_trans_units if unit.get("id")}

    for unit_id in page_ids:
        unit = id_to_unit_map.get(unit_id)
        if unit is not None:
            current_page_units_map[unit_id] = unit # Заполняем карту
            try:
                # ---> ИСПРАВЛЕНО: Используем ET.tostring с encoding='unicode' <---
                xml_string = ET.tostring(
                    unit,
                    encoding='unicode',      # Получаем строку Python (str)
                    pretty_print=True,       # Форматируем
                    xml_declaration=False    # Не нужна декларация для фрагмента
                ).strip()
                page_xml_parts.append(xml_string)
                # -----------------------------------------------------------------
            except Exception as e:
                print(f"{Fore.RED}Ошибка сериализации <trans-unit> ID '{unit_id}': {e}{Style.RESET_ALL}")
                traceback.print_exc() # Печатаем стек для отладки
                page_xml_parts.append(f"<!-- Ошибка отображения unit ID: {unit_id} ({e}) -->")
        else:
            print(f"{Fore.YELLOW}Предупреждение: Не найден <trans-unit> для ID '{unit_id}'.{Style.RESET_ALL}")

    full_xml_block = "\n\n".join(page_xml_parts) # Разделяем юниты пустой строкой
    set_editor_text_highlighted(editor_textbox, full_xml_block)
    editor_textbox.yview_moveto(0.0) # Прокрутка вверх
    update_navigation_buttons_state() # Обновляем кнопки ПОСЛЕ заполнения карты


def display_edit_page():
    """Отображает текущую страницу в режиме простого текста."""
    global current_page_units_map, editor_textbox, page_label, page_var, current_page_index
    global untranslated_ids, items_per_page, all_trans_units # Добавлены зависимости
    if editor_textbox is None: return

    editor_textbox.configure(state=tk.NORMAL)
    current_page_units_map.clear() # Очищаем карту ПЕРЕД заполнением
    target_widget = _get_inner_text_widget()

    # Убираем теги подсветки
    if PYGMENTS_AVAILABLE and target_widget:
        for tag in target_widget.tag_names():
            if tag.startswith("Token_"):
                 try: target_widget.tag_delete(tag)
                 except tk.TclError: pass

    if not untranslated_ids:
        if page_label: page_label.configure(text="Страница: - / -")
        if page_var: page_var.set("-")
        set_editor_text_highlighted(editor_textbox, "<нет непереведенных строк для отображения>")
        # editor_textbox.configure(state=tk.DISABLED) # set_editor_text_highlighted управляет этим
        update_navigation_buttons_state() # Обновляем кнопки
        return

    num_pages = math.ceil(len(untranslated_ids) / items_per_page)
    current_page_index = max(0, min(current_page_index, num_pages - 1))
    if page_label: page_label.configure(text=f"Страница: {current_page_index + 1} / {num_pages} (неперев.)")
    if page_var: page_var.set(str(current_page_index + 1))

    start_idx = current_page_index * items_per_page
    end_idx = min(start_idx + items_per_page, len(untranslated_ids))
    page_ids = untranslated_ids[start_idx:end_idx]

    text_content = []
    id_to_unit_map = {unit.get("id"): unit for unit in all_trans_units if unit.get("id")}

    for unit_id in page_ids:
        unit = id_to_unit_map.get(unit_id)
        if unit is not None:
            current_page_units_map[unit_id] = unit # Заполняем карту
            source_text = unit.xpath("string(./xliff:source)", namespaces=LXML_NSMAP) or ""
            target_node = unit.find("xliff:target", namespaces=LXML_NSMAP)
            # Используем string() для получения только текста из target
            target_text = target_node.xpath("string(.)") if target_node is not None else ""

            text_content.append(f"ID: {unit_id}")
            text_content.append(f"SOURCE: {source_text}")
            text_content.append(f"TARGET: {target_text}")
            text_content.append('-'*30)
        else:
            print(f"{Fore.YELLOW}Предупреждение: Не найден <trans-unit> для ID '{unit_id}'.{Style.RESET_ALL}")

    full_text_block = "\n".join(text_content)
    set_editor_text_highlighted(editor_textbox, full_text_block)
    editor_textbox.yview_moveto(0.0) # Прокрутка вверх
    update_navigation_buttons_state() # Обновляем кнопки ПОСЛЕ заполнения карты


# --- Функции сохранения страниц ---

def save_markup_page_data(force_check=False):
    """Парсит XML из редактора (разметка) и обновляет lxml В ПАМЯТИ."""
    global current_page_units_map, is_dirty, editor_textbox, save_button, untranslated_ids, all_trans_units
    inner_widget = _get_inner_text_widget()
    if not current_page_units_map or current_mode != 'markup': return True

    textbox_modified = False
    if inner_widget:
         try: textbox_modified = inner_widget.edit_modified()
         except tk.TclError: pass
    if not force_check and not textbox_modified: return True

    edited_xml_string = editor_textbox.get("1.0", "end-1c").strip() if editor_textbox else ""
    if not edited_xml_string: return True

    xml_to_parse = f"<root xmlns:xliff='{LXML_NSMAP['xliff']}'>{edited_xml_string}</root>"
    updated_ids_on_page = set(); any_change_made_in_memory = False

    try:
        parser = ET.XMLParser(remove_blank_text=False, strip_cdata=False, resolve_entities=False)
        edited_root = ET.fromstring(xml_to_parse, parser=parser)
        edited_units = edited_root.xpath("./xliff:trans-unit", namespaces=LXML_NSMAP)
        if not edited_units and edited_xml_string.strip():
             raise ValueError("Не найдено <trans-unit> в отредактированном тексте.")

        found_ids_in_editor = set()
        id_to_edited_unit = {}
        for edited_unit in edited_units:
            unit_id = edited_unit.get("id")
            if not unit_id: continue
            found_ids_in_editor.add(unit_id)
            id_to_edited_unit[unit_id] = edited_unit

        id_to_original_unit_map = {unit.get("id"): unit for unit in all_trans_units if unit.get("id")}

        for unit_id in current_page_units_map.keys():
            original_unit = id_to_original_unit_map.get(unit_id)
            edited_unit = id_to_edited_unit.get(unit_id)
            if original_unit is None or edited_unit is None: continue

            original_target_node = original_unit.find("xliff:target", namespaces=LXML_NSMAP)
            edited_target_node = edited_unit.find("xliff:target", namespaces=LXML_NSMAP)
            original_target_str = ET.tostring(original_target_node, encoding='unicode') if original_target_node is not None else "<target/>"
            edited_target_str = ET.tostring(edited_target_node, encoding='unicode') if edited_target_node is not None else "<target/>"

            if original_target_str != edited_target_str:
                if original_target_node is not None: original_unit.remove(original_target_node)
                if edited_target_node is not None:
                    source_node = original_unit.find("xliff:source", namespaces=LXML_NSMAP)
                    note_node = original_unit.find("xliff:note", namespaces=LXML_NSMAP)
                    insert_point = source_node if source_node is not None else note_node
                    if insert_point is not None: insert_point.addnext(edited_target_node)
                    else:
                        last_element = original_unit.xpath("./*[last()]")
                        if last_element: last_element[0].addnext(edited_target_node)
                        else: original_unit.append(edited_target_node)
                any_change_made_in_memory = True
                updated_ids_on_page.add(unit_id)

        new_ids_in_editor = found_ids_in_editor - set(current_page_units_map.keys())
        if new_ids_in_editor:
             print(f"{Fore.YELLOW}Предупреждение: ID из редактора не найдены на стр.: {', '.join(new_ids_in_editor)}.{Style.RESET_ALL}")

        if any_change_made_in_memory:
            print(f"Обновлено {len(updated_ids_on_page)} строк в памяти (разметка).")
            is_dirty = True
            if save_button: save_button.configure(state=tk.NORMAL)

            ids_to_remove = set(); ids_to_add = set()
            for unit_id in updated_ids_on_page:
                 unit = id_to_original_unit_map.get(unit_id)
                 if unit:
                     target = unit.find("xliff:target", namespaces=LXML_NSMAP)
                     is_approved = target is not None and target.get('approved') == 'yes'
                     has_text = target is not None and target.xpath("normalize-space(.)")
                     if has_text or is_approved:
                         if unit_id in untranslated_ids: ids_to_remove.add(unit_id)
                     else:
                         if unit_id not in untranslated_ids: ids_to_add.add(unit_id)
            if ids_to_remove:
                 print(f"Удаление {len(ids_to_remove)} ID из непереведенных...")
                 untranslated_ids = [uid for uid in untranslated_ids if uid not in ids_to_remove]
            if ids_to_add:
                 print(f"Добавление {len(ids_to_add)} ID в непереведенные...")
                 for uid in ids_to_add:
                     if uid not in untranslated_ids: untranslated_ids.append(uid)

            update_navigation_buttons_state()
            num_pages = math.ceil(len(untranslated_ids) / items_per_page) if untranslated_ids else 1
            if page_label: page_label.configure(text=f"Страница: {current_page_index + 1} / {num_pages} (неперев.)")
        else:
            print("Изменений на странице не обнаружено.")
        return True
    except ET.XMLSyntaxError as e:
        messagebox.showerror("Ошибка парсинга XML", f"Не удалось разобрать XML из редактора:\n{e}")
        return False
    except ValueError as ve:
        messagebox.showerror("Ошибка данных", f"Ошибка в структуре отредакт. текста:\n{ve}")
        return False
    except Exception as e:
        messagebox.showerror("Ошибка обновления", f"Ошибка при обновлении данных (разметка):\n{e}\n{traceback.format_exc()}")
        return False


def save_edit_page_data(force_check=False):
    """Сохраняет изменения из редактора (текст) В ПАМЯТЬ."""
    global current_page_units_map, is_dirty, editor_textbox, save_button, untranslated_ids, all_trans_units
    inner_widget = _get_inner_text_widget()
    if not current_page_units_map or current_mode != 'edit': return True

    textbox_modified = False
    if inner_widget:
        try: textbox_modified = inner_widget.edit_modified()
        except tk.TclError: pass
    if not force_check and not textbox_modified: return True

    edited_text = editor_textbox.get("1.0", "end-1c") if editor_textbox else ""
    lines = edited_text.split('\n')
    parsed_targets = {}; current_id = None; current_target_lines = []; in_target_section = False

    try: # Парсинг текста из редактора
        for line_number, line in enumerate(lines):
            line_strip = line.strip()
            if line.startswith("ID: "):
                if current_id is not None: parsed_targets[current_id] = "\n".join(current_target_lines).strip()
                current_id = line[4:].strip()
                if not current_id: current_id = None
                current_target_lines = []; in_target_section = False
            elif line.startswith("SOURCE: "): in_target_section = False
            elif line.startswith("TARGET: "):
                if current_id is None: continue
                in_target_section = True
                current_target_lines.append(line[8:])
            elif line_strip == '-'*30:
                if current_id is not None: parsed_targets[current_id] = "\n".join(current_target_lines).strip()
                current_id = None; current_target_lines = []; in_target_section = False
            elif in_target_section:
                 if current_id is None: continue
                 current_target_lines.append(line)
        if current_id is not None: parsed_targets[current_id] = "\n".join(current_target_lines).strip()
    except Exception as e:
        messagebox.showerror("Ошибка парсинга текста", f"Ошибка разбора текста редактора:\n{e}\n{traceback.format_exc()}")
        return False

    # Применение изменений к lxml
    updated_ids_on_page = set(); any_change_made_in_memory = False
    id_to_original_unit_map = {unit.get("id"): unit for unit in all_trans_units if unit.get("id")}

    for unit_id in current_page_units_map.keys(): # Итерируем по ID с текущей страницы
        if unit_id in parsed_targets: # Если для этого ID есть данные в редакторе
            original_unit = id_to_original_unit_map.get(unit_id)
            if original_unit is None: continue
            new_target_text = parsed_targets[unit_id]
            target_node = original_unit.find("xliff:target", namespaces=LXML_NSMAP)
            # Сравниваем только текст
            current_target_text = target_node.xpath("string(.)") if target_node is not None else ""

            if current_target_text != new_target_text:
                 if target_node is None:
                     target_node = ET.Element(f"{{{LXML_NSMAP['xliff']}}}target")
                     source_node = original_unit.find("xliff:source", namespaces=LXML_NSMAP)
                     note_node = original_unit.find("xliff:note", namespaces=LXML_NSMAP)
                     insert_point = source_node if source_node is not None else note_node
                     if insert_point is not None: insert_point.addnext(target_node)
                     else: original_unit.append(target_node)
                 target_node.clear()
                 target_node.text = new_target_text if new_target_text else None
                 if 'approved' in target_node.attrib: del target_node.attrib['approved']
                 any_change_made_in_memory = True; updated_ids_on_page.add(unit_id)

    ids_only_in_editor = set(parsed_targets.keys()) - set(current_page_units_map.keys())
    if ids_only_in_editor:
        print(f"{Fore.YELLOW}Предупреждение: ID найдены в редакторе, но отсутствовали на стр.: {', '.join(ids_only_in_editor)}.{Style.RESET_ALL}")

    if any_change_made_in_memory:
        print(f"Обновлено {len(updated_ids_on_page)} строк в памяти (редактирование).")
        is_dirty = True
        if save_button: save_button.configure(state=tk.NORMAL)
        # Обновление untranslated_ids (логика та же, что в markup)
        ids_to_remove = set(); ids_to_add = set()
        for unit_id in updated_ids_on_page:
            unit = id_to_original_unit_map.get(unit_id)
            if unit:
                target = unit.find("xliff:target", namespaces=LXML_NSMAP)
                is_approved = target is not None and target.get('approved') == 'yes'
                has_text = target is not None and target.xpath("normalize-space(.)")
                if has_text or is_approved:
                    if unit_id in untranslated_ids: ids_to_remove.add(unit_id)
                else:
                    if unit_id not in untranslated_ids: ids_to_add.add(unit_id)
        if ids_to_remove:
            print(f"Удаление {len(ids_to_remove)} ID из непереведенных...")
            untranslated_ids = [uid for uid in untranslated_ids if uid not in ids_to_remove]
        if ids_to_add:
            print(f"Добавление {len(ids_to_add)} ID в непереведенные...")
            for uid in ids_to_add:
                if uid not in untranslated_ids: untranslated_ids.append(uid)
        update_navigation_buttons_state()
        num_pages = math.ceil(len(untranslated_ids) / items_per_page) if untranslated_ids else 1
        if page_label: page_label.configure(text=f"Страница: {current_page_index + 1} / {num_pages} (неперев.)")
    else:
        print("Изменений на странице не обнаружено.")
    return True


# --- Создание основного окна и виджетов ---
def create_main_window():
    """Создает и настраивает главное окно и виджеты."""
    global main_window, editor_textbox, prev_button, next_button, page_label, page_var
    global page_entry, go_button, page_size_var, page_size_entry, page_size_button
    global status_label, save_button, open_button, markup_mode_button, edit_mode_button
    global translate_button # <--- Добавлено

    main_window = ctk.CTk()
    main_window.title("XLIFF Paged Editor")
    main_window.geometry("1000x700") # Увеличим немного

    # --- Top Frame ---
    top_frame = ctk.CTkFrame(main_window, fg_color="transparent")
    top_frame.pack(side=tk.TOP, fill=tk.X, padx=10, pady=(10, 5))
    # Frame для кнопок слева
    left_buttons_frame = ctk.CTkFrame(top_frame, fg_color="transparent")
    left_buttons_frame.pack(side=tk.LEFT, padx=(0, 10))
    markup_mode_button = ctk.CTkButton(left_buttons_frame, text="Режим разметки", command=lambda: set_mode('markup'), width=140)
    markup_mode_button.pack(side=tk.LEFT, padx=(0, 5))
    edit_mode_button = ctk.CTkButton(left_buttons_frame, text="Режим редактирования", command=lambda: set_mode('edit'), width=160)
    edit_mode_button.pack(side=tk.LEFT, padx=(0, 10))
    # Кнопка перевода <--- ДОБАВЛЕНО
    translate_button = ctk.CTkButton(left_buttons_frame, text="Перевести страницу", command=translate_current_page, width=150)
    translate_button.pack(side=tk.LEFT, padx=(0, 5))
    translate_button.configure(state=tk.DISABLED) # Изначально выключена
    if not TRANSLATION_AVAILABLE: translate_button.configure(text="Перевод (n/a)")
    # Кнопка открытия справа
    open_button = ctk.CTkButton(top_frame, text="Открыть XLIFF...", command=load_xliff, width=120)
    open_button.pack(side=tk.RIGHT)

    # --- Bottom Frame (Status and Save) ---
    bottom_frame_outer = ctk.CTkFrame(main_window)
    bottom_frame_outer.pack(side=tk.BOTTOM, fill=tk.X, padx=0, pady=0)
    bottom_frame_outer.grid_columnconfigure(0, weight=1)
    status_label = ctk.CTkLabel(bottom_frame_outer, text="Загрузите XLIFF файл...", anchor=tk.W)
    status_label.grid(row=0, column=0, padx=(10, 5), pady=5, sticky="ew")
    save_button = ctk.CTkButton(bottom_frame_outer, text="Сохранить XLIFF", command=save_xliff, width=120)
    save_button.grid(row=0, column=1, padx=(5, 10), pady=5, sticky="e")
    save_button.configure(state=tk.DISABLED)

    # --- Navigation Frame ---
    nav_frame = ctk.CTkFrame(main_window, fg_color="transparent")
    nav_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=(0, 5))
    nav_content_frame = ctk.CTkFrame(nav_frame, fg_color="transparent")
    nav_content_frame.pack(anchor=tk.CENTER)
    _nav_font = ctk.CTkFont(size=11)
    prev_button = ctk.CTkButton(nav_content_frame, text="<< Пред.", command=go_to_prev_page, width=70, font=_nav_font)
    prev_button.pack(side=tk.LEFT, padx=(0, 2))
    page_label = ctk.CTkLabel(nav_content_frame, text="Страница: - / -", width=120, font=_nav_font, anchor=tk.CENTER)
    page_label.pack(side=tk.LEFT, padx=2)
    page_var = tk.StringVar()
    page_entry = ctk.CTkEntry(nav_content_frame, textvariable=page_var, width=45, justify=tk.CENTER, font=_nav_font)
    page_entry.pack(side=tk.LEFT, padx=1); page_entry.bind("<Return>", go_to_page)
    go_button = ctk.CTkButton(nav_content_frame, text="Перейти", command=go_to_page, width=60, font=_nav_font)
    go_button.pack(side=tk.LEFT, padx=2)
    next_button = ctk.CTkButton(nav_content_frame, text="След. >>", command=go_to_next_page, width=70, font=_nav_font)
    next_button.pack(side=tk.LEFT, padx=(2, 15))
    page_size_label = ctk.CTkLabel(nav_content_frame, text="Строк:", font=_nav_font)
    page_size_label.pack(side=tk.LEFT, padx=(5, 1))
    page_size_var = tk.StringVar(value=str(items_per_page))
    page_size_entry = ctk.CTkEntry(nav_content_frame, textvariable=page_size_var, width=45, justify=tk.CENTER, font=_nav_font)
    page_size_entry.pack(side=tk.LEFT, padx=(1, 2)); page_size_entry.bind("<Return>", update_page_size)
    page_size_button = ctk.CTkButton(nav_content_frame, text="Прим.", command=update_page_size, width=50, font=_nav_font)
    page_size_button.pack(side=tk.LEFT, padx=2)

    # --- Text Editor ---
    editor_frame = ctk.CTkFrame(main_window, fg_color="transparent")
    editor_frame.pack(expand=True, fill=tk.BOTH, padx=10, pady=(0, 5))
    editor_font = ctk.CTkFont(family="Consolas", size=11)
    editor_textbox = ctk.CTkTextbox(
        editor_frame,
        wrap=tk.NONE, # Начнем без переноса, режим разметки включит WORD
        undo=True, font=editor_font, border_width=1, padx=5, pady=5
    )
    editor_scrollbar_y = ctk.CTkScrollbar(editor_frame, command=editor_textbox.yview)
    editor_scrollbar_y.pack(side=tk.RIGHT, fill=tk.Y)
    editor_scrollbar_x = ctk.CTkScrollbar(editor_frame, command=editor_textbox.xview, orientation="horizontal")
    editor_scrollbar_x.pack(side=tk.BOTTOM, fill=tk.X) # Скроллбар X для режима без переноса
    editor_textbox.configure(yscrollcommand=editor_scrollbar_y.set, xscrollcommand=editor_scrollbar_x.set)
    editor_textbox.pack(expand=True, fill=tk.BOTH, side=tk.LEFT)

    # --- Внутренний виджет и биндинги ---
    text_widget = _get_inner_text_widget()
    if text_widget:
        context_menu = tk.Menu(text_widget, tearoff=0)
        context_menu.add_command(label="Вырезать", command=lambda: cut_text(None))
        context_menu.add_command(label="Копировать", command=lambda: copy_text(None))
        context_menu.add_command(label="Вставить", command=lambda: paste_text(None))
        context_menu.add_separator()
        context_menu.add_command(label="Выделить все", command=lambda: select_all_text(None))
        def show_context_menu(event):
            can_modify = xliff_tree is not None; has_clipboard = False; has_selection = False; is_empty = True
            try: has_clipboard = bool(main_window.clipboard_get())
            except: pass
            try: has_selection = bool(text_widget.tag_ranges(tk.SEL))
            except: pass
            try: is_empty = not text_widget.get("1.0", tk.END + "-1c").strip()
            except: pass
            context_menu.entryconfigure("Вырезать", state=tk.NORMAL if can_modify and has_selection else tk.DISABLED)
            context_menu.entryconfigure("Копировать", state=tk.NORMAL if has_selection else tk.DISABLED)
            context_menu.entryconfigure("Вставить", state=tk.NORMAL if can_modify and has_clipboard else tk.DISABLED)
            context_menu.entryconfigure("Выделить все", state=tk.NORMAL if not is_empty else tk.DISABLED)
            if (can_modify and has_selection) or has_selection or (can_modify and has_clipboard) or not is_empty:
                context_menu.tk_popup(event.x_root, event.y_root)
        text_widget.bind("<Button-3>", show_context_menu)
        text_widget.bind("<Button-2>", show_context_menu)
        # Используем bind_all для перехвата стандартных комбинаций у CTkTextbox
        text_widget.bind_all("<Control-a>", select_all_text); text_widget.bind_all("<Control-A>", select_all_text)
        text_widget.bind_all("<Control-x>", cut_text); text_widget.bind_all("<Control-X>", cut_text)
        text_widget.bind_all("<Control-c>", copy_text); text_widget.bind_all("<Control-C>", copy_text)
        text_widget.bind_all("<Control-v>", paste_text); text_widget.bind_all("<Control-V>", paste_text)
        main_window.bind_all("<Control-s>", lambda event: save_xliff()); main_window.bind_all("<Control-S>", lambda event: save_xliff())
        text_widget.bind("<<Modified>>", handle_text_modification) # Отслеживание изменений
    else:
        print(f"{Fore.RED}Критическая ошибка: Не удалось получить внутренний tk.Text!{Style.RESET_ALL}")

    # --- Initial State ---
    reset_state()
    set_mode(DEFAULT_MODE, force_update=True) # Устанавливаем начальный режим
    main_window.protocol("WM_DELETE_WINDOW", on_closing) # Обработчик закрытия
    return main_window

# --- Управление режимами ---
def set_mode(mode, force_update=False):
    """Переключает режим редактора."""
    global current_mode, markup_mode_button, edit_mode_button, editor_textbox, status_label
    if not xliff_tree and not force_update:
        # Обновляем только кнопки, если файл не загружен
        if mode == 'markup':
             if markup_mode_button: markup_mode_button.configure(state=tk.DISABLED)
             if edit_mode_button: edit_mode_button.configure(state=tk.NORMAL)
        elif mode == 'edit':
             if markup_mode_button: markup_mode_button.configure(state=tk.NORMAL)
             if edit_mode_button: edit_mode_button.configure(state=tk.DISABLED)
        current_mode = mode # Запоминаем выбранный режим
        return
    if not force_update and mode == current_mode: return # Режим уже установлен

    # Пытаемся сохранить перед сменой режима
    if not force_update:
        if not save_current_page_data_if_dirty(prompt_save=True):
            print("Смена режима отменена.")
            return

    print(f"Установка режима: {mode}")
    previous_mode = current_mode
    current_mode = mode

    if editor_textbox:
        if mode == 'markup':
            if markup_mode_button: markup_mode_button.configure(state=tk.DISABLED)
            if edit_mode_button: edit_mode_button.configure(state=tk.NORMAL)
            editor_textbox.configure(wrap=tk.WORD) # Включаем перенос
            update_status("Режим: Разметка XML")
        elif mode == 'edit':
            if markup_mode_button: markup_mode_button.configure(state=tk.NORMAL)
            if edit_mode_button: edit_mode_button.configure(state=tk.DISABLED)
            editor_textbox.configure(wrap=tk.NONE) # Выключаем перенос
            update_status("Режим: Редактирование текста")
        else:
            current_mode = previous_mode
            print(f"{Fore.RED}Ошибка: Неизвестный режим '{mode}'{Style.RESET_ALL}")
            return

        # Перерисовываем содержимое, если режим изменился или нужно принудительно
        if mode != previous_mode or force_update:
            if mode == 'markup': display_markup_page()
            elif mode == 'edit': display_edit_page()

        set_focus_on_editor() # Устанавливаем фокус после смены режима/обновления
    else: # При инициализации, когда editor_textbox еще None
         if mode == 'markup':
             if markup_mode_button: markup_mode_button.configure(state=tk.DISABLED)
             if edit_mode_button: edit_mode_button.configure(state=tk.NORMAL)
         elif mode == 'edit':
             if markup_mode_button: markup_mode_button.configure(state=tk.NORMAL)
             if edit_mode_button: edit_mode_button.configure(state=tk.DISABLED)


def handle_text_modification(event=None):
    """Обработчик события <<Modified>> от внутреннего tk.Text."""
    # Этот обработчик в ИСХОДНОЙ версии использовался для установки is_dirty
    # Оставим его таким же для совместимости с оригинальной логикой,
    # хотя более строгая проверка делается в save_..._page_data
    global is_dirty, save_button
    inner_widget = _get_inner_text_widget()
    if inner_widget:
        try:
            if inner_widget.edit_modified():
                 if not is_dirty: # Ставим флаг только один раз
                     is_dirty = True
                     print("* Обнаружено изменение текста, установлен флаг is_dirty.") # Debug
                     if save_button: save_button.configure(state=tk.NORMAL)
        except tk.TclError: pass # Игнорируем ошибку, если виджет удален

def on_closing():
    """Обработчик события закрытия окна."""
    global is_dirty
    page_save_ok = True
    inner_widget = _get_inner_text_widget()
    textbox_modified = False
    if inner_widget:
         try: textbox_modified = inner_widget.edit_modified()
         except tk.TclError: pass

    # Сначала пытаемся сохранить изменения ТЕКУЩЕЙ страницы
    if textbox_modified:
        print("Обнаружены изменения в редакторе при закрытии...")
        page_save_ok = save_current_page_data_if_dirty(prompt_save=False) # Не спрашиваем
        if not page_save_ok:
             if not messagebox.askokcancel("Ошибка сохранения страницы", "Не удалось сохранить изменения на тек. странице. Все равно выйти?"):
                 return # Отменяем закрытие

    # Затем проверяем глобальный флаг is_dirty (изменения в памяти)
    if is_dirty:
        result = messagebox.askyesnocancel("Выход", "Есть несохраненные изменения. Сохранить перед выходом?", icon='warning')
        if result is True: # Yes
            save_xliff()
            if is_dirty: # Если сохранение не удалось
                 if messagebox.askokcancel("Ошибка сохранения файла", "Не удалось сохранить изменения. Все равно выйти?", icon='error'):
                     main_window.destroy() # Выходим без сохранения
                 else: return # Отмена
            else: main_window.destroy() # Сохранение удалось
        elif result is False: # No
            if messagebox.askyesno("Подтверждение", "Вы уверены, что хотите выйти без сохранения?", icon='warning'):
                 main_window.destroy()
            else: return # Отмена
        else: # Cancel
            return # Отмена
    else: # Нет изменений (is_dirty == False)
        main_window.destroy()

# --- Запуск приложения ---
if __name__ == "__main__":
    filepath_from_cli = None # <--- Добавлено для хранения пути из командной строки
    if len(sys.argv) > 1: # <--- Проверка аргументов командной строки
        filepath_from_cli = sys.argv[1]
        print(f"Файл из командной строки: {filepath_from_cli}") # Опционально для отладки

    display_available = True
    try:
        _test_root = tk.Tk(); _test_root.withdraw(); _test_root.destroy()
        print("Проверка дисплея прошла успешно.")
    except tk.TclError as e:
        if "no display name" in str(e) or "couldn't connect to display" in str(e):
             print(f"{Fore.RED}Ошибка Tkinter: Не удалось подключиться к дисплею.{Style.RESET_ALL}")
             display_available = False
             try: root_err = tk.Tk(); root_err.withdraw(); messagebox.showerror("Ошибка запуска", "Нет граф. дисплея."); root_err.destroy()
             except Exception: pass
        else:
             print(f"{Fore.RED}Неожиданная ошибка Tcl/Tk при проверке дисплея:{Style.RESET_ALL}\n{e}")
             display_available = False
             sys.exit(1)

    if display_available:
        try:
            root = create_main_window()
            if root:
                if filepath_from_cli: # <--- Загрузка файла, если путь передан
                    load_xliff(filepath_arg=filepath_from_cli) # <--- Вызов load_xliff с путем
                root.mainloop()
            else: print(f"{Fore.RED}Ошибка: Не удалось создать главное окно.{Style.RESET_ALL}"); sys.exit(1)
        except tk.TclError as e:
             print(f"{Fore.RED}Критическая ошибка Tcl/Tk:{Style.RESET_ALL}"); traceback.print_exc()
             try: root_err = tk.Tk(); root_err.withdraw(); messagebox.showerror("Критическая ошибка Tcl/Tk", f"Ошибка Tcl/Tk:\n{e}\nЗакрытие."); root_err.destroy()
             except Exception: pass
             sys.exit(1)
        except Exception as e:
             print(f"{Fore.RED}Критическая ошибка Python:{Style.RESET_ALL}"); traceback.print_exc()
             try: root_err = tk.Tk(); root_err.withdraw(); messagebox.showerror("Критическая ошибка Python", f"Ошибка Python:\n{type(e).__name__}: {e}\nЗакрытие."); root_err.destroy()
             except Exception: pass
             sys.exit(1)
    else:
         print("Запуск GUI отменен из-за отсутствия дисплея.")
         sys.exit(1)

# --- END OF FILE xliff_editor_gui.py ---