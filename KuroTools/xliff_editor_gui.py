# --- START OF FILE xliff_editor_gui.py ---

import tkinter as tk
from tkinter import filedialog, messagebox, font as tkfont, ttk # Added ttk for Combobox if needed later
import customtkinter as ctk # type: ignore
import lxml.etree as ET # type: ignore
import os
import sys
import shutil
import math
import io
import uuid
import traceback
import time
import re # For parsing note tags

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

# --- Deep Translator imports ---
try:
    from deep_translator import GoogleTranslator, MyMemoryTranslator # type: ignore
    TRANSLATOR_SERVICES = ["Google", "MyMemory"]
    DEFAULT_TRANSLATOR_SERVICE = "Google" # Или "MyMemory"
    TRANSLATION_AVAILABLE = True
    print(f"Библиотека deep-translator найдена. Доступные сервисы: {', '.join(TRANSLATOR_SERVICES)}. Сервис по умолчанию: {DEFAULT_TRANSLATOR_SERVICE}")
except ImportError:
    print(f"{Fore.YELLOW}Предупреждение: Библиотека deep-translator не найдена (pip install deep-translator). Автоматический перевод будет недоступен.{Style.RESET_ALL}")
    TRANSLATION_AVAILABLE = False
    TRANSLATOR_SERVICES = []
    GoogleTranslator = MyMemoryTranslator = None
    DEFAULT_TRANSLATOR_SERVICE = None
# --- /Deep Translator imports ---

# --- Конфигурация ---
XLIFF_FILE_DEFAULT = "data_game_strings.xliff"
BACKUP_SUFFIX = ".bak"
SOURCE_LANG = "en" # Fallback
TARGET_LANG = "ru" # Fallback
ITEMS_PER_PAGE_DEFAULT = 500
DEFAULT_MODE = "markup"
TRANSLATION_DELAY_SECONDS = 0.15
# Регулярное выражение для извлечения имени файла из тега <note>
NOTE_FILE_REGEX = re.compile(r"^File:\s*(.+)$", re.IGNORECASE)
ALL_FILES_FILTER = "--- Все файлы ---"
# --------------------

# --- Mappings for MyMemory ---
MYMEMORY_LANG_MAP = {
    "en": "en-US",  # Default to US English
    "ru": "ru-RU",
    "ko": "ko-KR",
    "ja": "ja-JP",
    "zh": "zh-CN", # Simplified Chinese
    "es": "es-ES", # Spain Spanish
    "fr": "fr-FR", # France French
    "de": "de-DE", # German German
    # Add more mappings as needed based on common languages in your files
    # or the MyMemory supported list.
}

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
all_trans_units = []           # Список ВСЕХ <trans-unit> объектов lxml
untranslated_ids = []          # Список ID ВСЕХ непереведенных <trans-unit>
filtered_untranslated_ids = [] # Список ID непереведенных <trans-unit> после применения фильтра файла
unit_id_to_filename_map = {}   # Словарь {unit_id: filename} для быстрой фильтрации
available_filenames = []       # Список доступных имен файлов для фильтра (+ ALL_FILES_FILTER)
selected_filename_filter = ALL_FILES_FILTER # Текущий выбранный фильтр файла

current_page_index = 0
items_per_page = ITEMS_PER_PAGE_DEFAULT
current_page_units_map = {} # Словарь {unit_id: unit_element} для ТЕКУЩЕЙ отображаемой страницы
is_dirty = False            # Есть ли несохраненные изменения в памяти
current_mode = DEFAULT_MODE # 'markup' или 'edit'
detected_source_lang = SOURCE_LANG
detected_target_lang = TARGET_LANG
selected_translator_service = DEFAULT_TRANSLATOR_SERVICE # Выбранный сервис перевода

# --- Переменные виджетов ---
main_window = None
editor_textbox = None
save_button = None
open_button = None
markup_mode_button = None
edit_mode_button = None
translate_button = None
stats_button = None
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
file_filter_combobox = None # Combobox для фильтра файлов
translator_combobox = None # Combobox для выбора переводчика
font_size_increase_button = None
font_size_decrease_button = None
current_font_size = 11 # Начальный размер шрифта редактора

LXML_NSMAP = {'xliff': 'urn:oasis:names:tc:xliff:document:1.2'}

# --- Общие функции UI ---

def update_status(message):
    """Обновляет текст в строке статуса."""
    global status_label
    if status_label:
        status_label.configure(text=message)
    if main_window:
        main_window.update_idletasks()

def reset_state():
     """Сбрасывает состояние приложения."""
     global xliff_tree, xliff_root, xliff_filepath, all_trans_units, untranslated_ids
     global filtered_untranslated_ids, unit_id_to_filename_map, available_filenames, selected_filename_filter
     global current_page_index, is_dirty, current_page_units_map, editor_textbox
     global save_button, status_label, page_label, prev_button, next_button
     global page_entry, go_button, page_size_entry, page_size_button, page_var
     global translate_button, stats_button, file_filter_combobox
     global detected_source_lang, detected_target_lang

     xliff_tree = xliff_root = None
     xliff_filepath = ""
     all_trans_units = []
     untranslated_ids = []
     filtered_untranslated_ids = []
     unit_id_to_filename_map = {}
     available_filenames = []
     selected_filename_filter = ALL_FILES_FILTER
     current_page_units_map = {}
     current_page_index = 0
     is_dirty = False
     detected_source_lang = SOURCE_LANG
     detected_target_lang = TARGET_LANG

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
     if translate_button: translate_button.configure(state=tk.DISABLED)
     if stats_button: stats_button.configure(state=tk.DISABLED)
     if page_var: page_var.set("")
     if page_label: page_label.configure(text="Страница: - / -")
     if file_filter_combobox:
         file_filter_combobox.configure(values=[ALL_FILES_FILTER], state=tk.DISABLED)
         file_filter_combobox.set(ALL_FILES_FILTER)


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
    if not xliff_tree: return # Не делаем ничего, если файл не загружен
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
                     if not save_current_page_data_if_dirty(prompt_save=False):
                         messagebox.showerror("Ошибка", "Не удалось сохранить изменения. Смена размера отменена.")
                         page_size_var.set(str(items_per_page))
                         return

            current_first_item_global_index_in_filtered_list = current_page_index * items_per_page
            items_per_page = new_size
            current_page_index = current_first_item_global_index_in_filtered_list // items_per_page

            # Обновляем отображение текущей страницы
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
    global current_page_index, page_var, filtered_untranslated_ids, items_per_page
    if not filtered_untranslated_ids: return
    try:
        page_num_str = page_var.get()
        if not page_num_str: return
        page_num = int(page_num_str)
        num_pages = math.ceil(len(filtered_untranslated_ids) / items_per_page) if filtered_untranslated_ids else 1

        if 1 <= page_num <= num_pages:
            new_page_index = page_num - 1
            if new_page_index == current_page_index: return
            if not save_current_page_data_if_dirty(prompt_save=True):
                page_var.set(str(current_page_index + 1))
                return
            current_page_index = new_page_index
            if current_mode == 'markup': display_markup_page()
            elif current_mode == 'edit': display_edit_page()
            update_status(f"Переход на страницу {current_page_index + 1} (фильтр: {selected_filename_filter})")
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
    global current_page_index, filtered_untranslated_ids, items_per_page
    num_pages = math.ceil(len(filtered_untranslated_ids) / items_per_page) if filtered_untranslated_ids else 1
    if current_page_index < num_pages - 1:
        if not save_current_page_data_if_dirty(prompt_save=True): return
        current_page_index += 1
        if current_mode == 'markup': display_markup_page()
        elif current_mode == 'edit': display_edit_page()
        update_status(f"Переход на страницу {current_page_index + 1} (фильтр: {selected_filename_filter})")
        set_focus_on_editor()

def go_to_prev_page():
    """Переходит на предыдущую страницу."""
    global current_page_index
    if current_page_index > 0:
        if not save_current_page_data_if_dirty(prompt_save=True): return
        current_page_index -= 1
        if current_mode == 'markup': display_markup_page()
        elif current_mode == 'edit': display_edit_page()
        update_status(f"Переход на страницу {current_page_index + 1} (фильтр: {selected_filename_filter})")
        set_focus_on_editor()

def update_navigation_buttons_state():
     """Обновляет состояние кнопок навигации."""
     global prev_button, next_button, go_button, page_entry, page_size_button, page_size_entry
     global translate_button, filtered_untranslated_ids, items_per_page, xliff_tree, current_page_units_map
     global page_label, page_var, selected_filename_filter

     has_content = bool(filtered_untranslated_ids)
     if not xliff_tree: has_content = False
     num_pages = math.ceil(len(filtered_untranslated_ids) / items_per_page) if has_content else 1

     prev_state = tk.NORMAL if has_content and current_page_index > 0 else tk.DISABLED
     next_state = tk.NORMAL if has_content and current_page_index < num_pages - 1 else tk.DISABLED
     entry_state = tk.NORMAL if has_content else tk.DISABLED
     translate_state = tk.NORMAL if xliff_tree and TRANSLATION_AVAILABLE and current_page_units_map else tk.DISABLED

     if prev_button: prev_button.configure(state=prev_state)
     if next_button: next_button.configure(state=next_state)
     if page_entry: page_entry.configure(state=entry_state)
     if go_button: go_button.configure(state=entry_state)
     if translate_button: translate_button.configure(state=translate_state)

     size_entry_state = tk.NORMAL if xliff_tree else tk.DISABLED
     if page_size_entry: page_size_entry.configure(state=size_entry_state)
     if page_size_button: page_size_button.configure(state=size_entry_state)

     # Обновление метки страницы
     if has_content:
         filter_text = os.path.basename(selected_filename_filter) if selected_filename_filter != ALL_FILES_FILTER else "Все"
         page_label_text = f"Стр: {current_page_index + 1}/{num_pages} (Ф: {filter_text})"
         if page_var: page_var.set(str(current_page_index + 1))
     else:
         page_label_text = "Страница: - / -"
         if page_var: page_var.set("")
     if page_label: page_label.configure(text=page_label_text)

def change_font_size(delta):
    """Изменяет размер шрифта редактора."""
    global editor_textbox, current_font_size
    if not editor_textbox: return
    new_size = current_font_size + delta
    if 5 <= new_size <= 30: # Ограничение размера
        current_font_size = new_size
        editor_font = ctk.CTkFont(family="Consolas", size=current_font_size) # Используем текущий шрифт
        editor_textbox.configure(font=editor_font)
        print(f"Размер шрифта изменен на {current_font_size}")
    else:
        print(f"Размер шрифта {new_size} вне допустимого диапазона (5-30).")

# --- Функции для работы с XLIFF ---

def load_xliff(filepath_arg=None):
    """Загружает XLIFF файл."""
    global xliff_tree, xliff_root, xliff_filepath, all_trans_units, untranslated_ids
    global filtered_untranslated_ids, unit_id_to_filename_map, available_filenames, selected_filename_filter
    global current_page_index, is_dirty, current_mode, save_button, status_label
    global page_label, open_button, items_per_page, page_size_var, stats_button
    global detected_source_lang, detected_target_lang, file_filter_combobox

    if is_dirty:
        if not messagebox.askyesno("Несохраненные изменения", "Есть изменения. Загрузить новый файл без сохранения?"):
            return

    if filepath_arg:
        filepath = filepath_arg
    else:
        filepath = filedialog.askopenfilename(
            title="Выберите XLIFF файл",
            filetypes=[("XLIFF files", "*.xliff"), ("All files", "*.*")],
            initialdir=os.path.dirname(xliff_filepath) if xliff_filepath else ".",
            initialfile=os.path.basename(xliff_filepath) if xliff_filepath else XLIFF_FILE_DEFAULT
        )
    if not filepath: return

    reset_state()
    items_per_page = ITEMS_PER_PAGE_DEFAULT # Сброс размера страницы к дефолту при загрузке
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

        # ---> ОПРЕДЕЛЕНИЕ ЯЗЫКОВ <---
        file_node = xliff_root.find('.//xliff:file', namespaces=LXML_NSMAP)
        if file_node is not None:
            src_lang = file_node.get('source-language')
            tgt_lang = file_node.get('target-language')
            if src_lang:
                detected_source_lang = src_lang.lower() # Приводим к нижнему регистру для консистентности
                print(f"Обнаружен source-language: {detected_source_lang}")
            else:
                detected_source_lang = SOURCE_LANG # Fallback
                print(f"{Fore.YELLOW}Предупреждение: Атрибут 'source-language' не найден в <file>. Используется '{detected_source_lang}'.{Style.RESET_ALL}")
            if tgt_lang:
                detected_target_lang = tgt_lang.lower() # Приводим к нижнему регистру
                print(f"Обнаружен target-language: {detected_target_lang}")
            else:
                detected_target_lang = TARGET_LANG # Fallback
                print(f"{Fore.YELLOW}Предупреждение: Атрибут 'target-language' не найден в <file>. Используется '{detected_target_lang}'.{Style.RESET_ALL}")
        else:
            detected_source_lang = SOURCE_LANG # Fallback
            detected_target_lang = TARGET_LANG # Fallback
            print(f"{Fore.YELLOW}Предупреждение: Элемент <file> не найден. Используются языки по умолчанию: source='{detected_source_lang}', target='{detected_target_lang}'.{Style.RESET_ALL}")
        # --- КОНЕЦ ОПРЕДЕЛЕНИЯ ЯЗЫКОВ ---

        all_trans_units = xliff_root.xpath(".//xliff:trans-unit", namespaces=LXML_NSMAP)

        if not all_trans_units:
             print(f"{Fore.YELLOW}Предупреждение: В файле не найдено <trans-unit>.{Style.RESET_ALL}")

        # Определение непереведенных строк И извлечение имен файлов из <note>
        untranslated_ids = []
        unit_id_to_filename_map = {}
        filenames_in_notes = set()
        for unit in all_trans_units:
            unit_id = unit.get("id")
            if not unit_id:
                 print(f"{Fore.YELLOW}Предупреждение: <trans-unit> без 'id'. Пропускается.{Style.RESET_ALL}")
                 continue

            # Извлечение имени файла из <note>
            note_node = unit.find("xliff:note", namespaces=LXML_NSMAP)
            filename = None
            if note_node is not None and note_node.text:
                match = NOTE_FILE_REGEX.match(note_node.text.strip())
                if match:
                    filename = match.group(1).strip()
                    if filename:
                        unit_id_to_filename_map[unit_id] = filename
                        filenames_in_notes.add(filename)
                    # else: print(f"Предупреждение: Пустое имя файла в <note> для ID {unit_id}") # Debug

            # Проверка на непереведенность
            target_elements = unit.xpath("./xliff:target", namespaces=LXML_NSMAP)
            if not target_elements:
                untranslated_ids.append(unit_id)
            else:
                target_node = target_elements[0]
                approved_attr = target_node.get('approved')
                # Проверяем на пустой контент (учитывая пробелы)
                has_content = target_node.xpath("normalize-space(.)")

                # Считаем непереведенным, если нет контента И нет approved='yes'
                if not has_content and approved_attr != 'yes':
                    untranslated_ids.append(unit_id)

        # Настройка фильтра файлов
        available_filenames = [ALL_FILES_FILTER] + sorted(list(filenames_in_notes))
        selected_filename_filter = ALL_FILES_FILTER
        if file_filter_combobox:
            file_filter_combobox.configure(values=available_filenames)
            if len(available_filenames) > 1:
                file_filter_combobox.configure(state=tk.NORMAL)
                print(f"Обнаружено {len(available_filenames)-1} файлов в <note> тегах.")
            else:
                file_filter_combobox.configure(state=tk.DISABLED)
                print("Теги <note> с именами файлов не найдены или их только один тип.")
            file_filter_combobox.set(ALL_FILES_FILTER)

        # Применяем начальный фильтр (показываем все)
        apply_current_filter(reset_page=True) # filtered_untranslated_ids будет заполнен здесь

        is_dirty = False
        set_mode(DEFAULT_MODE, force_update=True) # Устанавливаем дефолтный режим

        update_status(f"Загружен: {os.path.basename(filepath)} | Всего: {len(all_trans_units)} | Без перевода: {len(untranslated_ids)} | {detected_source_lang} -> {detected_target_lang}")
        if main_window: main_window.title(f"XLIFF Paged Editor - {os.path.basename(filepath)} [{detected_source_lang}->{detected_target_lang}]")
        if save_button: save_button.configure(state=tk.DISABLED)
        if stats_button: stats_button.configure(state=tk.NORMAL)
        if editor_textbox:
            editor_textbox.configure(state=tk.NORMAL)
            set_focus_on_editor()
        update_navigation_buttons_state() # Обновит навигацию после применения фильтра

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
            # Не показываем messagebox здесь, чтобы не мешать другим операциям
            return False # Считаем, что сохранить не удалось

    if not textbox_modified: return True

    should_save = True
    if prompt_save:
        mode_text = "разметки" if current_mode == 'markup' else "редактирования"
        filter_text = os.path.basename(selected_filename_filter) if selected_filename_filter != ALL_FILES_FILTER else "Все файлы"
        result = messagebox.askyesnocancel("Сохранить изменения?", f"Сохранить изменения на стр. {current_page_index + 1} (режим {mode_text}, фильтр: {filter_text})?")
        if result is None: return False
        elif result is False:
            should_save = False
            if inner_widget:
                try: inner_widget.edit_modified(False)
                except tk.TclError: pass
            return True

    if should_save:
        success = False
        print(f"Сохранение данных страницы {current_page_index + 1}...")
        if current_mode == 'markup':
            success = save_markup_page_data(force_check=True) # force_check нужен, т.к. мы уже проверили modified
            if not success:
                 messagebox.showerror("Ошибка сохранения", "Не удалось сохранить (разметка). Проверьте XML.")
                 return False
        elif current_mode == 'edit':
            success = save_edit_page_data(force_check=True) # force_check нужен
            if not success:
                 messagebox.showerror("Ошибка сохранения", "Не удалось сохранить (редактирование).")
                 return False
        if success:
            if inner_widget:
                try:
                    inner_widget.edit_modified(False)
                    print(f"Флаг модификации редактора сброшен после сохранения стр. {current_page_index + 1}.")
                except tk.TclError: pass
            # После успешного сохранения страницы, нужно обновить фильтрованный список и навигацию
            # Это будет сделано внутри save_markup/edit_page_data через apply_current_filter
            return True
        else:
             messagebox.showerror("Ошибка", "Непредвиденная ошибка при сохранении страницы.")
             return False
    else: # Если пользователь выбрал "Нет" (не сохранять)
         return True

def save_xliff():
    """Сохраняет все изменения из памяти в XLIFF файл."""
    global xliff_tree, xliff_filepath, is_dirty, save_button, status_label
    if xliff_tree is None or not xliff_filepath:
        messagebox.showwarning("Нет данных", "Сначала загрузите XLIFF файл.")
        return

    # Сначала пытаемся сохранить данные текущей страницы, если они были изменены
    if not save_current_page_data_if_dirty(prompt_save=False): # Не спрашиваем, просто пытаемся сохранить
        messagebox.showerror("Ошибка", "Не удалось сохранить изменения текущей страницы. Исправьте ошибки перед сохранением файла.")
        return

    # Проверяем is_dirty еще раз, т.к. save_current_page_data_if_dirty мог установить его
    if not is_dirty:
        if save_button: save_button.configure(state=tk.DISABLED)
        update_status("Нет изменений для сохранения.")
        print("Нет глобальных изменений для сохранения в файл.")
        return

    backup_filepath = xliff_filepath + BACKUP_SUFFIX
    try:
        if os.path.exists(xliff_filepath):
             print(f"Создание резервной копии: {os.path.basename(backup_filepath)}")
             shutil.copy2(xliff_filepath, backup_filepath)

        print(f"Сохранение изменений в: {xliff_filepath}...")
        output_buffer = io.BytesIO()

        # Просто записываем текущее дерево lxml
        xliff_tree.write(
            output_buffer,
            pretty_print=True,
            encoding='utf-8',
            xml_declaration=True,
        )
        xml_content = output_buffer.getvalue()

        # Проверка корректности перед записью (опционально)
        try:
            parser_check = ET.XMLParser(remove_blank_text=False, strip_cdata=False, resolve_entities=False)
            ET.fromstring(xml_content, parser=parser_check)
            print("Проверка XML перед записью: OK")
        except ET.XMLSyntaxError as xe:
            print(f"{Fore.RED}Ошибка: Сгенерированный XML некорректен! Сохранение отменено.{Style.RESET_ALL}")
            messagebox.showerror("Ошибка XML", f"Ошибка валидации перед сохранением:\n{xe}\n\nСохранение отменено.")
            return

        with open(xliff_filepath, "wb") as f:
            f.write(xml_content)

        is_dirty = False # Сбрасываем флаг ТОЛЬКО при успешном сохранении
        if save_button: save_button.configure(state=tk.DISABLED)
        # Обновляем статус с актуальным числом непереведенных
        update_status(f"Файл сохранен: {os.path.basename(xliff_filepath)} | Всего: {len(all_trans_units)} | Без перевода: {len(untranslated_ids)}")
        print("Файл успешно сохранен, is_dirty сброшен.")

        # Сбрасываем флаг модификации редактора, т.к. все сохранено
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
        if editor_wrapper:
             try:
                 editor_wrapper.configure(state=tk.NORMAL)
                 editor_wrapper.delete("1.0", tk.END)
                 editor_wrapper.insert("1.0", text)
                 editor_wrapper.edit_modified(False)
                 editor_wrapper.configure(state=(tk.NORMAL if xliff_tree else tk.DISABLED))
             except Exception as e: print(f"Ошибка вставки в обертку: {e}")
        return

    try:
        editor_wrapper.configure(state=tk.NORMAL)
        target_widget.configure(state=tk.NORMAL)
        target_widget.delete("1.0", tk.END)

        # Удаляем старые теги подсветки
        for tag in target_widget.tag_names():
            if tag.startswith("Token_"):
                try: target_widget.tag_delete(tag)
                except tk.TclError: pass # Игнорируем ошибку, если тега уже нет

        if not PYGMENTS_AVAILABLE or TEXT_HIGHLIGHT_CONFIG["lexer"] is None or current_mode != 'markup':
            target_widget.insert("1.0", text)
        else:
            # Настраиваем теги для текущей подсветки
            for token_type_key, config in TEXT_HIGHLIGHT_CONFIG["tags"].items():
                tag_name = "Token_" + str(token_type_key).replace(".", "_").replace("'", "")
                try: target_widget.tag_config(tag_name, **config)
                except tk.TclError as te: print(f"Ошибка настройки тега {tag_name}: {te}")

            lexer = TEXT_HIGHLIGHT_CONFIG["lexer"]
            try:
                tokens = lex(text, lexer)
                for token_type, token_value in tokens:
                    # Ищем наиболее специфичный тег
                    tag_config_key = None
                    temp_type = token_type
                    while temp_type is not None:
                        found = False
                        # Ищем точное совпадение объекта токена (если Token доступен) или по строковому представлению
                        key_to_match = temp_type if PYGMENTS_AVAILABLE else str(temp_type)
                        for config_key_obj in TEXT_HIGHLIGHT_CONFIG["tags"].keys():
                             match_target = config_key_obj if PYGMENTS_AVAILABLE else str(config_key_obj)
                             if key_to_match == match_target:
                                 tag_config_key = config_key_obj; found = True; break
                        if found: break
                        # Поднимаемся к родительскому токену
                        temp_type = getattr(temp_type, 'parent', None)

                    if tag_config_key:
                        tag_name = "Token_" + str(tag_config_key).replace(".", "_").replace("'", "")
                        try:
                            target_widget.insert(tk.END, token_value, tag_name)
                        except tk.TclError: # Если тег не найден (маловероятно)
                             target_widget.insert(tk.END, token_value)
                    else:
                        target_widget.insert(tk.END, token_value)
            except Exception as e:
                print(f"{Fore.RED}Ошибка подсветки синтаксиса: {e}{Style.RESET_ALL}")
                # В случае ошибки просто вставляем текст без подсветки
                target_widget.delete("1.0", tk.END)
                target_widget.insert("1.0", text)

        target_widget.edit_modified(False) # Сбрасываем флаг модификации после программной вставки

        final_state = tk.NORMAL if xliff_tree else tk.DISABLED
        editor_wrapper.configure(state=final_state)
        target_widget.configure(state=final_state)

    except tk.TclError as e:
        print(f"Ошибка Tcl при установке текста редактора: {e}")
    except Exception as e:
        print(f"Общая ошибка при установке текста редактора: {e}")
        traceback.print_exc()


# --- Функция автоматического перевода ---
def translate_current_page():
    """Переводит <source> для всех <trans-unit> на текущей странице."""
    global current_page_units_map, is_dirty, save_button, untranslated_ids, filtered_untranslated_ids
    global translate_button, status_label, all_trans_units
    global detected_source_lang, detected_target_lang, selected_translator_service
    global MYMEMORY_LANG_MAP # Ensure access to the map

    if not TRANSLATION_AVAILABLE:
        messagebox.showerror("Ошибка", "Функция перевода недоступна. Установите 'deep-translator'.")
        return
    if not current_page_units_map:
        messagebox.showinfo("Информация", "Нет строк для перевода на текущей странице (учитывая фильтр).")
        return
    if not selected_translator_service:
        messagebox.showerror("Ошибка", "Не выбран сервис перевода.")
        return

    source_lang_for_translator = detected_source_lang
    target_lang_for_translator = detected_target_lang

    # --- CORRECTED SECTION START ---
    if selected_translator_service == "MyMemory":
        # Use mapping, fall back to the original simple code if not in the map
        # MyMemory might accept some simple codes like 'fr', 'de' directly.
        source_lang_for_translator = MYMEMORY_LANG_MAP.get(detected_source_lang, detected_source_lang)
        target_lang_for_translator = MYMEMORY_LANG_MAP.get(detected_target_lang, detected_target_lang)
        print(f"DEBUG: Using MyMemory formatted languages: {source_lang_for_translator} -> {target_lang_for_translator}") # Added for debugging
    # --- CORRECTED SECTION END ---

    # Update the confirmation dialog to show the codes being used
    if not messagebox.askyesno("Подтверждение перевода",
                               f"Перевести {len(current_page_units_map)} строк на стр. {current_page_index + 1} "
                               f"({source_lang_for_translator} -> {target_lang_for_translator})?\n\n" # Use the potentially formatted codes
                               f"Существующие переводы будут ЗАМЕНЕНЫ.\n"
                               f"Сервис: {selected_translator_service}"):
        return

    print(f"Начало перевода страницы {current_page_index + 1} с помощью {selected_translator_service} ({source_lang_for_translator} -> {target_lang_for_translator})...") # Log the codes being used
    if translate_button: translate_button.configure(state=tk.DISABLED)
    original_status = status_label.cget("text") if status_label else "Перевод..."
    update_status(f"Перевод стр. {current_page_index + 1} ({source_lang_for_translator}->{target_lang_for_translator}) (0%)...") # Update status with used codes

    translated_count = 0; error_count = 0; updated_ids_on_page = set(); any_change_made_in_memory = False
    total_units = len(current_page_units_map); units_processed = 0

    try:
        if selected_translator_service == "Google":
            # Google usually handles simple codes well
            translator = GoogleTranslator(source=detected_source_lang, target=detected_target_lang)
        elif selected_translator_service == "MyMemory":
            # Pass the potentially formatted codes
            translator = MyMemoryTranslator(source=source_lang_for_translator, target=target_lang_for_translator)
        else: raise ValueError(f"Неизвестный сервис: {selected_translator_service}")
    except Exception as e:
         # Update the error message to show the codes that failed
         messagebox.showerror("Ошибка инициализации переводчика",
                              f"Не удалось создать переводчик ({source_lang_for_translator}->{target_lang_for_translator} с {selected_translator_service}):\n{e}")
         update_navigation_buttons_state() # Re-enable translate button potentially
         update_status(original_status)
         return

    # Используем карту всех юнитов для доступа по ID
    id_to_unit_map = {unit.get("id"): unit for unit in all_trans_units if unit.get("id")}

    # Итерируем по ID юнитов, которые *отображаются* на текущей странице
    for unit_id in list(current_page_units_map.keys()):
        unit = id_to_unit_map.get(unit_id) # Получаем сам элемент из общего списка
        if unit is None:
            print(f"Предупреждение: Unit с ID {unit_id} не найден в общем списке, пропуск.")
            units_processed += 1; continue

        source_node = unit.find("xliff:source", namespaces=LXML_NSMAP)
        # Используем itertext для сбора текста из вложенных тегов, если они есть в source
        source_text_parts = [text for text in source_node.itertext()] if source_node is not None else []
        source_text = "".join(source_text_parts).strip()

        if not source_text:
            print(f"  - Пропуск ID {unit_id}: пустой <source>.")
            units_processed += 1; continue

        target_node = unit.find("xliff:target", namespaces=LXML_NSMAP)
        # Сравниваем с текстом существующего перевода
        original_target_text = "".join(target_node.itertext()).strip() if target_node is not None else ""

        try:
            print(f"  - Перевод ID {unit_id} ({units_processed + 1}/{total_units}) [{len(source_text)} chars]...")
            translated_text = translator.translate(source_text)
            time.sleep(TRANSLATION_DELAY_SECONDS) # Пауза между запросами

            if translated_text and translated_text.strip():
                translated_text = translated_text.strip() # Убираем лишние пробелы
                if target_node is None:
                    target_node = ET.Element(f"{{{LXML_NSMAP['xliff']}}}target")
                    # Вставляем <target> после <source> или <note>
                    note_node = unit.find("xliff:note", namespaces=LXML_NSMAP)
                    insert_point = source_node if source_node is not None else note_node
                    if insert_point is not None:
                         insert_point.addnext(target_node)
                    else: # Если нет ни source, ни note, вставляем последним
                         last_element = unit.xpath("./*[last()]")
                         if last_element: last_element[0].addnext(target_node)
                         else: unit.append(target_node)

                # Обновляем, только если текст реально изменился
                if original_target_text != translated_text:
                    target_node.clear() # Очищаем содержимое target
                    target_node.text = translated_text # Устанавливаем новый текст
                    if 'approved' in target_node.attrib: del target_node.attrib['approved'] # Сбрасываем атрибут 'approved'
                    any_change_made_in_memory = True # Флаг, что были реальные изменения
                    updated_ids_on_page.add(unit_id)

                translated_count += 1
            else:
                print(f"  - {Fore.YELLOW}Предупреждение: Пустой перевод для ID {unit_id}.{Style.RESET_ALL}")
                error_count += 1
        except Exception as e:
            print(f"  - {Fore.RED}Ошибка перевода ID {unit_id}: {e}{Style.RESET_ALL}")
            error_count += 1
            if "TooManyRequestsError" in str(e) or "timed out" in str(e) or "429" in str(e):
                 print(f"{Fore.YELLOW}    -> Обнаружена ошибка сети/лимита запросов. Пауза 5 секунд...{Style.RESET_ALL}")
                 time.sleep(5)
            elif "TranslationNotFound" in str(e):
                 print(f"{Fore.YELLOW}    -> Перевод не найден для этого текста.{Style.RESET_ALL}")

        units_processed += 1
        progress = int((units_processed / total_units) * 100)
        update_status(f"Перевод стр. {current_page_index + 1} ({source_lang_for_translator}->{target_lang_for_translator}) ({progress}%)...")

    final_status_part1 = f"Перевод ({selected_translator_service}) завершен."
    final_status_part2 = f"Успешно: {translated_count}, Ошибки/Пропущено: {error_count}."
    print(final_status_part1, final_status_part2)

    if any_change_made_in_memory:
        print("Изменения внесены в память.")
        is_dirty = True # Устанавливаем глобальный флаг изменений
        if save_button: save_button.configure(state=tk.NORMAL)

        # Обновляем МАСТЕР-список непереведенных ID
        ids_removed_from_untranslated = 0
        for unit_id in updated_ids_on_page:
            if unit_id in untranslated_ids:
                unit = id_to_unit_map.get(unit_id)
                if unit:
                    target = unit.find("xliff:target", namespaces=LXML_NSMAP)
                    # Считаем переведенным, если есть target с непустым текстом
                    is_now_translated = target is not None and target.xpath("normalize-space(.)")
                    if is_now_translated:
                         untranslated_ids.remove(unit_id)
                         ids_removed_from_untranslated += 1

        if ids_removed_from_untranslated > 0:
            print(f"Удалено {ids_removed_from_untranslated} ID из мастер-списка непереведенных.")
            # Переприменяем текущий фильтр, чтобы обновить filtered_untranslated_ids
            apply_current_filter(reset_page=False) # Не сбрасываем на первую страницу
        else:
             # Если ничего не было удалено, возможно, переводили уже переведенные
             # Все равно обновим отображение, чтобы показать актуальный текст
             if current_mode == 'markup': display_markup_page()
             elif current_mode == 'edit': display_edit_page()

        # Сбрасываем флаг модификации редактора после автоперевода
        inner_widget = _get_inner_text_widget()
        if inner_widget:
            try: inner_widget.edit_modified(False)
            except tk.TclError: pass

        # Обновляем статус и навигацию
        update_navigation_buttons_state() # Обновит page_label и кнопки
        update_status(f"{final_status_part1} {final_status_part2} | Всего: {len(all_trans_units)} | Без перевода: {len(untranslated_ids)}")

    else:
        print("Не было внесено изменений в память (возможно, переводы совпали или были ошибки).")
        update_navigation_buttons_state() # Восстанавливаем кнопку перевода
        update_status(f"{final_status_part1} {final_status_part2} | Нет изменений.")


# --- Функции фильтрации ---

def on_file_filter_change(event=None):
    """Обработчик изменения выбора в комбобоксе фильтра файлов."""
    global selected_filename_filter, file_filter_combobox
    if not file_filter_combobox or not xliff_tree: return

    new_filter = file_filter_combobox.get()
    if new_filter == selected_filename_filter:
        return # Ничего не изменилось

    # Проверяем несохраненные изменения на ТЕКУЩЕЙ странице перед сменой фильтра
    if not save_current_page_data_if_dirty(prompt_save=True):
        # Пользователь отменил или произошла ошибка сохранения, возвращаем старое значение
        print("Смена фильтра отменена из-за несохраненных изменений.")
        file_filter_combobox.set(selected_filename_filter)
        return

    print(f"Смена фильтра на: {new_filter}")
    selected_filename_filter = new_filter
    apply_current_filter(reset_page=True) # Применяем новый фильтр и сбрасываем на 1 страницу
    set_focus_on_editor()


def apply_current_filter(reset_page=False):
    """
    Фильтрует мастер-список untranslated_ids на основе selected_filename_filter
    и обновляет filtered_untranslated_ids.
    Обновляет отображение.
    """
    global untranslated_ids, filtered_untranslated_ids, selected_filename_filter
    global unit_id_to_filename_map, current_page_index, status_label, all_trans_units

    if not xliff_tree:
        filtered_untranslated_ids = []
    elif selected_filename_filter == ALL_FILES_FILTER:
        filtered_untranslated_ids = list(untranslated_ids) # Копия мастер-списка
        print(f"Применен фильтр '{ALL_FILES_FILTER}'. Найдено непереведенных: {len(filtered_untranslated_ids)}")
    else:
        filtered_untranslated_ids = [
            unit_id for unit_id in untranslated_ids
            if unit_id_to_filename_map.get(unit_id) == selected_filename_filter
        ]
        print(f"Применен фильтр '{selected_filename_filter}'. Найдено непереведенных: {len(filtered_untranslated_ids)}")

    if reset_page:
        current_page_index = 0

    # Убедимся, что current_page_index не выходит за пределы нового списка
    num_pages = math.ceil(len(filtered_untranslated_ids) / items_per_page) if filtered_untranslated_ids else 1
    current_page_index = max(0, min(current_page_index, num_pages - 1))

    # Обновляем отображение текущей страницы с учетом нового фильтра
    if current_mode == 'markup': display_markup_page()
    elif current_mode == 'edit': display_edit_page()

    # Обновляем статус и навигацию
    filter_info = f"Фильтр: {os.path.basename(selected_filename_filter)}" if selected_filename_filter != ALL_FILES_FILTER else "Фильтр: Все"
    update_status(f"{filter_info} | Всего: {len(all_trans_units)} | Без перевода (всего): {len(untranslated_ids)} | Без перевода (фильтр): {len(filtered_untranslated_ids)}")
    update_navigation_buttons_state() # Обновит метку страницы и кнопки

# --- Функции отображения страниц ---

def display_markup_page():
    """Отображает текущую страницу в режиме разметки XML (с учетом фильтра)."""
    global current_page_units_map, editor_textbox, current_page_index
    global filtered_untranslated_ids, items_per_page, all_trans_units
    if editor_textbox is None: return

    editor_textbox.configure(state=tk.NORMAL)
    current_page_units_map.clear() # Очищаем карту текущей страницы

    if not filtered_untranslated_ids:
        set_editor_text_highlighted(editor_textbox, "<нет непереведенных строк для отображения (учитывая фильтр)>")
        update_navigation_buttons_state() # Обновит метку на "Страница: - / -"
        return

    num_pages = math.ceil(len(filtered_untranslated_ids) / items_per_page)
    # Убедимся, что индекс в пределах допустимого (могло измениться из-за фильтра/сохранения)
    current_page_index = max(0, min(current_page_index, num_pages - 1))
    update_navigation_buttons_state() # Обновит метку и кнопки навигации

    start_idx = current_page_index * items_per_page
    end_idx = min(start_idx + items_per_page, len(filtered_untranslated_ids))
    page_ids = filtered_untranslated_ids[start_idx:end_idx] # Берем ID из отфильтрованного списка

    page_xml_parts = []
    # Создаем карту всех юнитов для быстрого доступа по ID
    id_to_unit_map = {unit.get("id"): unit for unit in all_trans_units if unit.get("id")}

    for unit_id in page_ids:
        unit = id_to_unit_map.get(unit_id)
        if unit is not None:
            # Добавляем юнит в карту ТЕКУЩЕЙ страницы для последующего сохранения/перевода
            current_page_units_map[unit_id] = unit
            try:
                # Сериализуем конкретный <trans-unit> элемент
                xml_string = ET.tostring(
                    unit,
                    encoding='unicode',    # Используем unicode для строки Python
                    pretty_print=True,     # Форматируем для читаемости
                    xml_declaration=False  # Не добавляем <?xml...> для каждого юнита
                ).strip()
                page_xml_parts.append(xml_string)
            except Exception as e:
                print(f"{Fore.RED}Ошибка сериализации <trans-unit> ID '{unit_id}': {e}{Style.RESET_ALL}")
                traceback.print_exc()
                page_xml_parts.append(f"<!-- Ошибка отображения unit ID: {unit_id} ({e}) -->")
        else:
            # Этого не должно происходить, если filtered_untranslated_ids синхронизирован с all_trans_units
            print(f"{Fore.YELLOW}Предупреждение: Не найден <trans-unit> для ID '{unit_id}' в общем списке при отображении.{Style.RESET_ALL}")

    full_xml_block = "\n\n".join(page_xml_parts) # Разделяем юниты двойным переносом строки
    set_editor_text_highlighted(editor_textbox, full_xml_block)
    editor_textbox.yview_moveto(0.0) # Прокрутка вверх
    # update_navigation_buttons_state() # Уже вызван выше


def display_edit_page():
    """Отображает текущую страницу в режиме простого текста (с учетом фильтра)."""
    global current_page_units_map, editor_textbox, current_page_index
    global filtered_untranslated_ids, items_per_page, all_trans_units
    if editor_textbox is None: return

    editor_textbox.configure(state=tk.NORMAL)
    current_page_units_map.clear()
    target_widget = _get_inner_text_widget()

    # Отключаем подсветку синтаксиса XML в режиме текста
    if PYGMENTS_AVAILABLE and target_widget:
        for tag in target_widget.tag_names():
            if tag.startswith("Token_"):
                 try: target_widget.tag_delete(tag)
                 except tk.TclError: pass

    if not filtered_untranslated_ids:
        set_editor_text_highlighted(editor_textbox, "<нет непереведенных строк для отображения (учитывая фильтр)>")
        update_navigation_buttons_state()
        return

    num_pages = math.ceil(len(filtered_untranslated_ids) / items_per_page)
    current_page_index = max(0, min(current_page_index, num_pages - 1))
    update_navigation_buttons_state()

    start_idx = current_page_index * items_per_page
    end_idx = min(start_idx + items_per_page, len(filtered_untranslated_ids))
    page_ids = filtered_untranslated_ids[start_idx:end_idx]

    text_content = []
    id_to_unit_map = {unit.get("id"): unit for unit in all_trans_units if unit.get("id")}

    for unit_id in page_ids:
        unit = id_to_unit_map.get(unit_id)
        if unit is not None:
            current_page_units_map[unit_id] = unit # Добавляем в карту текущей страницы
            # Используем itertext для source и target, чтобы захватить текст из возможных вложенных тегов
            source_node = unit.find("xliff:source", namespaces=LXML_NSMAP)
            source_text = "".join(source_node.itertext()).strip() if source_node is not None else ""

            target_node = unit.find("xliff:target", namespaces=LXML_NSMAP)
            target_text = "".join(target_node.itertext()).strip() if target_node is not None else "" # Получаем существующий текст target

            text_content.append(f"ID: {unit_id}")
            text_content.append(f"SOURCE: {source_text}")
            text_content.append(f"TARGET: {target_text}") # Отображаем текущий target
            text_content.append('-'*30)
        else:
            print(f"{Fore.YELLOW}Предупреждение: Не найден <trans-unit> для ID '{unit_id}' в общем списке при отображении.{Style.RESET_ALL}")

    full_text_block = "\n".join(text_content)
    # Используем set_editor_text_highlighted без подсветки, т.к. режим 'edit'
    set_editor_text_highlighted(editor_textbox, full_text_block)
    editor_textbox.yview_moveto(0.0)
    # update_navigation_buttons_state() # Уже вызван выше


# --- Функции сохранения страниц ---

def save_markup_page_data(force_check=False):
    """Парсит XML из редактора (разметка) и обновляет lxml В ПАМЯТИ."""
    global current_page_units_map, is_dirty, editor_textbox, save_button, untranslated_ids, all_trans_units
    inner_widget = _get_inner_text_widget()
    if not current_page_units_map or current_mode != 'markup': return True # Нечего сохранять для этой страницы/режима

    textbox_modified = False
    if inner_widget:
         try: textbox_modified = inner_widget.edit_modified()
         except tk.TclError: pass
    # Сохраняем, если force_check=True ИЛИ если текст был модифицирован
    if not force_check and not textbox_modified:
        return True

    edited_xml_string = editor_textbox.get("1.0", "end-1c").strip() if editor_textbox else ""

    # Добавляем корневой элемент с нужным пространством имен для парсинга фрагмента
    root_ns_decl = f"xmlns:xliff='{LXML_NSMAP['xliff']}'" if LXML_NSMAP.get('xliff') else ""
    xml_to_parse = f"<root {root_ns_decl}>{edited_xml_string}</root>"
    updated_ids_on_page = set(); any_change_made_in_memory = False
    successfully_parsed = False

    try:
        parser = ET.XMLParser(remove_blank_text=False, strip_cdata=False, resolve_entities=False)
        edited_root = ET.fromstring(xml_to_parse, parser=parser)
        # Получаем все trans-unit непосредственно под <root>
        edited_units = edited_root.xpath("./xliff:trans-unit", namespaces=LXML_NSMAP)
        successfully_parsed = True # Если дошли сюда, парсинг успешен

        # Если парсинг прошел, но юнитов нет, а текст был, это ошибка структуры
        if not edited_units and edited_xml_string:
             raise ValueError("Не найдено <trans-unit> в отредактированном тексте, хотя текст не пуст.")

        # Собираем ID юнитов, найденных в редакторе
        found_ids_in_editor = set()
        id_to_edited_unit = {}
        for edited_unit in edited_units:
            unit_id = edited_unit.get("id")
            if not unit_id:
                raise ValueError("<trans-unit> без атрибута 'id' найден в редакторе.")
            if unit_id in found_ids_in_editor:
                 raise ValueError(f"Дублирующийся ID '{unit_id}' найден в редакторе.")
            found_ids_in_editor.add(unit_id)
            id_to_edited_unit[unit_id] = edited_unit

        # Карта оригинальных юнитов из общего списка
        id_to_original_unit_map = {unit.get("id"): unit for unit in all_trans_units if unit.get("id")}

        # Итерация по ID, которые *должны* были быть на этой странице (из current_page_units_map)
        ids_processed_on_page = set()
        for unit_id in current_page_units_map.keys():
            ids_processed_on_page.add(unit_id)
            original_unit = id_to_original_unit_map.get(unit_id)
            edited_unit = id_to_edited_unit.get(unit_id)

            if original_unit is None:
                 print(f"{Fore.RED}Критическая ошибка: Оригинальный <trans-unit> ID '{unit_id}' не найден в all_trans_units!{Style.RESET_ALL}")
                 continue

            if edited_unit is None:
                 print(f"{Fore.YELLOW}Предупреждение: <trans-unit> ID '{unit_id}' (ожидался на странице) не найден в редакторе. Изменения для него не сохранены.{Style.RESET_ALL}")
                 continue

            # Сравниваем оригинальный и отредактированный юниты
            try:
                original_unit_str = ET.tostring(original_unit, encoding='unicode', pretty_print=True)
                edited_unit_str = ET.tostring(edited_unit, encoding='unicode', pretty_print=True)
            except Exception as ser_err:
                 print(f"{Fore.RED}Ошибка сериализации при сравнении ID {unit_id}: {ser_err}{Style.RESET_ALL}")
                 continue # Пропускаем этот юнит

            if original_unit_str != edited_unit_str:
                parent = original_unit.getparent()
                if parent is not None:
                    try:
                        index = parent.index(original_unit)
                        parent.remove(original_unit)
                        parent.insert(index, edited_unit)
                    except ValueError:
                        print(f"{Fore.RED}Ошибка: не удалось найти индекс original_unit ID '{unit_id}' у родителя. Замена через replace.{Style.RESET_ALL}")
                        parent.replace(original_unit, edited_unit)

                    # Обновляем ссылку в all_trans_units (важно!)
                    try:
                        idx_in_all = all_trans_units.index(original_unit)
                        all_trans_units[idx_in_all] = edited_unit
                    except ValueError:
                        print(f"{Fore.RED}Критическая ошибка: original_unit ID '{unit_id}' не найден в all_trans_units при замене!{Style.RESET_ALL}")
                        found_in_all = False
                        for i, u in enumerate(all_trans_units):
                             if u.get("id") == unit_id:
                                 all_trans_units[i] = edited_unit
                                 found_in_all = True
                                 print(f"{Fore.YELLOW}Предупреждение: Замена в all_trans_units выполнена по ID.{Style.RESET_ALL}")
                                 break
                        if not found_in_all:
                             print(f"{Fore.RED}Ошибка: Не удалось обновить all_trans_units для ID '{unit_id}'.{Style.RESET_ALL}")

                    # Обновляем карту ID -> filename, если note изменился
                    note_node = edited_unit.find("xliff:note", namespaces=LXML_NSMAP)
                    new_filename = None
                    if note_node is not None and note_node.text:
                         match = NOTE_FILE_REGEX.match(note_node.text.strip())
                         if match: new_filename = match.group(1).strip()
                    if new_filename: unit_id_to_filename_map[unit_id] = new_filename
                    elif unit_id in unit_id_to_filename_map:
                         del unit_id_to_filename_map[unit_id]

                    any_change_made_in_memory = True
                    updated_ids_on_page.add(unit_id)
                else:
                    print(f"{Fore.RED}Критическая ошибка: Не найден родитель для <trans-unit> ID {unit_id}. Замена невозможна.{Style.RESET_ALL}")

        # Проверяем ID, которые были в редакторе, но не ожидались на этой странице
        new_ids_in_editor = found_ids_in_editor - ids_processed_on_page
        if new_ids_in_editor:
             print(f"{Fore.YELLOW}Предупреждение: ID из редактора не ожидались на этой странице и были проигнорированы: {', '.join(new_ids_in_editor)}.{Style.RESET_ALL}")

        if any_change_made_in_memory:
            print(f"Обновлено {len(updated_ids_on_page)} строк в памяти (разметка).")
            is_dirty = True # Устанавливаем глобальный флаг
            if save_button: save_button.configure(state=tk.NORMAL)

            # Обновляем МАСТЕР-список untranslated_ids после изменений
            ids_to_remove_from_untranslated = set()
            ids_to_add_to_untranslated = set()
            # Перепроверяем статус перевода для ИЗМЕНЕННЫХ юнитов
            for unit_id in updated_ids_on_page:
                 edited_unit = None
                 for u in all_trans_units:
                      if u.get("id") == unit_id:
                           edited_unit = u
                           break
                 if edited_unit:
                     target = edited_unit.find("xliff:target", namespaces=LXML_NSMAP)
                     is_approved = target is not None and target.get('approved') == 'yes'
                     has_content = target is not None and target.xpath("normalize-space(.)")
                     is_currently_translated = has_content or is_approved
                     was_in_untranslated = unit_id in untranslated_ids
                     if is_currently_translated and was_in_untranslated:
                         ids_to_remove_from_untranslated.add(unit_id)
                     elif not is_currently_translated and not was_in_untranslated:
                         ids_to_add_to_untranslated.add(unit_id)

            if ids_to_remove_from_untranslated:
                 print(f"Удаление {len(ids_to_remove_from_untranslated)} ID из непереведенных...")
                 untranslated_ids = [uid for uid in untranslated_ids if uid not in ids_to_remove_from_untranslated]
            if ids_to_add_to_untranslated:
                 print(f"Добавление {len(ids_to_add_to_untranslated)} ID в непереведенные...")
                 current_untranslated_set = set(untranslated_ids)
                 new_untranslated_set = current_untranslated_set.union(set(ids_to_add_to_untranslated))
                 all_units_order = {u.get("id"): i for i, u in enumerate(all_trans_units)}
                 untranslated_ids = sorted(
                     list(new_untranslated_set),
                     key=lambda x: all_units_order.get(x, float('inf'))
                 )

            # После обновления untranslated_ids, переприменяем фильтр
            apply_current_filter(reset_page=False) # Обновит filtered_untranslated_ids и дисплей

            # Обновляем статус внизу
            update_status(f"Изменения стр. {current_page_index+1} сохранены в памяти. Всего: {len(all_trans_units)} | Без перевода: {len(untranslated_ids)}")
        else:
            print("Изменений на странице не обнаружено (разметка).")
        return True # Успешное сохранение (или нет изменений)

    except ET.XMLSyntaxError as e:
        messagebox.showerror("Ошибка парсинга XML", f"Не удалось разобрать XML из редактора:\n{e}")
        return False # Ошибка парсинга
    except ValueError as ve:
        messagebox.showerror("Ошибка данных", f"Ошибка в структуре отредакт. текста:\n{ve}")
        return False # Ошибка структуры (нет ID, дубликат ID)
    except Exception as e:
        messagebox.showerror("Ошибка обновления", f"Ошибка при обновлении данных (разметка):\n{e}\n{traceback.format_exc()}")
        return False # Другая ошибка

def save_edit_page_data(force_check=False):
    """Сохраняет изменения из редактора (текст) В ПАМЯТЬ."""
    global current_page_units_map, is_dirty, editor_textbox, save_button, untranslated_ids, all_trans_units
    inner_widget = _get_inner_text_widget()
    if not current_page_units_map or current_mode != 'edit': return True

    textbox_modified = False
    if inner_widget:
        try: textbox_modified = inner_widget.edit_modified()
        except tk.TclError: pass
    if not force_check and not textbox_modified:
        return True

    edited_text = editor_textbox.get("1.0", "end-1c") if editor_textbox else ""
    lines = edited_text.split('\n')
    parsed_targets = {}; current_id = None; current_target_lines = []; in_target_section = False

    try:
        # Парсинг текста из редактора (формат ID:, SOURCE:, TARGET:, ---)
        for line_number, line in enumerate(lines):
            line_strip = line.strip()

            if line.startswith("ID: "):
                if current_id is not None and in_target_section:
                    parsed_targets[current_id] = "\n".join(current_target_lines).rstrip()
                current_id = line[4:].strip()
                if not current_id: current_id = None
                current_target_lines = []
                in_target_section = False
            elif line.startswith("SOURCE: "):
                in_target_section = False
            elif line.startswith("TARGET: "):
                if current_id is None: continue
                in_target_section = True
                current_target_lines.append(line[8:])
            elif line_strip == '-'*30:
                if current_id is not None and in_target_section:
                     parsed_targets[current_id] = "\n".join(current_target_lines).rstrip()
                current_id = None
                current_target_lines = []
                in_target_section = False
            elif in_target_section:
                 if current_id is None: continue
                 current_target_lines.append(line)

        # Сохраняем последний таргет, если файл закончился без разделителя
        if current_id is not None and in_target_section:
             parsed_targets[current_id] = "\n".join(current_target_lines).rstrip()

    except Exception as e:
        messagebox.showerror("Ошибка парсинга текста", f"Ошибка разбора текста редактора:\n{e}\n{traceback.format_exc()}")
        return False

    updated_ids_on_page = set(); any_change_made_in_memory = False
    id_to_original_unit_map = {unit.get("id"): unit for unit in all_trans_units if unit.get("id")}

    ids_processed_on_page = set()
    for unit_id in current_page_units_map.keys():
        ids_processed_on_page.add(unit_id)
        original_unit = id_to_original_unit_map.get(unit_id)
        if original_unit is None:
            print(f"{Fore.RED}Критическая ошибка: Оригинальный <trans-unit> ID '{unit_id}' не найден в all_trans_units!{Style.RESET_ALL}")
            continue

        if unit_id in parsed_targets:
            new_target_text = parsed_targets[unit_id]
            target_node = original_unit.find("xliff:target", namespaces=LXML_NSMAP)

            current_target_text = ""
            if target_node is not None:
                current_target_text = "".join(target_node.itertext()).rstrip()

            if current_target_text != new_target_text:
                 if target_node is None:
                     target_node = ET.Element(f"{{{LXML_NSMAP['xliff']}}}target")
                     source_node = original_unit.find("xliff:source", namespaces=LXML_NSMAP)
                     note_node = original_unit.find("xliff:note", namespaces=LXML_NSMAP)
                     insert_point = source_node if source_node is not None else note_node
                     if insert_point is not None:
                         insert_point.addnext(target_node)
                     else:
                         last_element = original_unit.xpath("./*[last()]")
                         if last_element: last_element[0].addnext(target_node)
                         else: original_unit.append(target_node)

                 target_node.clear()
                 target_node.text = new_target_text if new_target_text else None # Set text or None
                 if 'approved' in target_node.attrib: del target_node.attrib['approved']

                 any_change_made_in_memory = True
                 updated_ids_on_page.add(unit_id)
        else:
            print(f"{Fore.YELLOW}Предупреждение: ID '{unit_id}' (ожидался на странице) не найден в тексте редактора. Изменения для него не сохранены.{Style.RESET_ALL}")

    ids_only_in_editor = set(parsed_targets.keys()) - ids_processed_on_page
    if ids_only_in_editor:
        print(f"{Fore.YELLOW}Предупреждение: ID найдены в редакторе, но не ожидались на этой странице: {', '.join(ids_only_in_editor)}. Они были проигнорированы.{Style.RESET_ALL}")

    if any_change_made_in_memory:
        print(f"Обновлено {len(updated_ids_on_page)} строк в памяти (редактирование).")
        is_dirty = True
        if save_button: save_button.configure(state=tk.NORMAL)

        # Обновляем МАСТЕР-список untranslated_ids
        ids_to_remove_from_untranslated = set()
        ids_to_add_to_untranslated = set()
        for unit_id in updated_ids_on_page:
            edited_unit = None
            for u in all_trans_units:
                 if u.get("id") == unit_id: edited_unit = u; break
            if edited_unit:
                target = edited_unit.find("xliff:target", namespaces=LXML_NSMAP)
                is_approved = target is not None and target.get('approved') == 'yes'
                has_content = target is not None and target.xpath("normalize-space(.)")
                is_currently_translated = has_content or is_approved
                was_in_untranslated = unit_id in untranslated_ids
                if is_currently_translated and was_in_untranslated:
                    ids_to_remove_from_untranslated.add(unit_id)
                elif not is_currently_translated and not was_in_untranslated:
                    ids_to_add_to_untranslated.add(unit_id)

        if ids_to_remove_from_untranslated:
            print(f"Удаление {len(ids_to_remove_from_untranslated)} ID из непереведенных...")
            untranslated_ids = [uid for uid in untranslated_ids if uid not in ids_to_remove_from_untranslated]
        if ids_to_add_to_untranslated:
            print(f"Добавление {len(ids_to_add_to_untranslated)} ID в непереведенные...")
            current_untranslated_set = set(untranslated_ids)
            new_untranslated_set = current_untranslated_set.union(set(ids_to_add_to_untranslated))
            all_units_order = {u.get("id"): i for i, u in enumerate(all_trans_units)}
            untranslated_ids = sorted(
                list(new_untranslated_set),
                key=lambda x: all_units_order.get(x, float('inf'))
            )

        # Переприменяем фильтр и обновляем дисплей
        apply_current_filter(reset_page=False)

        # Обновляем статус
        update_status(f"Изменения стр. {current_page_index+1} сохранены в памяти. Всего: {len(all_trans_units)} | Без перевода: {len(untranslated_ids)}")

    else:
        print("Изменений на странице не обнаружено (редактирование).")
    return True # Успех (или нет изменений)


# --- Функция отображения статистики ---
def show_statistics_window():
    """Отображает окно со статистикой перевода."""
    global all_trans_units, untranslated_ids, main_window, xliff_tree, xliff_filepath

    if not xliff_tree:
        messagebox.showinfo("Нет данных", "Сначала загрузите XLIFF файл.")
        return

    # Используем актуальную длину мастер-списка непереведенных
    total_units = len(all_trans_units)
    untranslated_count = len(untranslated_ids)
    translated_count = total_units - untranslated_count
    progress_value = (translated_count / total_units) if total_units > 0 else 0

    # Создаем новое Toplevel окно
    stats_win = ctk.CTkToplevel(main_window)
    stats_win.title("Статистика")
    stats_win.geometry("400x320") # Чуть шире для имени файла
    stats_win.resizable(False, False)
    stats_win.transient(main_window) # Делаем модальным относительно главного
    stats_win.grab_set() # Захватываем фокус

    # --- Заголовок внутри окна ---
    title_font = ctk.CTkFont(size=14, weight="bold")
    title_label = ctk.CTkLabel(stats_win, text="Статистика перевода", font=title_font, anchor="center")
    title_label.pack(pady=(15, 10), padx=15, fill='x')

    # --- Метки с информацией ---
    info_frame = ctk.CTkFrame(stats_win, fg_color="transparent")
    info_frame.pack(pady=5, padx=15, fill='x')
    info_frame.grid_columnconfigure(0, weight=1) # Метка слева
    info_frame.grid_columnconfigure(1, weight=0) # Значение справа

    # Имя файла
    ctk.CTkLabel(info_frame, text="Файл:", anchor="w").grid(row=0, column=0, sticky='w', pady=3)
    file_label = ctk.CTkLabel(info_frame, text=os.path.basename(xliff_filepath), anchor="e", wraplength=250)
    file_label.grid(row=0, column=1, sticky='e', pady=3, padx=(10,0))
    # Подсказка для полного пути (Optional)
    # file_tooltip = Hovertip(file_label, xliff_filepath) if 'Hovertip' in globals() else None

    # Языки
    ctk.CTkLabel(info_frame, text="Языки:", anchor="w").grid(row=1, column=0, sticky='w', pady=3)
    ctk.CTkLabel(info_frame, text=f"{detected_source_lang} → {detected_target_lang}", anchor="e").grid(row=1, column=1, sticky='e', pady=3, padx=(10,0))

    # Статистика
    ctk.CTkLabel(info_frame, text="Всего строк (trans-unit):", anchor="w").grid(row=2, column=0, sticky='w', pady=3)
    ctk.CTkLabel(info_frame, text=f"{total_units}", anchor="e").grid(row=2, column=1, sticky='e', pady=3, padx=(10,0))

    ctk.CTkLabel(info_frame, text="Не переведено строк:", anchor="w").grid(row=3, column=0, sticky='w', pady=3)
    ctk.CTkLabel(info_frame, text=f"{untranslated_count}", anchor="e").grid(row=3, column=1, sticky='e', pady=3, padx=(10,0))

    ctk.CTkLabel(info_frame, text="Переведено строк:", anchor="w").grid(row=4, column=0, sticky='w', pady=3)
    ctk.CTkLabel(info_frame, text=f"{translated_count}", anchor="e").grid(row=4, column=1, sticky='e', pady=3, padx=(10,0))

    ctk.CTkLabel(info_frame, text="Прогресс перевода:", anchor="w").grid(row=5, column=0, sticky='w', pady=3)
    ctk.CTkLabel(info_frame, text=f"{progress_value*100:.2f}%", anchor="e").grid(row=5, column=1, sticky='e', pady=3, padx=(10,0))


    # --- Прогресс-бар ---
    stats_progress_bar = ctk.CTkProgressBar(stats_win, orientation="horizontal", height=15)
    stats_progress_bar.pack(pady=(15, 10), padx=15, fill='x')
    stats_progress_bar.set(progress_value) # Устанавливаем значение от 0 до 1

    # --- Кнопка Закрыть ---
    close_button = ctk.CTkButton(stats_win, text="Закрыть", command=stats_win.destroy, width=100)
    close_button.pack(pady=(5, 15))


    stats_win.focus_set() # Устанавливаем фокус на окно статистики
    stats_win.bind("<Escape>", lambda e: stats_win.destroy()) # Закрытие по Escape

    # --- Центрирование окна статистики ---
    main_window.update_idletasks()
    stats_win.update_idletasks()

    main_win_x = main_window.winfo_x()
    main_win_y = main_window.winfo_y()
    main_win_width = main_window.winfo_width()
    main_win_height = main_window.winfo_height()
    stats_win_width = stats_win.winfo_width()
    stats_win_height = stats_win.winfo_height()

    pos_x = main_win_x + (main_win_width // 2) - (stats_win_width // 2)
    pos_y = main_win_y + (main_win_height // 2) - (stats_win_height // 2)

    screen_width = main_window.winfo_screenwidth()
    screen_height = main_window.winfo_screenheight()
    pos_x = max(0, min(pos_x, screen_width - stats_win_width))
    pos_y = max(0, min(pos_y, screen_height - stats_win_height))

    stats_win.geometry(f"+{pos_x}+{pos_y}")

# --- Класс для подсказок (если нужен, tkinter 3.7+) ---
try:
    # tix might be deprecated, prefer ttk Tooltip if available and styled
    # from tkinter.tix import Hovertip # type: ignore
    pass # Keep it simple for now
except ImportError:
    pass

# --- Создание основного окна и виджетов ---
def create_main_window():
    """Создает и настраивает главное окно и виджеты."""
    global main_window, editor_textbox, prev_button, next_button, page_label, page_var
    global page_entry, go_button, page_size_var, page_size_entry, page_size_button
    global status_label, save_button, open_button, markup_mode_button, edit_mode_button
    global translate_button, stats_button, file_filter_combobox, translator_combobox
    global font_size_increase_button, font_size_decrease_button, current_font_size

    main_window = ctk.CTk()
    main_window.title("XLIFF Paged Editor")
    main_window.geometry("1100x750") # Немного увеличим размер по умолчанию

    # --- Top Frame ---
    top_frame = ctk.CTkFrame(main_window, fg_color="transparent")
    top_frame.pack(side=tk.TOP, fill=tk.X, padx=10, pady=(10, 5))
    top_frame.grid_columnconfigure(1, weight=1) # Центральная часть растягивается

    # --- Left Buttons Frame (Modes, Translate, Stats, Font) ---
    left_buttons_frame = ctk.CTkFrame(top_frame, fg_color="transparent")
    left_buttons_frame.grid(row=0, column=0, padx=(0, 10), sticky="w")

    markup_mode_button = ctk.CTkButton(left_buttons_frame, text="Разметка", command=lambda: set_mode('markup'), width=100)
    markup_mode_button.pack(side=tk.LEFT, padx=(0, 5))
    edit_mode_button = ctk.CTkButton(left_buttons_frame, text="Текст", command=lambda: set_mode('edit'), width=80)
    edit_mode_button.pack(side=tk.LEFT, padx=(0, 5))

    # Группа перевода
    translate_group = ctk.CTkFrame(left_buttons_frame, fg_color="transparent")
    translate_group.pack(side=tk.LEFT, padx=(0, 5))
    translate_button = ctk.CTkButton(translate_group, text="Перевести стр.", command=translate_current_page, width=120)
    translate_button.pack(side=tk.LEFT, padx=(0, 3))
    translator_combobox = ctk.CTkComboBox(
        translate_group,
        values=TRANSLATOR_SERVICES if TRANSLATION_AVAILABLE else ["N/A"],
        width=90,
        command=on_translator_selected # Функция для обновления selected_translator_service
    )
    translator_combobox.pack(side=tk.LEFT)
    if TRANSLATION_AVAILABLE:
        translator_combobox.set(DEFAULT_TRANSLATOR_SERVICE)
        on_translator_selected(DEFAULT_TRANSLATOR_SERVICE) # Устанавливаем начальное значение
    else:
        translator_combobox.configure(state=tk.DISABLED)
        translate_button.configure(state=tk.DISABLED, text="Перевод (N/A)")

    # Группа статистики и шрифта
    misc_group = ctk.CTkFrame(left_buttons_frame, fg_color="transparent")
    misc_group.pack(side=tk.LEFT, padx=(10, 5))
    stats_button = ctk.CTkButton(misc_group, text="Статистика", command=show_statistics_window, width=100)
    stats_button.pack(side=tk.LEFT, padx=(0, 10))

    font_size_decrease_button = ctk.CTkButton(misc_group, text="A-", command=lambda: change_font_size(-1), width=30)
    font_size_decrease_button.pack(side=tk.LEFT, padx=(0, 2))
    font_size_increase_button = ctk.CTkButton(misc_group, text="A+", command=lambda: change_font_size(1), width=30)
    font_size_increase_button.pack(side=tk.LEFT, padx=(0, 5))

    # --- Right Frame (Filter, Open) ---
    right_frame = ctk.CTkFrame(top_frame, fg_color="transparent")
    right_frame.grid(row=0, column=2, padx=(10, 0), sticky="e")

    # Фильтр файлов
    file_filter_label = ctk.CTkLabel(right_frame, text="Фильтр:")
    file_filter_label.pack(side=tk.LEFT, padx=(0, 3))
    file_filter_combobox = ctk.CTkComboBox(
        right_frame,
        values=[ALL_FILES_FILTER],
        command=on_file_filter_change,
        width=180,
        state=tk.DISABLED # Изначально выключен
    )
    file_filter_combobox.pack(side=tk.LEFT, padx=(0, 10))
    file_filter_combobox.set(ALL_FILES_FILTER)

    # Кнопка Открыть
    open_button = ctk.CTkButton(right_frame, text="Открыть XLIFF...", command=load_xliff, width=120)
    open_button.pack(side=tk.LEFT)

    # --- Bottom Frame (Status and Save) ---
    bottom_frame_outer = ctk.CTkFrame(main_window)
    bottom_frame_outer.pack(side=tk.BOTTOM, fill=tk.X, padx=0, pady=0)
    bottom_frame_outer.grid_columnconfigure(0, weight=1) # Статус растягивается

    status_label = ctk.CTkLabel(bottom_frame_outer, text="Загрузите XLIFF файл...", anchor=tk.W)
    status_label.grid(row=0, column=0, padx=(10, 5), pady=5, sticky="ew")

    save_button = ctk.CTkButton(bottom_frame_outer, text="Сохранить XLIFF", command=save_xliff, width=130)
    save_button.grid(row=0, column=1, padx=(5, 10), pady=5, sticky="e")
    save_button.configure(state=tk.DISABLED)

    # --- Navigation Frame ---
    nav_frame = ctk.CTkFrame(main_window, fg_color="transparent")
    nav_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=(0, 5))

    # Центрируем навигацию
    nav_content_frame = ctk.CTkFrame(nav_frame, fg_color="transparent")
    nav_content_frame.pack(anchor=tk.CENTER)

    _nav_font = ctk.CTkFont(size=11)

    prev_button = ctk.CTkButton(nav_content_frame, text="<< Пред.", command=go_to_prev_page, width=70, font=_nav_font)
    prev_button.pack(side=tk.LEFT, padx=(0, 2))

    page_label = ctk.CTkLabel(nav_content_frame, text="Страница: - / -", width=150, font=_nav_font, anchor=tk.CENTER)
    page_label.pack(side=tk.LEFT, padx=2)

    page_var = tk.StringVar()
    page_entry = ctk.CTkEntry(nav_content_frame, textvariable=page_var, width=45, justify=tk.CENTER, font=_nav_font)
    page_entry.pack(side=tk.LEFT, padx=1)
    page_entry.bind("<Return>", go_to_page)

    go_button = ctk.CTkButton(nav_content_frame, text="Перейти", command=go_to_page, width=60, font=_nav_font)
    go_button.pack(side=tk.LEFT, padx=2)

    next_button = ctk.CTkButton(nav_content_frame, text="След. >>", command=go_to_next_page, width=70, font=_nav_font)
    next_button.pack(side=tk.LEFT, padx=(2, 15)) # Отступ справа

    page_size_label = ctk.CTkLabel(nav_content_frame, text="Строк:", font=_nav_font)
    page_size_label.pack(side=tk.LEFT, padx=(5, 1))

    page_size_var = tk.StringVar(value=str(items_per_page))
    page_size_entry = ctk.CTkEntry(nav_content_frame, textvariable=page_size_var, width=45, justify=tk.CENTER, font=_nav_font)
    page_size_entry.pack(side=tk.LEFT, padx=(1, 2))
    page_size_entry.bind("<Return>", update_page_size)

    page_size_button = ctk.CTkButton(nav_content_frame, text="Прим.", command=update_page_size, width=50, font=_nav_font)
    page_size_button.pack(side=tk.LEFT, padx=2)

    # --- Text Editor ---
    editor_frame = ctk.CTkFrame(main_window, fg_color="transparent")
    editor_frame.pack(expand=True, fill=tk.BOTH, padx=10, pady=(0, 5))

    editor_font = ctk.CTkFont(family="Consolas", size=current_font_size)

    editor_textbox = ctk.CTkTextbox(
        editor_frame,
        wrap=tk.NONE,
        undo=True,
        font=editor_font,
        border_width=1,
        padx=5,
        pady=5
    )

    editor_scrollbar_y = ctk.CTkScrollbar(editor_frame, command=editor_textbox.yview)
    editor_scrollbar_y.pack(side=tk.RIGHT, fill=tk.Y)
    editor_textbox.configure(yscrollcommand=editor_scrollbar_y.set)
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
            can_modify = xliff_tree is not None
            has_clipboard = False
            has_selection = False
            is_empty = True
            try: has_clipboard = bool(main_window.clipboard_get())
            except: pass
            try: has_selection = bool(text_widget.tag_ranges(tk.SEL))
            except: pass
            try: is_empty = not bool(text_widget.get("1.0", tk.END + "-1c").strip())
            except: pass

            widget_state = text_widget.cget("state")
            can_modify = can_modify and (widget_state == tk.NORMAL)

            context_menu.entryconfigure("Вырезать", state=tk.NORMAL if can_modify and has_selection else tk.DISABLED)
            context_menu.entryconfigure("Копировать", state=tk.NORMAL if has_selection else tk.DISABLED)
            context_menu.entryconfigure("Вставить", state=tk.NORMAL if can_modify and has_clipboard else tk.DISABLED)
            context_menu.entryconfigure("Выделить все", state=tk.NORMAL if not is_empty else tk.DISABLED)

            if has_selection or (can_modify and has_clipboard) or not is_empty:
                 context_menu.tk_popup(event.x_root, event.y_root)

        text_widget.bind("<Button-3>", show_context_menu)
        text_widget.bind("<Button-2>", show_context_menu)

        main_window.bind_all("<Control-a>", select_all_text); main_window.bind_all("<Control-A>", select_all_text)
        main_window.bind_all("<Control-x>", cut_text); main_window.bind_all("<Control-X>", cut_text)
        main_window.bind_all("<Control-c>", copy_text); main_window.bind_all("<Control-C>", copy_text)
        main_window.bind_all("<Control-v>", paste_text); main_window.bind_all("<Control-V>", paste_text)
        main_window.bind_all("<Command-a>", select_all_text); main_window.bind_all("<Command-A>", select_all_text)
        main_window.bind_all("<Command-x>", cut_text); main_window.bind_all("<Command-X>", cut_text)
        main_window.bind_all("<Command-c>", copy_text); main_window.bind_all("<Command-C>", copy_text)
        main_window.bind_all("<Command-v>", paste_text); main_window.bind_all("<Command-V>", paste_text)

        main_window.bind_all("<Control-s>", lambda event: save_xliff()); main_window.bind_all("<Control-S>", lambda event: save_xliff())
        main_window.bind_all("<Command-s>", lambda event: save_xliff()); main_window.bind_all("<Command-S>", lambda event: save_xliff())

        text_widget.bind("<<Modified>>", handle_text_modification)
    else:
        print(f"{Fore.RED}Критическая ошибка: Не удалось получить внутренний tk.Text! Функционал будет ограничен.{Style.RESET_ALL}")

    # --- Initial State ---
    reset_state()
    set_mode(DEFAULT_MODE, force_update=True)
    main_window.protocol("WM_DELETE_WINDOW", on_closing)
    return main_window

# --- Управление режимами ---
def set_mode(mode, force_update=False):
    """Переключает режим редактора ('markup' или 'edit')."""
    global current_mode, markup_mode_button, edit_mode_button, editor_textbox, status_label
    global current_page_index

    if not xliff_tree and not force_update:
        active_color = ctk.ThemeManager.theme["CTkButton"]["fg_color"]
        inactive_color = ctk.ThemeManager.theme["CTkButton"]["hover_color"]
        if mode == 'markup':
             if markup_mode_button: markup_mode_button.configure(fg_color=active_color)
             if edit_mode_button: edit_mode_button.configure(fg_color=inactive_color)
        elif mode == 'edit':
             if markup_mode_button: markup_mode_button.configure(fg_color=inactive_color)
             if edit_mode_button: edit_mode_button.configure(fg_color=active_color)
        return

    if not force_update and mode == current_mode: return

    if not force_update and xliff_tree:
        if not save_current_page_data_if_dirty(prompt_save=True):
            print("Смена режима отменена пользователем или из-за ошибки сохранения.")
            return

    print(f"Установка режима: {mode}")
    previous_mode = current_mode
    current_mode = mode

    if editor_textbox:
        active_color = ctk.ThemeManager.theme["CTkButton"]["fg_color"]
        inactive_color = ctk.ThemeManager.theme["CTkButton"]["hover_color"]

        if mode == 'markup':
            if markup_mode_button: markup_mode_button.configure(state=tk.DISABLED, fg_color=active_color)
            if edit_mode_button: edit_mode_button.configure(state=tk.NORMAL, fg_color=inactive_color)
            editor_textbox.configure(wrap=tk.NONE) # XML без переноса
            update_status("Режим: Разметка XML")
        elif mode == 'edit':
            if markup_mode_button: markup_mode_button.configure(state=tk.NORMAL, fg_color=inactive_color)
            if edit_mode_button: edit_mode_button.configure(state=tk.DISABLED, fg_color=active_color)
            editor_textbox.configure(wrap=tk.WORD) # Текст с переносом
            update_status("Режим: Редактирование текста")
        else:
            print(f"{Fore.RED}Ошибка: Неизвестный режим '{mode}'. Возврат к '{previous_mode}'.{Style.RESET_ALL}")
            current_mode = previous_mode
            set_mode(previous_mode, force_update=True)
            return

        if xliff_tree and (mode != previous_mode or force_update):
            if mode == 'markup': display_markup_page()
            elif mode == 'edit': display_edit_page()
            inner_widget = _get_inner_text_widget()
            if inner_widget:
                try: inner_widget.edit_modified(False)
                except tk.TclError: pass

        set_focus_on_editor()

    else: # При инициализации
         active_color = ctk.ThemeManager.theme["CTkButton"]["fg_color"]
         inactive_color = ctk.ThemeManager.theme["CTkButton"]["hover_color"]
         if mode == 'markup':
             if markup_mode_button: markup_mode_button.configure(state=tk.DISABLED, fg_color=active_color)
             if edit_mode_button: edit_mode_button.configure(state=tk.NORMAL, fg_color=inactive_color)
         elif mode == 'edit':
             if markup_mode_button: markup_mode_button.configure(state=tk.NORMAL, fg_color=inactive_color)
             if edit_mode_button: edit_mode_button.configure(state=tk.DISABLED, fg_color=active_color)

def handle_text_modification(event=None):
    """Обработчик события <<Modified>> от внутреннего tk.Text."""
    global is_dirty, save_button
    inner_widget = _get_inner_text_widget()
    if inner_widget:
        try:
            if inner_widget.edit_modified():
                 if not is_dirty:
                    is_dirty = True
                    print("* Обнаружено изменение текста, установлен флаг is_dirty.")
                 if save_button and save_button.cget('state') == tk.DISABLED:
                     save_button.configure(state=tk.NORMAL)
        except tk.TclError: pass

def on_translator_selected(choice):
    """Обновляет выбранный сервис перевода."""
    global selected_translator_service
    print(f"Выбран сервис перевода: {choice}")
    selected_translator_service = choice

def on_closing():
    """Обработчик события закрытия окна."""
    global is_dirty
    page_save_ok = save_current_page_data_if_dirty(prompt_save=False)
    if not page_save_ok:
        if not messagebox.askokcancel("Ошибка сохранения страницы",
                                      "Не удалось сохранить изменения на текущей странице из-за ошибки.\n"
                                      "Все равно выйти (изменения страницы будут потеряны)?",
                                      icon='warning'):
             return

    if is_dirty:
        result = messagebox.askyesnocancel("Выход",
                                           "Есть несохраненные изменения.\n"
                                           "Сохранить их в файл перед выходом?",
                                           icon='warning')
        if result is True: # Да
            save_xliff()
            if is_dirty: # Сохранение не удалось
                 if messagebox.askokcancel("Ошибка сохранения файла",
                                          "Не удалось сохранить изменения в файл.\n"
                                          "Все равно выйти (все изменения будут потеряны)?",
                                          icon='error'):
                     main_window.destroy()
                 else: return
            else: main_window.destroy() # Успешно сохранено
        elif result is False: # Нет
            if messagebox.askyesno("Подтверждение",
                                   "Вы уверены, что хотите выйти без сохранения изменений?",
                                   icon='warning'):
                 main_window.destroy()
            else: return
        else: # Отмена
            return
    else:
        main_window.destroy()

# --- Запуск приложения ---
if __name__ == "__main__":
    filepath_from_cli = None
    if len(sys.argv) > 1:
        filepath_from_cli = sys.argv[1]
        if not os.path.isfile(filepath_from_cli):
            print(f"{Fore.RED}Ошибка: Файл '{filepath_from_cli}' из командной строки не найден.{Style.RESET_ALL}")
            filepath_from_cli = None
        else:
            print(f"Файл из командной строки: {filepath_from_cli}")

    display_available = True
    try:
        _test_root = tk.Tk()
        _test_root.withdraw()
        _test_button = ctk.CTkButton(_test_root) # Check CTk integration
        _test_root.destroy()
        print("Проверка Tkinter и CustomTkinter прошла успешно.")
    except tk.TclError as e:
        if "no display name" in str(e) or "couldn't connect to display" in str(e):
             print(f"{Fore.RED}Ошибка Tkinter: Не удалось подключиться к дисплею.{Style.RESET_ALL}")
             display_available = False
             try: root_err = tk.Tk(); root_err.withdraw(); messagebox.showerror("Ошибка запуска", "Не удалось инициализировать графический интерфейс.\nУбедитесь, что дисплей доступен."); root_err.destroy()
             except Exception: pass
        else:
             print(f"{Fore.RED}Неожиданная ошибка Tcl/Tk при проверке дисплея:{Style.RESET_ALL}\n{e}")
             traceback.print_exc()
             display_available = False
             try: root_err = tk.Tk(); root_err.withdraw(); messagebox.showerror("Ошибка Tcl/Tk", f"Критическая ошибка Tcl/Tk:\n{e}\nЗапуск невозможен."); root_err.destroy()
             except Exception: pass
             sys.exit(1)

    if display_available:
        try:
            root = create_main_window()
            if root:
                if filepath_from_cli:
                    root.after(100, lambda: load_xliff(filepath_arg=filepath_from_cli))
                root.mainloop()
            else:
                print(f"{Fore.RED}Ошибка: Не удалось создать главное окно.{Style.RESET_ALL}")
                sys.exit(1)
        except tk.TclError as e:
             print(f"{Fore.RED}Критическая ошибка Tcl/Tk во время выполнения:{Style.RESET_ALL}")
             traceback.print_exc()
             try: root_err = tk.Tk(); root_err.withdraw(); messagebox.showerror("Критическая ошибка Tcl/Tk", f"Ошибка Tcl/Tk:\n{e}\nПриложение будет закрыто."); root_err.destroy()
             except Exception: pass
             sys.exit(1)
        except Exception as e:
             print(f"{Fore.RED}Критическая ошибка Python во время выполнения:{Style.RESET_ALL}")
             traceback.print_exc()
             try: root_err = tk.Tk(); root_err.withdraw(); messagebox.showerror("Критическая ошибка Python", f"Ошибка Python:\n{type(e).__name__}: {e}\nПриложение будет закрыто."); root_err.destroy()
             except Exception: pass
             sys.exit(1)
    else:
         print("Запуск GUI отменен из-за отсутствия или ошибки дисплея.")
         sys.exit(1)

# --- END OF FILE xliff_editor_gui.py ---