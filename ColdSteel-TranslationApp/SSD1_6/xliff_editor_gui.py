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
# import uuid # Removed, seems unused
import traceback
import time
import re # For parsing note tags and search

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
DEFAULT_MODE = "markup" # 'markup' или 'edit'
DEFAULT_STATUS_FILTER = "untranslated" # 'untranslated', 'translated', 'all'
TRANSLATION_DELAY_SECONDS = 0.15
NOTE_FILE_REGEX = re.compile(r"^File:\s*(.+)$", re.IGNORECASE)
ALL_FILES_FILTER = "--- Все файлы ---"
# --------------------

# --- Mappings for MyMemory ---
MYMEMORY_LANG_MAP = {
    "en": "en-US", "ru": "ru-RU", "ko": "ko-KR", "ja": "ja-JP",
    "zh": "zh-CN", "es": "es-ES", "fr": "fr-FR", "de": "de-DE",
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

LXML_NSMAP = {'xliff': 'urn:oasis:names:tc:xliff:document:1.2'}

# --- Основной класс приложения ---
class XliffEditorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("XLIFF Paged Editor")
        self.root.geometry("1400x800") # Increased width slightly

        # --- Состояние приложения ---
        self.xliff_tree = None
        self.xliff_root = None
        self.xliff_filepath = ""
        self.all_trans_units = []           # Список ВСЕХ <trans-unit> объектов lxml
        self.unit_status_map = {}           # Словарь {unit_id: 'untranslated' | 'translated' | 'approved'}
        self.unit_id_to_filename_map = {}   # Словарь {unit_id: filename}
        self.available_filenames = [ALL_FILES_FILTER] # Список доступных имен файлов для фильтра
        self.untranslated_filenames = set() # Множество имен файлов с непереведенными юнитами
        self.show_untranslated_files_only = False # Состояние переключателя фильтра файлов
        self.is_dirty = False               # Есть ли несохраненные изменения в памяти
        self.current_mode = DEFAULT_MODE    # 'markup' или 'edit'
        self.detected_source_lang = SOURCE_LANG
        self.detected_target_lang = TARGET_LANG
        self.selected_translator_service = DEFAULT_TRANSLATOR_SERVICE
        self.current_page_index = 0
        self.items_per_page = ITEMS_PER_PAGE_DEFAULT
        self.current_page_units_map = {}    # Словарь {unit_id: unit_element} для ТЕКУЩЕЙ отображаемой страницы
        self.filtered_display_ids = []      # ID юнитов, отображаемых после ВСЕХ фильтров (файл + статус)
        self.selected_filename_filter = ALL_FILES_FILTER # Текущий фильтр файла
        self.selected_status_filter = DEFAULT_STATUS_FILTER # Текущий фильтр статуса
        self.current_font_size = 11         # Начальный размер шрифта редактора
        self.search_term = ""               # Текущий термин для поиска
        self.last_search_pos = "1.0"        # Последняя позиция поиска в тексте

        # --- Переменные виджетов ---
        self.main_window = root # Alias for clarity in methods
        self.editor_textbox = None
        self.save_button = None
        self.open_button = None
        self.markup_mode_button = None
        self.edit_mode_button = None
        self.translate_button = None
        self.stats_button = None # Variable was present, creation was missing
        self.status_label = None
        self.page_label = None
        self.prev_button = None
        self.next_button = None
        self.page_entry = None
        self.go_button = None
        self.page_size_entry = None
        self.page_size_button = None
        self.page_var = tk.StringVar()
        self.page_size_var = tk.StringVar(value=str(self.items_per_page))
        self.file_filter_combobox = None
        self.show_untranslated_switch = None # Variable for the switch
        self.status_filter_combobox = None
        self.translator_combobox = None
        self.font_size_increase_button = None
        self.font_size_decrease_button = None
        self.search_entry = None
        self.find_next_button = None

        self._create_widgets()
        self.reset_state()
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    # --- Общие функции UI ---

    def update_status(self, message):
        if self.status_label:
            self.status_label.configure(text=message)
        if self.main_window:
            self.main_window.update_idletasks()

    def update_title(self):
        """Обновляет заголовок окна, добавляя '*' при наличии изменений."""
        if not self.main_window: return
        base_title = "XLIFF Paged Editor"
        if self.xliff_filepath:
            file_part = f" - {os.path.basename(self.xliff_filepath)}"
            lang_part = f" [{self.detected_source_lang}->{self.detected_target_lang}]"
            dirty_part = "*" if self.is_dirty else ""
            self.main_window.title(f"{base_title}{file_part}{lang_part}{dirty_part}")
        else:
            self.main_window.title(base_title)

    def set_dirty_flag(self, dirty_state):
        """Устанавливает флаг is_dirty и обновляет UI."""
        if self.is_dirty != dirty_state:
            self.is_dirty = dirty_state
            print(f"* Флаг is_dirty установлен в: {self.is_dirty}")
            self.update_title()
            if self.save_button:
                self.save_button.configure(state=tk.NORMAL if self.is_dirty else tk.DISABLED)

    def reset_state(self):
        """Сбрасывает состояние приложения."""
        self.xliff_tree = self.xliff_root = None
        self.xliff_filepath = ""
        self.all_trans_units = []
        self.unit_status_map = {}
        self.unit_id_to_filename_map = {}
        self.available_filenames = [ALL_FILES_FILTER]
        self.untranslated_filenames.clear()
        self.show_untranslated_files_only = False
        self.selected_filename_filter = ALL_FILES_FILTER
        self.selected_status_filter = DEFAULT_STATUS_FILTER
        self.current_page_units_map = {}
        self.filtered_display_ids = []
        self.current_page_index = 0
        self.items_per_page = ITEMS_PER_PAGE_DEFAULT
        self.page_size_var.set(str(self.items_per_page))
        self.set_dirty_flag(False)
        self.detected_source_lang = SOURCE_LANG
        self.detected_target_lang = TARGET_LANG
        self.search_term = ""
        self.last_search_pos = "1.0"

        if self.editor_textbox is not None:
            text_widget = self._get_inner_text_widget()
            self.editor_textbox.configure(state=tk.NORMAL)
            self.editor_textbox.delete("1.0", tk.END)
            self.editor_textbox.configure(state=tk.DISABLED)
            if text_widget:
                try: text_widget.edit_modified(False)
                except tk.TclError: pass

        if self.save_button: self.save_button.configure(state=tk.DISABLED)
        if self.prev_button: self.prev_button.configure(state=tk.DISABLED)
        if self.next_button: self.next_button.configure(state=tk.DISABLED)
        if self.page_entry: self.page_entry.configure(state=tk.DISABLED)
        if self.go_button: self.go_button.configure(state=tk.DISABLED)
        if self.page_size_entry: self.page_size_entry.configure(state=tk.DISABLED)
        if self.page_size_button: self.page_size_button.configure(state=tk.DISABLED)
        if self.translate_button: self.translate_button.configure(state=tk.DISABLED)
        if self.stats_button: self.stats_button.configure(state=tk.DISABLED) # Reset stats button state
        if self.page_var: self.page_var.set("")
        if self.page_label: self.page_label.configure(text="Страница: - / -")
        if self.file_filter_combobox:
            self.file_filter_combobox.configure(values=[ALL_FILES_FILTER], state=tk.DISABLED)
            self.file_filter_combobox.set(ALL_FILES_FILTER)
        # Reset switch state
        if self.show_untranslated_switch:
            self.show_untranslated_switch.deselect()
            self.show_untranslated_switch.configure(state=tk.DISABLED)
        if self.status_filter_combobox:
            status_map_internal_to_display = {"untranslated": "Непереведенные", "translated": "Переведенные", "approved": "Подтвержденные", "all": "Все статусы"}
            self.status_filter_combobox.set(status_map_internal_to_display.get(DEFAULT_STATUS_FILTER)) # Set display value
            self.status_filter_combobox.configure(state=tk.DISABLED)
        if self.search_entry:
            self.search_entry.delete(0, tk.END)
            self.search_entry.configure(state=tk.DISABLED)
        if self.find_next_button: self.find_next_button.configure(state=tk.DISABLED)

        self.update_status("Готово к загрузке файла.")
        self.update_title()
        self.set_mode(self.current_mode, force_update=True) # Reset mode button states


    def _get_inner_text_widget(self):
        """Вспомогательная функция для получения внутреннего tk.Text виджета."""
        if self.editor_textbox and hasattr(self.editor_textbox, '_textbox'):
            return self.editor_textbox._textbox
        return None

    def _check_inner_focus(self):
        """Проверяет, находится ли фокус на внутреннем tk.Text виджете."""
        inner_widget = self._get_inner_text_widget()
        if not inner_widget or not self.main_window: return False
        try: return self.main_window.focus_get() == inner_widget
        except Exception: return False

    # --- Контекстное меню и биндинги ---
    def can_cut_now(self):
        target_widget = self._get_inner_text_widget()
        if not target_widget: return False
        return (self.xliff_tree is not None and
                target_widget.cget("state") == tk.NORMAL and
                target_widget.tag_ranges(tk.SEL))

    def can_copy_now(self):
        target_widget = self._get_inner_text_widget()
        if not target_widget: return False
        return (target_widget.tag_ranges(tk.SEL))

    def can_paste_now(self):
        target_widget = self._get_inner_text_widget()
        if not target_widget: return False
        has_clipboard = False
        try: has_clipboard = bool(self.main_window.clipboard_get())
        except: pass
        return (self.xliff_tree is not None and
                target_widget.cget("state") == tk.NORMAL and
                has_clipboard)

    def select_all_text(self, event=None):
        target_widget = self._get_inner_text_widget()
        if not target_widget: return None
        if self._check_inner_focus():
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

    def cut_text(self, event=None):
        target_widget = self._get_inner_text_widget()
        if not target_widget: return 'break'
        can_cut = (self.xliff_tree is not None and
                   self._check_inner_focus() and
                   target_widget.cget("state") == tk.NORMAL and
                   target_widget.tag_ranges(tk.SEL))
        return None if can_cut else 'break'

    def copy_text(self, event=None):
        target_widget = self._get_inner_text_widget()
        if not target_widget: return 'break'
        can_copy = (self._check_inner_focus() and
                    target_widget.tag_ranges(tk.SEL))
        return None if can_copy else 'break'

    def paste_text(self, event=None):
        target_widget = self._get_inner_text_widget()
        if not target_widget: return 'break'
        can_paste = (self.xliff_tree is not None and
                     self._check_inner_focus() and
                     target_widget.cget("state") == tk.NORMAL)
        return None if can_paste else 'break'

    def set_focus_on_editor(self):
        """Устанавливает фокус на внутренний текстовый виджет."""
        inner_widget = self._get_inner_text_widget()
        if inner_widget:
            try: inner_widget.focus_set()
            except tk.TclError as e: print(f"Ошибка при установке фокуса: {e}")

    # --- Навигация и размер страницы ---
    def update_page_size(self, *args):
        """Обрабатывает изменение размера страницы."""
        if not self.xliff_tree: return
        try:
            new_size = int(self.page_size_var.get())
            if new_size > 0:
                page_modified = False
                inner_widget = self._get_inner_text_widget()
                if inner_widget:
                    try: page_modified = inner_widget.edit_modified()
                    except tk.TclError: pass

                if page_modified:
                    if not messagebox.askyesno("Несохраненные изменения", "Есть изменения на текущей странице. Сменить размер без сохранения этих изменений?"):
                        self.page_size_var.set(str(self.items_per_page))
                        return
                    else:
                        if not self.save_current_page_data_if_dirty(prompt_save=False):
                            messagebox.showerror("Ошибка", "Не удалось сохранить изменения. Смена размера отменена.")
                            self.page_size_var.set(str(self.items_per_page))
                            return
                        if inner_widget:
                            try: inner_widget.edit_modified(False)
                            except tk.TclError: pass

                current_first_item_global_index_in_filtered_list = self.current_page_index * self.items_per_page
                self.items_per_page = new_size
                self.current_page_index = current_first_item_global_index_in_filtered_list // self.items_per_page

                self._display_current_page() # This calls update_navigation_buttons_state indirectly via apply_filters
                self.update_status(f"Размер страницы изменен на {self.items_per_page}")
                self.set_focus_on_editor()
            else:
                messagebox.showwarning("Неверный размер", "Размер страницы должен быть > 0.")
                self.page_size_var.set(str(self.items_per_page))
        except ValueError:
            messagebox.showwarning("Неверный ввод", "Введите числовое значение размера.")
            self.page_size_var.set(str(self.items_per_page))
        except Exception as e:
            messagebox.showerror("Ошибка", f"Ошибка при изменении размера страницы: {e}\n{traceback.format_exc()}")
            self.page_size_var.set(str(self.items_per_page))
        # Explicitly call update nav state here in case _display_current_page wasn't called
        self.update_navigation_buttons_state()

    # --- ИСПРАВЛЕНО: Добавлен вызов update_navigation_buttons_state ---
    def go_to_page(self, *args):
        """Переходит на указанную страницу."""
        if not self.filtered_display_ids: return
        try:
            page_num_str = self.page_var.get()
            if not page_num_str: return
            page_num = int(page_num_str)
            num_pages = math.ceil(len(self.filtered_display_ids) / self.items_per_page) if self.filtered_display_ids else 1

            if 1 <= page_num <= num_pages:
                new_page_index = page_num - 1
                if new_page_index == self.current_page_index: return
                if not self.save_current_page_data_if_dirty(prompt_save=True):
                    # self.page_var.set(str(self.current_page_index + 1)) # Keep old value visually
                    return
                self.current_page_index = new_page_index
                self._display_current_page()
                self.update_status(f"Переход на страницу {self.current_page_index + 1} ({self._get_current_filter_description()})")
                self.update_navigation_buttons_state() # <<<--- ADDED HERE
                self.set_focus_on_editor()
            else:
                messagebox.showwarning("Неверный номер", f"Введите номер страницы от 1 до {num_pages}.")
                # Keep old value visually
                if self.page_var: self.page_var.set(str(self.current_page_index + 1))
        except ValueError:
            messagebox.showwarning("Неверный ввод", "Введите числовое значение номера страницы.")
            if self.page_var: self.page_var.set(str(self.current_page_index + 1))
        except Exception as e:
            messagebox.showerror("Ошибка", f"Ошибка при переходе на страницу: {e}\n{traceback.format_exc()}")
            if self.page_var: self.page_var.set(str(self.current_page_index + 1))

        # Always update nav state after potential errors or successful navigation attempt
        self.update_navigation_buttons_state()

    # --- ИСПРАВЛЕНО: Добавлен вызов update_navigation_buttons_state ---
    def go_to_next_page(self):
        """Переходит на следующую страницу."""
        num_pages = math.ceil(len(self.filtered_display_ids) / self.items_per_page) if self.filtered_display_ids else 1
        if self.current_page_index < num_pages - 1:
            if not self.save_current_page_data_if_dirty(prompt_save=True): return
            self.current_page_index += 1
            self._display_current_page()
            self.update_status(f"Переход на страницу {self.current_page_index + 1} ({self._get_current_filter_description()})")
            self.update_navigation_buttons_state() # <<<--- ADDED HERE
            self.set_focus_on_editor()

    # --- ИСПРАВЛЕНО: Добавлен вызов update_navigation_buttons_state ---
    def go_to_prev_page(self):
        """Переходит на предыдущую страницу."""
        if self.current_page_index > 0:
            if not self.save_current_page_data_if_dirty(prompt_save=True): return
            self.current_page_index -= 1
            self._display_current_page()
            self.update_status(f"Переход на страницу {self.current_page_index + 1} ({self._get_current_filter_description()})")
            self.update_navigation_buttons_state() # <<<--- ADDED HERE
            self.set_focus_on_editor()

    def _get_current_filter_description(self):
        """Возвращает строку с описанием текущих фильтров."""
        file_filter_text = os.path.basename(self.selected_filename_filter) if self.selected_filename_filter != ALL_FILES_FILTER else "Все"
        if self.show_untranslated_files_only and self.selected_filename_filter == ALL_FILES_FILTER:
            file_filter_text = "Все (Только неперев.)"
        elif self.show_untranslated_files_only:
             file_filter_text += " (Только неперев.)"

        status_filter_text = {
            "untranslated": "Неперев.",
            "translated": "Перев.",
            "approved": "Подтв.",
            "all": "Все"
        }.get(self.selected_status_filter, self.selected_status_filter)
        # Combine File and Status descriptions
        return f"Ф: {file_filter_text}, Ст: {status_filter_text}"


    def update_navigation_buttons_state(self):
        """Обновляет состояние кнопок навигации и связанных элементов."""
        has_content = bool(self.filtered_display_ids)
        if not self.xliff_tree: has_content = False
        num_pages = math.ceil(len(self.filtered_display_ids) / self.items_per_page) if has_content else 1

        prev_state = tk.NORMAL if has_content and self.current_page_index > 0 else tk.DISABLED
        next_state = tk.NORMAL if has_content and self.current_page_index < num_pages - 1 else tk.DISABLED
        entry_state = tk.NORMAL if has_content else tk.DISABLED
        translate_state = tk.NORMAL if self.xliff_tree and TRANSLATION_AVAILABLE and self.current_page_units_map else tk.DISABLED

        if self.prev_button: self.prev_button.configure(state=prev_state)
        if self.next_button: self.next_button.configure(state=next_state)
        if self.page_entry: self.page_entry.configure(state=entry_state)
        if self.go_button: self.go_button.configure(state=entry_state)
        if self.translate_button: self.translate_button.configure(state=translate_state)

        # Elements depending only on file load state
        general_state = tk.NORMAL if self.xliff_tree else tk.DISABLED
        if self.page_size_entry: self.page_size_entry.configure(state=general_state)
        if self.page_size_button: self.page_size_button.configure(state=general_state)

        # Update file combobox and switch together
        if self.file_filter_combobox:
             current_values = self.file_filter_combobox.cget("values")
             combo_state = tk.NORMAL if self.xliff_tree and len(current_values) > 1 else tk.DISABLED
             self.file_filter_combobox.configure(state=combo_state)
        if self.show_untranslated_switch:
            # Switch is enabled if a file is loaded
            self.show_untranslated_switch.configure(state=general_state)

        if self.status_filter_combobox: self.status_filter_combobox.configure(state=general_state)
        if self.search_entry: self.search_entry.configure(state=general_state)
        if self.find_next_button: self.find_next_button.configure(state=general_state if self.search_entry and self.search_entry.get() else tk.DISABLED)
        if self.stats_button: self.stats_button.configure(state=general_state) # Enable/disable stats button
        if self.markup_mode_button: self.markup_mode_button.configure(state=tk.DISABLED if self.current_mode == 'markup' else general_state)
        if self.edit_mode_button: self.edit_mode_button.configure(state=tk.DISABLED if self.current_mode == 'edit' else general_state)
        if self.font_size_increase_button: self.font_size_increase_button.configure(state=general_state)
        if self.font_size_decrease_button: self.font_size_decrease_button.configure(state=general_state)

        # Update page label text and entry value
        if has_content:
            # Use the helper function for consistent filter description
            page_label_text = f"Стр: {self.current_page_index + 1}/{num_pages} ({self._get_current_filter_description()})"
            if self.page_var: self.page_var.set(str(self.current_page_index + 1))
        else:
            page_label_text = "Страница: - / -"
            if self.page_var: self.page_var.set("")
        if self.page_label: self.page_label.configure(text=page_label_text)


    def change_font_size(self, delta):
        """Изменяет размер шрифта редактора."""
        if not self.editor_textbox: return
        new_size = self.current_font_size + delta
        if 5 <= new_size <= 30: # Limit font size
            self.current_font_size = new_size
            try:
                editor_font = ctk.CTkFont(family="Consolas", size=self.current_font_size)
                self.editor_textbox.configure(font=editor_font)
                print(f"Размер шрифта изменен на {self.current_font_size}")
            except tk.TclError:
                 print(f"{Fore.YELLOW}Предупреждение: Шрифт 'Consolas' не найден. Используется Courier New.{Style.RESET_ALL}")
                 try:
                    editor_font = ctk.CTkFont(family="Courier New", size=self.current_font_size)
                    self.editor_textbox.configure(font=editor_font)
                    print(f"Размер шрифта изменен на {self.current_font_size} (использован Courier New)")
                 except Exception as e:
                     print(f"{Fore.RED}Ошибка установки шрифта: {e}{Style.RESET_ALL}")
        else:
            print(f"Размер шрифта {new_size} вне допустимого диапазона (5-30).")

    # --- Функции для работы с XLIFF ---

    # --- ИСПРАВЛЕНО: Простая логика - target не пуст = переведен ---
    def _is_unit_translated(self, unit):
        """Определяет статус перевода юнита ('untranslated', 'translated', 'approved').
           Считает юнит переведенным, если <target> существует и не пуст (содержит текст или дочерние теги)."""
        if unit is None: return 'untranslated'

        target_elements = unit.xpath("./xliff:target", namespaces=LXML_NSMAP)

        if not target_elements:
            # No <target> -> untranslated
            # print(f"DEBUG: ID {unit.get('id')} - No target node, marking 'untranslated'.")
            return 'untranslated'

        target_node = target_elements[0]
        approved_attr = target_node.get('approved')

        # 1. Check 'approved' (highest priority)
        if approved_attr == 'yes':
            # print(f"DEBUG: ID {unit.get('id')} - Approved='yes', marking 'approved'.")
            return 'approved'

        # 2. Check for *any* content within <target>
        # normalize-space(.) checks for non-whitespace text anywhere inside target
        # ./* checks for any child elements (<g>, <x/>, etc.)
        has_any_content = target_node.xpath("boolean(normalize-space(.) or ./*)")

        if has_any_content:
            # <target> exists and contains text or child elements -> translated
            # print(f"DEBUG: ID {unit.get('id')} - Target has content, marking 'translated'.")
            return 'translated'
        else:
            # <target> exists but is empty (no text and no children) -> untranslated
            # print(f"DEBUG: ID {unit.get('id')} - Target exists but is empty, marking 'untranslated'.")
            return 'untranslated'


    def _update_unit_statuses_and_filters(self):
        """Пересчитывает статусы всех юнитов, обновляет доступные фильтры
           и определяет файлы с непереведенными юнитами."""
        self.unit_status_map.clear()
        self.unit_id_to_filename_map.clear()
        filenames_in_notes = set()
        self.untranslated_filenames.clear()
        status_counts = {'untranslated': 0, 'translated': 0, 'approved': 0}

        for unit in self.all_trans_units:
            unit_id = unit.get("id")
            if not unit_id:
                 print(f"{Fore.YELLOW}Предупреждение: <trans-unit> без 'id'. Пропускается.{Style.RESET_ALL}")
                 continue

            # Translation Status
            status = self._is_unit_translated(unit)
            self.unit_status_map[unit_id] = status
            status_counts[status] += 1

            # Filename from <note>
            note_node = unit.find("xliff:note", namespaces=LXML_NSMAP)
            filename = None
            if note_node is not None and note_node.text:
                match = NOTE_FILE_REGEX.match(note_node.text.strip())
                if match:
                    filename = match.group(1).strip()
                    if filename:
                        self.unit_id_to_filename_map[unit_id] = filename
                        filenames_in_notes.add(filename)
                        # Add to untranslated set if applicable
                        if status == 'untranslated':
                            self.untranslated_filenames.add(filename)

        # Update the list of ALL available filenames
        self.available_filenames = [ALL_FILES_FILTER] + sorted(list(filenames_in_notes))

        # Update the values in the file filter combobox based on the switch state
        self._update_file_filter_combobox_values()

        # Enable the status combobox
        if self.status_filter_combobox:
            self.status_filter_combobox.configure(state=tk.NORMAL)

        print(f"Статистика статусов: Непереведенные={status_counts['untranslated']}, Переведенные={status_counts['translated']}, Подтвержденные={status_counts['approved']}")
        print(f"Файлов с непереведенными строками: {len(self.untranslated_filenames)}")
        return status_counts['untranslated']


    def _update_file_filter_combobox_values(self):
        """Обновляет список значений в file_filter_combobox в зависимости
           от состояния переключателя show_untranslated_files_only."""
        if not self.file_filter_combobox:
            return

        current_selection = self.file_filter_combobox.get()
        new_values = []

        if self.show_untranslated_files_only:
            # Show "All Files" + only those with untranslated units
            new_values = [ALL_FILES_FILTER] + sorted(list(self.untranslated_filenames))
            # print(f"DEBUG: Showing untranslated files only. Count: {len(new_values)}")
        else:
            # Show all available files
            new_values = self.available_filenames # already contains ALL_FILES_FILTER and is sorted
            # print(f"DEBUG: Showing all available files. Count: {len(new_values)}")

        # Update combobox values
        self.file_filter_combobox.configure(values=new_values)

        # Try to restore current selection if it exists in the new list
        if current_selection in new_values:
            self.file_filter_combobox.set(current_selection)
            # print(f"DEBUG: Restored selection: {current_selection}")
        else:
            # If the current selection is not available (filtered out), select "All Files"
            self.file_filter_combobox.set(ALL_FILES_FILTER)
            # print(f"DEBUG: Selection '{current_selection}' not in new list, defaulting to {ALL_FILES_FILTER}")
            # Update self.selected_filename_filter as the selection was changed programmatically
            if self.selected_filename_filter != ALL_FILES_FILTER:
                 # print(f"DEBUG: Internal selected_filename_filter reset to {ALL_FILES_FILTER}")
                 self.selected_filename_filter = ALL_FILES_FILTER

        # Update combobox state (enabled if more than one option)
        # This will be potentially overridden by update_navigation_buttons_state later, but good for immediate reaction
        combo_state = tk.NORMAL if self.xliff_tree and len(new_values) > 1 else tk.DISABLED
        self.file_filter_combobox.configure(state=combo_state)


    def _on_show_untranslated_switch_toggle(self):
        """Обработчик изменения состояния переключателя 'Только неперев.'"""
        if not self.xliff_tree or not self.show_untranslated_switch:
            return

        new_switch_state = bool(self.show_untranslated_switch.get())
        if new_switch_state == self.show_untranslated_files_only:
             return # State hasn't changed

        # Ask to save if current page is dirty
        if not self.save_current_page_data_if_dirty(prompt_save=True):
            print("File filter change cancelled due to unsaved changes.")
            # Revert switch state in UI
            self.show_untranslated_switch.select() if self.show_untranslated_files_only else self.show_untranslated_switch.deselect()
            return

        self.show_untranslated_files_only = new_switch_state
        print(f"Переключатель 'Only not-tr.' установлен в: {self.show_untranslated_files_only}")

        # Update the file list in the combobox (this might also reset selection)
        self._update_file_filter_combobox_values()

        # Apply all filters (including the potentially changed file filter from combobox update)
        self.apply_current_filters(reset_page=True)
        # self.update_navigation_buttons_state() # Called implicitly by apply_current_filters
        self.set_focus_on_editor()


    def load_xliff(self, filepath_arg=None):
        """Загружает XLIFF файл."""
        if self.is_dirty:
            if not messagebox.askyesno("Несохраненные изменения", "Есть несохраненные изменения. Загрузить новый файл без сохранения?"):
                return

        if filepath_arg:
            filepath = filepath_arg
        else:
            initial_dir = os.path.dirname(self.xliff_filepath) if self.xliff_filepath else "."
            initial_file = os.path.basename(self.xliff_filepath) if self.xliff_filepath else XLIFF_FILE_DEFAULT
            filepath = filedialog.askopenfilename(
                title="Выберите XLIFF файл",
                filetypes=[("XLIFF files", "*.xliff"), ("All files", "*.*")],
                initialdir=initial_dir,
                initialfile=initial_file
            )
        if not filepath: return

        self.reset_state() # Reset everything before loading

        try:
            print(f"Загрузка файла: {filepath}")
            parser = ET.XMLParser(remove_blank_text=False, strip_cdata=False, resolve_entities=False)
            self.xliff_tree = ET.parse(filepath, parser=parser)
            self.xliff_root = self.xliff_tree.getroot()

            expected_ns = LXML_NSMAP['xliff']
            if not self.xliff_root.tag.startswith(f"{{{expected_ns}}}"):
                if 'xliff' not in self.xliff_root.tag:
                    raise ValueError(f"Некорректный корневой элемент. Ожидался '{expected_ns}', получен '{self.xliff_root.tag}'.")
                else:
                    print(f"{Fore.YELLOW}Предупреждение: Пространство имен ('{self.xliff_root.tag}') отличается от '{expected_ns}'. Попытка продолжить.{Style.RESET_ALL}")

            self.xliff_filepath = filepath

            # Detect languages
            file_node = self.xliff_root.find('.//xliff:file', namespaces=LXML_NSMAP)
            if file_node is not None:
                src_lang = file_node.get('source-language')
                tgt_lang = file_node.get('target-language')
                self.detected_source_lang = src_lang.lower() if src_lang else SOURCE_LANG
                self.detected_target_lang = tgt_lang.lower() if tgt_lang else TARGET_LANG
                print(f"Обнаружены языки: {self.detected_source_lang} -> {self.detected_target_lang}")
                if not src_lang: print(f"{Fore.YELLOW}Предупреждение: 'source-language' не найден. Используется '{SOURCE_LANG}'.{Style.RESET_ALL}")
                if not tgt_lang: print(f"{Fore.YELLOW}Предупреждение: 'target-language' не найден. Используется '{TARGET_LANG}'.{Style.RESET_ALL}")
            else:
                self.detected_source_lang = SOURCE_LANG
                self.detected_target_lang = TARGET_LANG
                print(f"{Fore.YELLOW}Предупреждение: Элемент <file> не найден. Используются языки по умолчанию: '{SOURCE_LANG}' -> '{TARGET_LANG}'.{Style.RESET_ALL}")

            # Get all trans-units
            self.all_trans_units = self.xliff_root.xpath(".//xliff:trans-unit", namespaces=LXML_NSMAP)
            if not self.all_trans_units:
                print(f"{Fore.YELLOW}Предупреждение: В файле не найдено <trans-unit>.{Style.RESET_ALL}")

            # Update statuses, filters etc. This also calls _update_file_filter_combobox_values()
            untranslated_count = self._update_unit_statuses_and_filters()

            # Apply initial filters (default: all files, untranslated status)
            self.apply_current_filters(reset_page=True)

            self.set_dirty_flag(False)
            self.set_mode(DEFAULT_MODE, force_update=True) # Set default view mode

            self.update_status(f"Загружен: {os.path.basename(filepath)} | Всего: {len(self.all_trans_units)} | Неперев.: {untranslated_count} | Языки: {self.detected_source_lang} -> {self.detected_target_lang}")
            self.update_title()
            if self.editor_textbox:
                self.editor_textbox.configure(state=tk.NORMAL) # Enable editor after load
                self.set_focus_on_editor()
            # update_navigation_buttons_state() is called by apply_current_filters

        except ET.XMLSyntaxError as xe:
            messagebox.showerror("Ошибка парсинга XML", f"Не удалось разобрать XLIFF (синтаксис):\n{xe}")
            self.reset_state()
        except ValueError as ve:
            messagebox.showerror("Ошибка формата", f"Некорректный формат XLIFF:\n{ve}")
            self.reset_state()
        except Exception as e:
            messagebox.showerror("Ошибка загрузки", f"Не удалось загрузить XLIFF:\n{e}\n{traceback.format_exc()}")
            self.reset_state()

    def save_current_page_data_if_dirty(self, prompt_save=False):
        """Сохраняет данные текущей страницы из редактора В ПАМЯТЬ, если были изменения."""
        inner_widget = self._get_inner_text_widget()
        textbox_modified = False
        if inner_widget:
            try: textbox_modified = inner_widget.edit_modified()
            except tk.TclError:
                print("Ошибка проверки флага модификации виджета.")
                return False

        if not textbox_modified: return True

        should_save = True
        if prompt_save:
            mode_text = "разметки" if self.current_mode == 'markup' else "текста"
            filter_desc = self._get_current_filter_description()
            result = messagebox.askyesnocancel("Сохранить изменения?", f"Сохранить изменения на стр. {self.current_page_index + 1} (режим {mode_text}, {filter_desc})?")
            if result is None: return False
            if result is False:
                should_save = False
                if inner_widget:
                    try: inner_widget.edit_modified(False)
                    except tk.TclError: pass
                return True

        if should_save:
            success = False
            print(f"Сохранение данных страницы {self.current_page_index + 1}...")
            recalculate_untranslated_files = False

            if self.current_mode == 'markup':
                save_result = self._save_markup_page_data(force_check=True)
                success = save_result['success']
                recalculate_untranslated_files = save_result.get('statuses_changed', False)
                if not success:
                    messagebox.showerror("Ошибка сохранения", "Не удалось сохранить изменения (разметка). Проверьте корректность XML.")
                    return False
            elif self.current_mode == 'edit':
                save_result = self._save_edit_page_data(force_check=True)
                success = save_result['success']
                recalculate_untranslated_files = save_result.get('statuses_changed', False)
                if not success:
                    messagebox.showerror("Ошибка сохранения", "Не удалось сохранить изменения (редактирование).")
                    return False

            if success:
                if inner_widget:
                    try:
                        inner_widget.edit_modified(False)
                        print(f"Флаг модификации редактора сброшен после сохранения стр. {self.current_page_index + 1}.")
                    except tk.TclError: pass

                if recalculate_untranslated_files:
                    print("Статусы могли измениться, пересчитываем список файлов с непереведенными...")
                    self._update_unit_statuses_and_filters() # This updates self.untranslated_filenames and calls _update_file_filter_combobox_values

                # Re-apply filters anyway to refresh display if needed (e.g., status changed)
                self.apply_current_filters(reset_page=False)

                return True
            else:
                 messagebox.showerror("Ошибка", "Непредвиденная ошибка при сохранении страницы.")
                 return False
        else: # User chose "No"
            return True

    def save_xliff(self):
        """Сохраняет все изменения из памяти в XLIFF файл."""
        if self.xliff_tree is None or not self.xliff_filepath:
            messagebox.showwarning("Нет данных", "Сначала загрузите XLIFF файл.")
            return

        if not self.save_current_page_data_if_dirty(prompt_save=False):
            messagebox.showerror("Ошибка", "Не удалось сохранить изменения текущей страницы. Исправьте ошибки перед сохранением файла.")
            return

        if not self.is_dirty:
            self.update_status("Нет изменений для сохранения.")
            print("Нет глобальных изменений для сохранения в файл.")
            if self.save_button: self.save_button.configure(state=tk.DISABLED)
            return

        backup_filepath = self.xliff_filepath + BACKUP_SUFFIX
        try:
            if os.path.exists(self.xliff_filepath):
                print(f"Создание резервной копии: {os.path.basename(backup_filepath)}")
                shutil.copy2(self.xliff_filepath, backup_filepath)

            print(f"Сохранение изменений в: {self.xliff_filepath}...")
            output_buffer = io.BytesIO()

            self.xliff_tree.write(
                output_buffer,
                pretty_print=True,
                encoding='utf-8',
                xml_declaration=True,
            )
            xml_content = output_buffer.getvalue()

            # Validate before writing
            try:
                parser_check = ET.XMLParser(remove_blank_text=False, strip_cdata=False, resolve_entities=False)
                ET.fromstring(xml_content, parser=parser_check)
                print("Проверка XML перед записью: OK")
            except ET.XMLSyntaxError as xe:
                print(f"{Fore.RED}Ошибка: Сгенерированный XML некорректен! Сохранение отменено.{Style.RESET_ALL}")
                messagebox.showerror("Ошибка XML", f"Ошибка валидации перед сохранением:\n{xe}\n\nСохранение отменено.")
                return

            with open(self.xliff_filepath, "wb") as f:
                f.write(xml_content)

            self.set_dirty_flag(False) # Reset dirty flag ONLY on successful save
            inner_widget = self._get_inner_text_widget()
            if inner_widget:
                try: inner_widget.edit_modified(False)
                except tk.TclError: pass

            untranslated_count = sum(1 for status in self.unit_status_map.values() if status == 'untranslated')
            self.update_status(f"Файл сохранен: {os.path.basename(self.xliff_filepath)} | Всего: {len(self.all_trans_units)} | Неперев.: {untranslated_count}")
            print("Файл успешно сохранен.")

        except Exception as e:
            messagebox.showerror("Ошибка сохранения", f"Не удалось сохранить XLIFF файл:\n{e}\n{traceback.format_exc()}")
            self.update_status("Ошибка сохранения файла.")


    def _set_editor_text_highlighted(self, text):
        """Вставляет текст в редактор с подсветкой (если режим 'markup')."""
        target_widget = self._get_inner_text_widget()
        if not target_widget:
            print("Ошибка: Внутренний виджет редактора не найден.")
            if self.editor_textbox:
                 try:
                     self.editor_textbox.configure(state=tk.NORMAL)
                     self.editor_textbox.delete("1.0", tk.END)
                     self.editor_textbox.insert("1.0", text)
                     # self.editor_textbox.edit_modified(False) # Set modified False after setting text
                     editor_state = tk.NORMAL if self.xliff_tree else tk.DISABLED
                     self.editor_textbox.configure(state=editor_state)
                 except Exception as e: print(f"Ошибка вставки в обертку: {e}")
            return

        try:
            editor_state = tk.NORMAL if self.xliff_tree else tk.DISABLED
            self.editor_textbox.configure(state=tk.NORMAL)
            target_widget.configure(state=tk.NORMAL)
            target_widget.delete("1.0", tk.END)

            # Remove old highlight tags
            for tag in target_widget.tag_names():
                if tag.startswith("Token_") or tag == "search_highlight":
                    try: target_widget.tag_delete(tag)
                    except tk.TclError: pass

            if not PYGMENTS_AVAILABLE or TEXT_HIGHLIGHT_CONFIG["lexer"] is None or self.current_mode != 'markup':
                target_widget.insert("1.0", text)
            else:
                # Configure tags for current highlighting
                for token_type_key, config in TEXT_HIGHLIGHT_CONFIG["tags"].items():
                    tag_name = "Token_" + str(token_type_key).replace(".", "_").replace("'", "")
                    try: target_widget.tag_config(tag_name, **config)
                    except tk.TclError as te: print(f"Ошибка настройки тега {tag_name}: {te}")

                lexer = TEXT_HIGHLIGHT_CONFIG["lexer"]
                try:
                    tokens = lex(text, lexer)
                    for token_type, token_value in tokens:
                        # Find most specific tag
                        tag_config_key = None; temp_type = token_type
                        while temp_type is not None:
                            key_to_match = temp_type if PYGMENTS_AVAILABLE else str(temp_type)
                            found = False
                            for config_key_obj in TEXT_HIGHLIGHT_CONFIG["tags"].keys():
                                match_target = config_key_obj if PYGMENTS_AVAILABLE else str(config_key_obj)
                                if key_to_match == match_target:
                                    tag_config_key = config_key_obj; found = True; break
                            if found: break
                            temp_type = getattr(temp_type, 'parent', None)

                        if tag_config_key:
                            tag_name = "Token_" + str(tag_config_key).replace(".", "_").replace("'", "")
                            try: target_widget.insert(tk.END, token_value, tag_name)
                            except tk.TclError: target_widget.insert(tk.END, token_value)
                        else: target_widget.insert(tk.END, token_value)
                except Exception as e:
                    print(f"{Fore.RED}Ошибка подсветки синтаксиса: {e}{Style.RESET_ALL}")
                    target_widget.delete("1.0", tk.END) # Clear before inserting without highlight
                    target_widget.insert("1.0", text)

            # target_widget.edit_modified(False) # Reset modified flag after setting text
            self.editor_textbox.configure(state=editor_state) # Restore state
            target_widget.configure(state=editor_state)
            self.last_search_pos = "1.0" # Reset search position on text change

        except tk.TclError as e:
            print(f"Ошибка Tcl при установке текста редактора: {e}")
        except Exception as e:
            print(f"Общая ошибка при установке текста редактора: {e}")
            traceback.print_exc()

    # --- Функция автоматического перевода ---
    def translate_current_page(self):
        """Переводит <source> для всех <trans-unit> на текущей странице."""
        if not TRANSLATION_AVAILABLE:
            messagebox.showerror("Ошибка", "Функция перевода недоступна. Установите 'deep-translator'.")
            return
        if not self.current_page_units_map:
            messagebox.showinfo("Информация", "Нет строк для перевода на текущей странице (учитывая фильтры).")
            return
        if not self.selected_translator_service:
            messagebox.showerror("Ошибка", "Не выбран сервис перевода.")
            return

        source_lang_for_translator = self.detected_source_lang
        target_lang_for_translator = self.detected_target_lang

        if self.selected_translator_service == "MyMemory":
            source_lang_for_translator = MYMEMORY_LANG_MAP.get(self.detected_source_lang, self.detected_source_lang)
            target_lang_for_translator = MYMEMORY_LANG_MAP.get(self.detected_target_lang, self.detected_target_lang)
            print(f"DEBUG: Using MyMemory formatted languages: {source_lang_for_translator} -> {target_lang_for_translator}")

        if not messagebox.askyesno("Подтверждение перевода",
                               f"Перевести {len(self.current_page_units_map)} строк на стр. {self.current_page_index + 1} "
                               f"({source_lang_for_translator} -> {target_lang_for_translator})?\n\n"
                               f"Существующие переводы и статус 'approved' будут ЗАМЕНЕНЫ.\n"
                               f"Сервис: {self.selected_translator_service}"):
            return

        print(f"Начало перевода страницы {self.current_page_index + 1} с помощью {self.selected_translator_service} ({source_lang_for_translator} -> {target_lang_for_translator})...")
        if self.translate_button: self.translate_button.configure(state=tk.DISABLED)
        original_status_text = self.status_label.cget("text") if self.status_label else "Перевод..."
        self.update_status(f"Перевод стр. {self.current_page_index + 1} ({source_lang_for_translator}->{target_lang_for_translator}) (0%)...")

        translated_count = 0; error_count = 0; units_processed = 0
        any_change_made_in_memory = False
        statuses_changed = False
        total_units = len(self.current_page_units_map)
        updated_unit_ids = set()

        try:
            if self.selected_translator_service == "Google":
                translator = GoogleTranslator(source=self.detected_source_lang, target=self.detected_target_lang)
            elif self.selected_translator_service == "MyMemory":
                translator = MyMemoryTranslator(source=source_lang_for_translator, target=target_lang_for_translator)
            else: raise ValueError(f"Неизвестный сервис: {self.selected_translator_service}")
        except Exception as e:
            messagebox.showerror("Ошибка инициализации переводчика",
                                 f"Не удалось создать переводчик ({source_lang_for_translator}->{target_lang_for_translator} с {self.selected_translator_service}):\n{e}")
            self.update_navigation_buttons_state()
            self.update_status(original_status_text)
            return

        for unit_id, unit in self.current_page_units_map.items():
            source_node = unit.find("xliff:source", namespaces=LXML_NSMAP)
            source_text = "".join(source_node.itertext()).strip() if source_node is not None else ""

            if not source_text:
                print(f"  - Пропуск ID {unit_id}: пустой <source>.")
                units_processed += 1; continue

            target_node = unit.find("xliff:target", namespaces=LXML_NSMAP)
            original_target_text = "".join(target_node.itertext()).strip() if target_node is not None else ""
            original_status_unit = self.unit_status_map.get(unit_id)

            try:
                print(f"  - Перевод ID {unit_id} ({units_processed + 1}/{total_units}) [{len(source_text)} chars]...")
                translated_text = translator.translate(source_text)
                time.sleep(TRANSLATION_DELAY_SECONDS)

                if translated_text and translated_text.strip():
                    translated_text = translated_text.strip()
                    if target_node is None:
                        target_node = ET.Element(f"{{{LXML_NSMAP['xliff']}}}target")
                        insert_point = source_node or unit.find("xliff:note", namespaces=LXML_NSMAP)
                        if insert_point is not None: insert_point.addnext(target_node)
                        else: unit.append(target_node)

                    if original_target_text != translated_text:
                        target_node.clear()
                        target_node.text = translated_text
                        if 'approved' in target_node.attrib: del target_node.attrib['approved']

                        new_status_unit = self._is_unit_translated(unit)
                        self.unit_status_map[unit_id] = new_status_unit
                        if original_status_unit != new_status_unit:
                            statuses_changed = True

                        any_change_made_in_memory = True
                        updated_unit_ids.add(unit_id)

                    translated_count += 1
                else:
                    print(f"  - {Fore.YELLOW}Предупреждение: Пустой перевод для ID {unit_id}.{Style.RESET_ALL}")
                    error_count += 1
            except Exception as e:
                print(f"  - {Fore.RED}Ошибка перевода ID {unit_id}: {e}{Style.RESET_ALL}")
                error_count += 1
                error_str = str(e).lower()
                if "too many requests" in error_str or "timed out" in error_str or "429" in error_str or "connection" in error_str:
                    pause_time = 5
                    print(f"{Fore.YELLOW}    -> Обнаружена ошибка сети/лимита запросов. Пауза {pause_time} секунд...{Style.RESET_ALL}")
                    time.sleep(pause_time)
                elif "translation not found" in error_str or "no translation" in error_str:
                    print(f"{Fore.YELLOW}    -> Перевод не найден для этого текста.{Style.RESET_ALL}")

            units_processed += 1
            progress = int((units_processed / total_units) * 100)
            self.update_status(f"Перевод стр. {self.current_page_index + 1} ({source_lang_for_translator}->{target_lang_for_translator}) ({progress}%)...")

        final_status_part1 = f"Перевод ({self.selected_translator_service}) завершен."
        final_status_part2 = f"Успешно: {translated_count}, Ошибки/Пропущено: {error_count}."
        print(final_status_part1, final_status_part2)

        if any_change_made_in_memory:
            print("Изменения внесены в память.")
            self.set_dirty_flag(True)

            if statuses_changed:
                 print("Статусы изменились, обновляем список непереведенных файлов...")
                 self._update_unit_statuses_and_filters()

            self.apply_current_filters(reset_page=False)

            inner_widget = self._get_inner_text_widget()
            if inner_widget:
                try: inner_widget.edit_modified(False)
                except tk.TclError: pass

            untranslated_count = sum(1 for status in self.unit_status_map.values() if status == 'untranslated')
            self.update_status(f"{final_status_part1} {final_status_part2} | Всего: {len(self.all_trans_units)} | Неперев.: {untranslated_count}")
        else:
            print("Не было внесено изменений в память.")
            self.update_navigation_buttons_state() # Re-enable translate button
            untranslated_count = sum(1 for status in self.unit_status_map.values() if status == 'untranslated')
            self.update_status(f"{final_status_part1} {final_status_part2} | Нет изменений. | Неперев.: {untranslated_count}")

    # --- Функции фильтрации ---

    def on_file_filter_change(self, event=None):
        """Обработчик изменения выбора в комбобоксе фильтра файлов."""
        if not self.file_filter_combobox or not self.xliff_tree: return

        new_filter = self.file_filter_combobox.get()
        if new_filter == self.selected_filename_filter:
            return

        if not self.save_current_page_data_if_dirty(prompt_save=True):
            print("Смена фильтра файла отменена из-за несохраненных изменений.")
            self.file_filter_combobox.set(self.selected_filename_filter)
            return

        print(f"Смена фильтра файла на: {new_filter}")
        self.selected_filename_filter = new_filter
        self.apply_current_filters(reset_page=True)
        self.set_focus_on_editor()

    def on_status_filter_change(self, event=None):
        """Обработчик изменения выбора в комбобоксе фильтра статуса."""
        if not self.status_filter_combobox or not self.xliff_tree: return

        status_map_display_to_internal = {
            "Непереведенные": "untranslated",
            "Переведенные": "translated",
            "Подтвержденные": "approved",
            "Все статусы": "all",
        }
        selected_display_value = self.status_filter_combobox.get()
        new_filter = status_map_display_to_internal.get(selected_display_value, "all")

        if new_filter == self.selected_status_filter:
            return

        if not self.save_current_page_data_if_dirty(prompt_save=True):
            print("Смена фильтра статуса отменена из-за несохраненных изменений.")
            status_map_internal_to_display = {v: k for k, v in status_map_display_to_internal.items()}
            self.status_filter_combobox.set(status_map_internal_to_display.get(self.selected_status_filter, "Все статусы"))
            return

        print(f"Смена фильтра статуса на: {new_filter}")
        self.selected_status_filter = new_filter
        self.apply_current_filters(reset_page=True)
        self.set_focus_on_editor()


    def apply_current_filters(self, reset_page=False):
        """
        Фильтрует мастер-список all_trans_units на основе ВСЕХ фильтров
        и обновляет self.filtered_display_ids. Обновляет отображение.
        """
        if not self.xliff_tree:
            self.filtered_display_ids = []
        else:
            # print(f"Применение фильтров: Файл='{self.selected_filename_filter}', Статус='{self.selected_status_filter}', ПоказНеперев={self.show_untranslated_files_only}")

            # 1. Filter by filename
            if self.selected_filename_filter == ALL_FILES_FILTER:
                ids_after_file_filter = list(self.unit_status_map.keys())
            else:
                ids_after_file_filter = [
                    unit_id for unit_id, filename in self.unit_id_to_filename_map.items()
                    if filename == self.selected_filename_filter
                ]

            # 2. Filter by status
            if self.selected_status_filter == "all":
                self.filtered_display_ids = ids_after_file_filter
            else:
                self.filtered_display_ids = [
                    unit_id for unit_id in ids_after_file_filter
                    if self.unit_status_map.get(unit_id) == self.selected_status_filter
                ]

            # Sort by original order in the file
            original_order = {unit.get("id"): i for i, unit in enumerate(self.all_trans_units) if unit.get("id")}
            self.filtered_display_ids.sort(key=lambda unit_id: original_order.get(unit_id, float('inf')))

            print(f"Найдено юнитов после фильтрации: {len(self.filtered_display_ids)}")

        if reset_page:
            self.current_page_index = 0

        # Ensure current page index is valid for the new filtered list
        num_pages = math.ceil(len(self.filtered_display_ids) / self.items_per_page) if self.filtered_display_ids else 1
        self.current_page_index = max(0, min(self.current_page_index, num_pages - 1))

        # Update the editor display for the current page
        self._display_current_page()

        # Update status bar and navigation buttons/labels
        total_units = len(self.all_trans_units)
        untranslated_count = sum(1 for status in self.unit_status_map.values() if status == 'untranslated')
        filter_desc = self._get_current_filter_description()
        self.update_status(f"{filter_desc} | Отображено: {len(self.filtered_display_ids)} | Всего: {total_units} | Неперев.: {untranslated_count}")
        self.update_navigation_buttons_state() # Update page label, buttons


    # --- Функции отображения страниц ---

    def _display_current_page(self):
        """Вызывает нужный метод отображения в зависимости от текущего режима."""
        if self.editor_textbox is None: return

        try: self.editor_textbox.configure(state=tk.NORMAL)
        except tk.TclError: pass

        if self.current_mode == 'markup':
            self._display_markup_page()
        elif self.current_mode == 'edit':
            self._display_edit_page()
        else:
            print(f"Ошибка: Неизвестный режим отображения '{self.current_mode}'")
            self._set_editor_text_highlighted(f"<Ошибка: Неизвестный режим '{self.current_mode}'>")

        self.last_search_pos = "1.0"
        inner_widget = self._get_inner_text_widget()
        if inner_widget:
            try: inner_widget.tag_remove("search_highlight", "1.0", tk.END)
            except tk.TclError: pass
            try: inner_widget.edit_modified(False) # Reset modified flag AFTER displaying
            except tk.TclError: pass

        editor_state = tk.NORMAL if self.xliff_tree else tk.DISABLED
        if self.editor_textbox:
             try: self.editor_textbox.configure(state=editor_state)
             except tk.TclError: pass
        if inner_widget:
             try: inner_widget.configure(state=editor_state)
             except tk.TclError: pass


    def _display_markup_page(self):
        """Отображает текущую страницу в режиме разметки XML (с учетом фильтров)."""
        if self.editor_textbox is None: return

        self.current_page_units_map.clear()

        if not self.filtered_display_ids:
            self._set_editor_text_highlighted("<нет строк для отображения (учитывая фильтры)>")
            return

        start_idx = self.current_page_index * self.items_per_page
        end_idx = min(start_idx + self.items_per_page, len(self.filtered_display_ids))
        page_ids = self.filtered_display_ids[start_idx:end_idx]

        page_xml_parts = []
        id_to_unit_map = {unit.get("id"): unit for unit in self.all_trans_units if unit.get("id")}

        for unit_id in page_ids:
            unit = id_to_unit_map.get(unit_id)
            if unit is not None:
                self.current_page_units_map[unit_id] = unit
                try:
                    xml_string = ET.tostring(
                        unit, encoding='unicode', pretty_print=True, xml_declaration=False
                    ).strip()
                    page_xml_parts.append(xml_string)
                except Exception as e:
                    print(f"{Fore.RED}Ошибка сериализации <trans-unit> ID '{unit_id}': {e}{Style.RESET_ALL}")
                    page_xml_parts.append(f"<!-- Ошибка отображения unit ID: {unit_id} ({e}) -->")
            else:
                print(f"{Fore.YELLOW}Предупреждение: Не найден <trans-unit> для ID '{unit_id}' при отображении разметки.{Style.RESET_ALL}")

        full_xml_block = "\n\n".join(page_xml_parts)
        self._set_editor_text_highlighted(full_xml_block)
        self.editor_textbox.yview_moveto(0.0)


    def _display_edit_page(self):
        """Отображает текущую страницу в режиме простого текста (с учетом фильтров)."""
        if self.editor_textbox is None: return

        self.current_page_units_map.clear()
        target_widget = self._get_inner_text_widget()

        if PYGMENTS_AVAILABLE and target_widget:
            for tag in target_widget.tag_names():
                if tag.startswith("Token_"):
                    try: target_widget.tag_delete(tag)
                    except tk.TclError: pass

        if not self.filtered_display_ids:
            self._set_editor_text_highlighted("<нет строк для отображения (учитывая фильтры)>")
            return

        start_idx = self.current_page_index * self.items_per_page
        end_idx = min(start_idx + self.items_per_page, len(self.filtered_display_ids))
        page_ids = self.filtered_display_ids[start_idx:end_idx]

        text_content = []
        id_to_unit_map = {unit.get("id"): unit for unit in self.all_trans_units if unit.get("id")}

        for unit_id in page_ids:
            unit = id_to_unit_map.get(unit_id)
            if unit is not None:
                self.current_page_units_map[unit_id] = unit
                source_node = unit.find("xliff:source", namespaces=LXML_NSMAP)
                source_text = "".join(source_node.itertext()).strip() if source_node is not None else ""

                target_node = unit.find("xliff:target", namespaces=LXML_NSMAP)
                target_text = "".join(target_node.itertext()).strip() if target_node is not None else ""

                text_content.append(f"ID: {unit_id}")
                text_content.append(f"SOURCE: {source_text}")
                text_content.append(f"TARGET: {target_text}")
                text_content.append('-'*30)
            else:
                print(f"{Fore.YELLOW}Предупреждение: Не найден <trans-unit> для ID '{unit_id}' при отображении текста.{Style.RESET_ALL}")

        full_text_block = "\n".join(text_content)
        self._set_editor_text_highlighted(full_text_block)
        self.editor_textbox.yview_moveto(0.0)


    # --- Функции сохранения страниц ---

    def _save_markup_page_data(self, force_check=False):
        """Парсит XML из редактора (разметка) и обновляет lxml В ПАМЯТИ.
           Возвращает {'success': bool, 'statuses_changed': bool}"""
        default_return = {'success': True, 'statuses_changed': False}
        inner_widget = self._get_inner_text_widget()
        if not self.current_page_units_map or self.current_mode != 'markup': return default_return

        textbox_modified = False
        if inner_widget:
            try: textbox_modified = inner_widget.edit_modified()
            except tk.TclError: pass
        if not force_check and not textbox_modified: return default_return

        edited_xml_string = self.editor_textbox.get("1.0", "end-1c").strip() if self.editor_textbox else ""
        if not edited_xml_string:
             print(f"{Fore.YELLOW}Предупреждение: Редактор разметки пуст. Изменения не будут применены к юнитам этой страницы.{Style.RESET_ALL}")
             return default_return

        root_ns_decl = f"xmlns:xliff='{LXML_NSMAP['xliff']}'" if LXML_NSMAP.get('xliff') else ""
        edited_xml_string_cleaned = re.sub(r'<\?xml.*\?>', '', edited_xml_string).strip()
        xml_to_parse = f"<root {root_ns_decl}>{edited_xml_string_cleaned}</root>"

        any_change_made_in_memory = False
        statuses_changed_on_page = False
        updated_ids_on_page = set()

        try:
            parser = ET.XMLParser(remove_blank_text=False, strip_cdata=False, resolve_entities=False)
            edited_root = ET.fromstring(xml_to_parse, parser=parser)
            edited_units = edited_root.xpath("./*[local-name()='trans-unit']")

            if not edited_units and edited_xml_string_cleaned:
                 raise ValueError("Не найдено <trans-unit> в отредактированном тексте.")

            found_ids_in_editor = set()
            id_to_edited_unit = {}
            for edited_unit in edited_units:
                unit_id = edited_unit.get("id")
                if not unit_id: raise ValueError("<trans-unit> без 'id' в редакторе.")
                if unit_id in found_ids_in_editor: raise ValueError(f"Дублирующийся ID '{unit_id}' в редакторе.")
                found_ids_in_editor.add(unit_id)
                ET.register_namespace('xliff', LXML_NSMAP['xliff'])
                id_to_edited_unit[unit_id] = edited_unit

            id_to_original_unit_map = {unit.get("id"): unit for unit in self.all_trans_units if unit.get("id")}
            ids_processed_on_page = set()

            for unit_id in self.current_page_units_map.keys():
                ids_processed_on_page.add(unit_id)
                original_unit = id_to_original_unit_map.get(unit_id)
                edited_unit = id_to_edited_unit.get(unit_id)

                if original_unit is None:
                    print(f"{Fore.RED}Критическая ошибка: Оригинальный <trans-unit> ID '{unit_id}' не найден!{Style.RESET_ALL}")
                    continue

                if edited_unit is None:
                    print(f"{Fore.YELLOW}Предупреждение: <trans-unit> ID '{unit_id}' (ожидался) не найден в редакторе. Пропуск.{Style.RESET_ALL}")
                    continue

                original_unit_str = ET.tostring(original_unit, encoding='unicode').strip()
                edited_unit_str = ET.tostring(edited_unit, encoding='unicode').strip()

                if original_unit_str != edited_unit_str:
                    parent = original_unit.getparent()
                    if parent is not None:
                        try:
                            original_status = self.unit_status_map.get(unit_id)
                            parent.replace(original_unit, edited_unit)

                            # Update reference in all_trans_units
                            try:
                                idx_in_all = self.all_trans_units.index(original_unit)
                                self.all_trans_units[idx_in_all] = edited_unit
                            except ValueError:
                                found = False
                                for i, u in enumerate(self.all_trans_units):
                                    if u.get("id") == unit_id:
                                        self.all_trans_units[i] = edited_unit
                                        found = True; break
                                if not found: print(f"{Fore.RED}Критическая ошибка: Не удалось обновить all_trans_units для ID '{unit_id}'.{Style.RESET_ALL}")

                            # Update status and filename map
                            new_status = self._is_unit_translated(edited_unit)
                            self.unit_status_map[unit_id] = new_status
                            if original_status != new_status:
                                statuses_changed_on_page = True

                            note_node = edited_unit.find("xliff:note", namespaces=LXML_NSMAP)
                            new_filename = None
                            if note_node is not None and note_node.text:
                                match = NOTE_FILE_REGEX.match(note_node.text.strip())
                                if match: new_filename = match.group(1).strip()
                            if new_filename: self.unit_id_to_filename_map[unit_id] = new_filename
                            elif unit_id in self.unit_id_to_filename_map:
                                if note_node is None or not new_filename:
                                     del self.unit_id_to_filename_map[unit_id]

                            any_change_made_in_memory = True
                            updated_ids_on_page.add(unit_id)
                        except Exception as replace_err:
                             print(f"{Fore.RED}Ошибка при замене <trans-unit> ID {unit_id}: {replace_err}{Style.RESET_ALL}")
                    else:
                        print(f"{Fore.RED}Критическая ошибка: Не найден родитель для <trans-unit> ID {unit_id}. Замена невозможна.{Style.RESET_ALL}")

            new_ids_in_editor = found_ids_in_editor - ids_processed_on_page
            if new_ids_in_editor:
                print(f"{Fore.YELLOW}Предупреждение: ID из редактора не ожидались на этой странице и были проигнорированы: {', '.join(new_ids_in_editor)}.{Style.RESET_ALL}")

            if any_change_made_in_memory:
                print(f"Обновлено {len(updated_ids_on_page)} строк в памяти (разметка). Статусы изменены: {statuses_changed_on_page}")
                self.set_dirty_flag(True)
            else:
                print("Изменений на странице не обнаружено (разметка).")
            return {'success': True, 'statuses_changed': statuses_changed_on_page}

        except ET.XMLSyntaxError as e:
            messagebox.showerror("Ошибка парсинга XML", f"Не удалось разобрать XML из редактора:\n{e}")
            return {'success': False, 'statuses_changed': False}
        except ValueError as ve:
            messagebox.showerror("Ошибка данных", f"Ошибка в структуре отредакт. текста:\n{ve}")
            return {'success': False, 'statuses_changed': False}
        except Exception as e:
            messagebox.showerror("Ошибка обновления", f"Ошибка при обновлении данных (разметка):\n{e}\n{traceback.format_exc()}")
            return {'success': False, 'statuses_changed': False}


    def _save_edit_page_data(self, force_check=False):
        """Сохраняет изменения из редактора (текст) В ПАМЯТЬ.
           Возвращает {'success': bool, 'statuses_changed': bool}"""
        default_return = {'success': True, 'statuses_changed': False}
        inner_widget = self._get_inner_text_widget()
        if not self.current_page_units_map or self.current_mode != 'edit': return default_return

        textbox_modified = False
        if inner_widget:
            try: textbox_modified = inner_widget.edit_modified()
            except tk.TclError: pass
        if not force_check and not textbox_modified: return default_return

        edited_text = self.editor_textbox.get("1.0", "end-1c") if self.editor_textbox else ""
        lines = edited_text.split('\n')
        parsed_targets = {}; current_id = None; current_target_lines = []; in_target_section = False

        try:
            # Parse text from editor (ID:, SOURCE:, TARGET:, --- format)
            for line in lines:
                line_strip = line.strip()
                if line.startswith("ID: "):
                    if current_id is not None and in_target_section:
                        parsed_targets[current_id] = "\n".join(current_target_lines).rstrip()
                    current_id = line[4:].strip() or None
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
                elif in_target_section and current_id is not None:
                    current_target_lines.append(line)

            if current_id is not None and in_target_section:
                parsed_targets[current_id] = "\n".join(current_target_lines).rstrip()

        except Exception as e:
            messagebox.showerror("Ошибка парсинга текста", f"Ошибка разбора текста редактора:\n{e}\n{traceback.format_exc()}")
            return {'success': False, 'statuses_changed': False}

        any_change_made_in_memory = False
        statuses_changed_on_page = False
        updated_ids_on_page = set()
        id_to_original_unit_map = {unit.get("id"): unit for unit in self.all_trans_units if unit.get("id")}
        ids_processed_on_page = set()

        for unit_id in self.current_page_units_map.keys():
            ids_processed_on_page.add(unit_id)
            original_unit = id_to_original_unit_map.get(unit_id)
            if original_unit is None:
                print(f"{Fore.RED}Критическая ошибка: Оригинальный <trans-unit> ID '{unit_id}' не найден!{Style.RESET_ALL}")
                continue

            if unit_id in parsed_targets:
                new_target_text = parsed_targets[unit_id]
                target_node = original_unit.find("xliff:target", namespaces=LXML_NSMAP)
                current_target_text = "".join(target_node.itertext()).rstrip() if target_node is not None else ""
                original_status = self.unit_status_map.get(unit_id)

                if current_target_text != new_target_text:
                    if target_node is None:
                        target_node = ET.Element(f"{{{LXML_NSMAP['xliff']}}}target")
                        source_node = original_unit.find("xliff:source", namespaces=LXML_NSMAP)
                        insert_point = source_node or original_unit.find("xliff:note", namespaces=LXML_NSMAP)
                        if insert_point is not None: insert_point.addnext(target_node)
                        else: original_unit.append(target_node)

                    target_node.clear()
                    target_node.text = new_target_text if new_target_text else None
                    if 'approved' in target_node.attrib: del target_node.attrib['approved']

                    new_status = self._is_unit_translated(original_unit)
                    self.unit_status_map[unit_id] = new_status
                    if original_status != new_status:
                         statuses_changed_on_page = True

                    any_change_made_in_memory = True
                    updated_ids_on_page.add(unit_id)
            else:
                print(f"{Fore.YELLOW}Предупреждение: ID '{unit_id}' (ожидался) не найден в тексте редактора. Изменения для него не сохранены.{Style.RESET_ALL}")


        ids_only_in_editor = set(parsed_targets.keys()) - ids_processed_on_page
        if ids_only_in_editor:
            print(f"{Fore.YELLOW}Предупреждение: ID найдены в редакторе, но не ожидались на этой странице: {', '.join(ids_only_in_editor)}. Они были проигнорированы.{Style.RESET_ALL}")


        if any_change_made_in_memory:
            print(f"Обновлено {len(updated_ids_on_page)} строк в памяти (редактирование). Статусы изменены: {statuses_changed_on_page}")
            self.set_dirty_flag(True)
        else:
            print("Изменений на странице не обнаружено (редактирование).")
        return {'success': True, 'statuses_changed': statuses_changed_on_page}

    # --- Функция отображения статистики ---
    def show_statistics_window(self):
        """Отображает окно со статистикой перевода."""
        if not self.xliff_tree:
            messagebox.showinfo("Нет данных", "Сначала загрузите XLIFF файл.", parent=self.root)
            return

        total_units = len(self.all_trans_units)
        counts = {'untranslated': 0, 'translated': 0, 'approved': 0}
        for status in self.unit_status_map.values():
            counts[status] = counts.get(status, 0) + 1

        untranslated_count = counts['untranslated']
        translated_count = counts['translated']
        approved_count = counts['approved']
        overall_translated = translated_count + approved_count
        progress_value = (overall_translated / total_units) if total_units > 0 else 0

        stats_win = ctk.CTkToplevel(self.root)
        stats_win.title("Статистика")
        stats_win.geometry("420x390") # Adjusted height for more info
        stats_win.resizable(False, False)
        stats_win.transient(self.root)
        stats_win.grab_set()

        title_font = ctk.CTkFont(size=14, weight="bold")
        ctk.CTkLabel(stats_win, text="Статистика перевода", font=title_font, anchor="center").pack(pady=(15, 10), padx=15, fill='x')

        info_frame = ctk.CTkFrame(stats_win, fg_color="transparent")
        info_frame.pack(pady=5, padx=15, fill='x')
        info_frame.grid_columnconfigure(0, weight=1)
        info_frame.grid_columnconfigure(1, weight=0)

        row = 0
        # File
        ctk.CTkLabel(info_frame, text="Файл:", anchor="w").grid(row=row, column=0, sticky='w', pady=3)
        file_label = ctk.CTkLabel(info_frame, text=os.path.basename(self.xliff_filepath), anchor="e", wraplength=270)
        file_label.grid(row=row, column=1, sticky='e', pady=3, padx=(10,0)); row += 1
        # Languages
        ctk.CTkLabel(info_frame, text="Языки:", anchor="w").grid(row=row, column=0, sticky='w', pady=3)
        ctk.CTkLabel(info_frame, text=f"{self.detected_source_lang} → {self.detected_target_lang}", anchor="e").grid(row=row, column=1, sticky='e', pady=3, padx=(10,0)); row += 1
        # Statistics
        ctk.CTkLabel(info_frame, text="Всего строк (trans-unit):", anchor="w").grid(row=row, column=0, sticky='w', pady=3)
        ctk.CTkLabel(info_frame, text=f"{total_units}", anchor="e").grid(row=row, column=1, sticky='e', pady=3, padx=(10,0)); row += 1
        ctk.CTkLabel(info_frame, text="Не переведено:", anchor="w").grid(row=row, column=0, sticky='w', pady=3)
        ctk.CTkLabel(info_frame, text=f"{untranslated_count}", anchor="e").grid(row=row, column=1, sticky='e', pady=3, padx=(10,0)); row += 1
        ctk.CTkLabel(info_frame, text="Переведено:", anchor="w").grid(row=row, column=0, sticky='w', pady=3)
        ctk.CTkLabel(info_frame, text=f"{translated_count}", anchor="e").grid(row=row, column=1, sticky='e', pady=3, padx=(10,0)); row += 1
        # File info
        ctk.CTkLabel(info_frame, text="Обнаружено файлов:", anchor="w").grid(row=row, column=0, sticky='w', pady=3)
        ctk.CTkLabel(info_frame, text=f"{len(self.available_filenames) - 1}", anchor="e").grid(row=row, column=1, sticky='e', pady=3, padx=(10,0)); row += 1
        ctk.CTkLabel(info_frame, text="Файлов с непереведенными:", anchor="w").grid(row=row, column=0, sticky='w', pady=3)
        ctk.CTkLabel(info_frame, text=f"{len(self.untranslated_filenames)}", anchor="e").grid(row=row, column=1, sticky='e', pady=3, padx=(10,0)); row += 1
        # Overall Progress
        ctk.CTkLabel(info_frame, text="Общий прогресс:", anchor="w").grid(row=row, column=0, sticky='w', pady=(10,3)) # Add padding before progress
        ctk.CTkLabel(info_frame, text=f"{progress_value*100:.2f}%", anchor="e").grid(row=row, column=1, sticky='e', pady=(10,3), padx=(10,0)); row += 1

        stats_progress_bar = ctk.CTkProgressBar(stats_win, orientation="horizontal", height=15)
        stats_progress_bar.pack(pady=(10, 15), padx=15, fill='x') # Adjusted padding
        stats_progress_bar.set(progress_value)

        close_button = ctk.CTkButton(stats_win, text="Закрыть", command=stats_win.destroy)
        close_button.pack(pady=(0, 15)) # Adjusted padding

        stats_win.focus_set()
        stats_win.bind("<Escape>", lambda e: stats_win.destroy())

        # Center window
        self.root.update_idletasks()
        stats_win.update_idletasks()
        main_x, main_y = self.root.winfo_x(), self.root.winfo_y()
        main_w, main_h = self.root.winfo_width(), self.root.winfo_height()
        stat_w, stat_h = stats_win.winfo_width(), stats_win.winfo_height()
        pos_x = main_x + (main_w // 2) - (stat_w // 2)
        pos_y = main_y + (main_h // 2) - (stat_h // 2)
        stats_win.geometry(f"+{pos_x}+{pos_y}")

    # --- Поиск ---
    def find_next(self, event=None):
        """Ищет следующее вхождение текста в редакторе."""
        target_widget = self._get_inner_text_widget()
        if not target_widget or not self.xliff_tree: return
        if not self.search_entry: return

        search_term = self.search_entry.get()
        if not search_term:
            self.update_status("Введите текст для поиска.")
            self.last_search_pos = "1.0"
            try: target_widget.tag_remove("search_highlight", "1.0", tk.END)
            except tk.TclError: pass
            return

        try: target_widget.tag_remove("search_highlight", "1.0", tk.END)
        except tk.TclError: pass

        try:
            start_pos = target_widget.index(f"{self.last_search_pos}+1c")
            match_pos = target_widget.search(search_term, start_pos, stopindex=tk.END, nocase=True)

            if match_pos:
                end_pos = f"{match_pos}+{len(search_term)}c"
                try: target_widget.tag_config("search_highlight", background="yellow", foreground="black")
                except tk.TclError: pass
                target_widget.tag_add("search_highlight", match_pos, end_pos)
                target_widget.see(match_pos)
                self.last_search_pos = match_pos
                self.update_status(f"Найдено: '{search_term}'")
                self.set_focus_on_editor()
                target_widget.tag_raise(tk.SEL)
            else:
                # Wrap search from beginning
                self.last_search_pos = "1.0"
                match_pos = target_widget.search(search_term, self.last_search_pos, stopindex=tk.END, nocase=True)
                if match_pos:
                    end_pos = f"{match_pos}+{len(search_term)}c"
                    try: target_widget.tag_config("search_highlight", background="yellow", foreground="black")
                    except tk.TclError: pass
                    target_widget.tag_add("search_highlight", match_pos, end_pos)
                    target_widget.see(match_pos)
                    self.last_search_pos = match_pos
                    self.update_status(f"Найдено с начала: '{search_term}'")
                    self.set_focus_on_editor()
                    target_widget.tag_raise(tk.SEL)
                else:
                    print(f"Текст '{search_term}' не найден на текущей странице.")
                    self.update_status(f"Текст '{search_term}' не найден.")
                    self.last_search_pos = "1.0"

        except tk.TclError as e:
            self.update_status("Ошибка во время поиска.")
        except Exception as e:
             print(f"Ошибка поиска: {e}")
             traceback.print_exc()
             self.update_status("Ошибка поиска.")


    def on_search_entry_change(self, *args):
        """Активирует/деактивирует кнопку поиска при изменении текста в поле."""
        new_search_term = self.search_entry.get() if self.search_entry else ""
        state = tk.NORMAL if new_search_term and self.xliff_tree else tk.DISABLED
        if self.find_next_button:
             self.find_next_button.configure(state=state)

        if new_search_term != self.search_term:
            self.search_term = new_search_term
            self.last_search_pos = "1.0"
            target_widget = self._get_inner_text_widget()
            if target_widget:
                 try: target_widget.tag_remove("search_highlight", "1.0", tk.END)
                 except tk.TclError: pass

    # --- Создание виджетов ---
    # --- ИСПРАВЛЕНО: Добавлен stats_button.pack() и финальная компоновка right_controls ---
    def _create_widgets(self):
        """Создает и размещает все виджеты интерфейса."""

        # --- Top Frame ---
        top_frame = ctk.CTkFrame(self.root, fg_color="transparent")
        top_frame.pack(side=tk.TOP, fill=tk.X, padx=10, pady=(10, 5))
        top_frame.grid_columnconfigure(1, weight=1) # Center spacer

        # --- Left Control Frame (Modes, Translate, Font, Stats) ---
        left_controls = ctk.CTkFrame(top_frame, fg_color="transparent")
        left_controls.grid(row=0, column=0, padx=(0, 5), sticky="w")

        self.markup_mode_button = ctk.CTkButton(left_controls, text="Разметка", command=lambda: self.set_mode('markup'), width=90)
        self.markup_mode_button.pack(side=tk.LEFT, padx=(0, 5))
        self.edit_mode_button = ctk.CTkButton(left_controls, text="Текст", command=lambda: self.set_mode('edit'), width=70)
        self.edit_mode_button.pack(side=tk.LEFT, padx=(0, 15))

        # Translate Group
        translate_group = ctk.CTkFrame(left_controls, fg_color="transparent")
        translate_group.pack(side=tk.LEFT, padx=(0, 15))
        self.translate_button = ctk.CTkButton(translate_group, text="Перевести стр.", command=self.translate_current_page, width=120)
        self.translate_button.pack(side=tk.LEFT, padx=(0, 3))
        self.translator_combobox = ctk.CTkComboBox(
            translate_group, values=TRANSLATOR_SERVICES if TRANSLATION_AVAILABLE else ["N/A"],
            width=90, command=self.on_translator_selected)
        self.translator_combobox.pack(side=tk.LEFT)
        if TRANSLATION_AVAILABLE:
            self.translator_combobox.set(DEFAULT_TRANSLATOR_SERVICE)
            self.on_translator_selected(DEFAULT_TRANSLATOR_SERVICE)
        else:
            self.translator_combobox.configure(state=tk.DISABLED)
            self.translate_button.configure(state=tk.DISABLED, text="Перевод (N/A)")

        # Font Group
        font_group = ctk.CTkFrame(left_controls, fg_color="transparent")
        font_group.pack(side=tk.LEFT, padx=(0, 15))
        self.font_size_decrease_button = ctk.CTkButton(font_group, text="A-", command=lambda: self.change_font_size(-1), width=30)
        self.font_size_decrease_button.pack(side=tk.LEFT, padx=(0, 2))
        self.font_size_increase_button = ctk.CTkButton(font_group, text="A+", command=lambda: self.change_font_size(1), width=30)
        self.font_size_increase_button.pack(side=tk.LEFT)

        # Stats Button <<<--- ADDED BACK
        self.stats_button = ctk.CTkButton(left_controls, text="Статистика", command=self.show_statistics_window, width=90)
        self.stats_button.pack(side=tk.LEFT, padx=(0, 5))

        # --- Right Control Frame (Switch, Filters, Open) ---
        right_controls = ctk.CTkFrame(top_frame, fg_color="transparent")
        right_controls.grid(row=0, column=2, padx=(5, 0), sticky="e")

        # 1. Switch Text Label (Leftmost)
        switch_label = ctk.CTkLabel(right_controls, text="Only not-tr.:")
        switch_label.pack(side=tk.LEFT, padx=(0, 3))

        # 2. Switch (without text)
        self.show_untranslated_switch = ctk.CTkSwitch(
            right_controls, text="",
            command=self._on_show_untranslated_switch_toggle,
            onvalue=True, offvalue=False,
            state=tk.DISABLED, width=0
        )
        self.show_untranslated_switch.pack(side=tk.LEFT, padx=(0, 15)) # Padding after switch

        # 3. File Filter: Label + Combobox
        ctk.CTkLabel(right_controls, text="Файл:").pack(side=tk.LEFT, padx=(0, 3))
        self.file_filter_combobox = ctk.CTkComboBox(
            right_controls, values=[ALL_FILES_FILTER], command=self.on_file_filter_change,
            width=160, state=tk.DISABLED)
        self.file_filter_combobox.pack(side=tk.LEFT, padx=(0, 15)) # Padding after file combo
        self.file_filter_combobox.set(ALL_FILES_FILTER)

        # 4. Status Filter: Label + Combobox
        ctk.CTkLabel(right_controls, text="Статус:").pack(side=tk.LEFT, padx=(0, 3))
        status_filter_options = ["Непереведенные", "Переведенные", "Подтвержденные", "Все статусы"]
        status_map_internal_to_display = {"untranslated": "Непереведенные", "translated": "Переведенные", "approved": "Подтвержденные", "all": "Все статусы"}
        self.status_filter_combobox = ctk.CTkComboBox(
            right_controls, values=status_filter_options, command=self.on_status_filter_change,
            width=130, state=tk.DISABLED)
        self.status_filter_combobox.pack(side=tk.LEFT, padx=(0, 15)) # Padding after status combo
        self.status_filter_combobox.set(status_map_internal_to_display.get(DEFAULT_STATUS_FILTER))

        # 5. Open Button (Rightmost)
        self.open_button = ctk.CTkButton(right_controls, text="Открыть XLIFF...", command=self.load_xliff, width=120)
        self.open_button.pack(side=tk.LEFT, padx=(0, 0)) # No padding after last element


        # --- Search Frame ---
        search_frame = ctk.CTkFrame(self.root, fg_color="transparent")
        search_frame.pack(side=tk.TOP, fill=tk.X, padx=10, pady=(0, 5))

        search_label = ctk.CTkLabel(search_frame, text="Поиск (на стр.):")
        search_label.pack(side=tk.LEFT, padx=(0, 5))

        search_var = tk.StringVar()
        search_var.trace_add("write", self.on_search_entry_change)
        self.search_entry = ctk.CTkEntry(search_frame, placeholder_text="Введите текст...", width=300, textvariable=search_var)
        self.search_entry.pack(side=tk.LEFT, padx=(0, 5), fill=tk.X, expand=True)
        self.search_entry.bind("<Return>", self.find_next)
        self.search_entry.bind("<KP_Enter>", self.find_next)

        self.find_next_button = ctk.CTkButton(search_frame, text="Найти далее", command=self.find_next, width=100)
        self.find_next_button.pack(side=tk.LEFT, padx=(5, 0))
        self.find_next_button.configure(state=tk.DISABLED)


        # --- Bottom Frame (Status and Save) ---
        bottom_frame_outer = ctk.CTkFrame(self.root)
        bottom_frame_outer.pack(side=tk.BOTTOM, fill=tk.X, padx=0, pady=0)
        bottom_frame_outer.grid_columnconfigure(0, weight=1)

        self.status_label = ctk.CTkLabel(bottom_frame_outer, text="Загрузите XLIFF файл...", anchor=tk.W)
        self.status_label.grid(row=0, column=0, padx=(10, 5), pady=5, sticky="ew")

        self.save_button = ctk.CTkButton(bottom_frame_outer, text="Сохранить XLIFF", command=self.save_xliff, width=130)
        self.save_button.grid(row=0, column=1, padx=(5, 10), pady=5, sticky="e")
        self.save_button.configure(state=tk.DISABLED)

        # --- Navigation Frame ---
        nav_frame = ctk.CTkFrame(self.root, fg_color="transparent")
        nav_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=(0, 5))
        nav_content_frame = ctk.CTkFrame(nav_frame, fg_color="transparent")
        nav_content_frame.pack(anchor=tk.CENTER)

        _nav_font = ctk.CTkFont(size=11)
        self.prev_button = ctk.CTkButton(nav_content_frame, text="<< Пред.", command=self.go_to_prev_page, width=70, font=_nav_font)
        self.prev_button.pack(side=tk.LEFT, padx=(0, 2))
        self.page_label = ctk.CTkLabel(nav_content_frame, text="Страница: - / -", width=220, font=_nav_font, anchor=tk.CENTER)
        self.page_label.pack(side=tk.LEFT, padx=2)
        self.page_entry = ctk.CTkEntry(nav_content_frame, textvariable=self.page_var, width=45, justify=tk.CENTER, font=_nav_font)
        self.page_entry.pack(side=tk.LEFT, padx=1)
        self.page_entry.bind("<Return>", self.go_to_page)
        self.page_entry.bind("<KP_Enter>", self.go_to_page)
        self.go_button = ctk.CTkButton(nav_content_frame, text="Перейти", command=self.go_to_page, width=60, font=_nav_font)
        self.go_button.pack(side=tk.LEFT, padx=2)
        self.next_button = ctk.CTkButton(nav_content_frame, text="След. >>", command=self.go_to_next_page, width=70, font=_nav_font)
        self.next_button.pack(side=tk.LEFT, padx=(2, 15))
        page_size_label = ctk.CTkLabel(nav_content_frame, text="Строк:", font=_nav_font)
        page_size_label.pack(side=tk.LEFT, padx=(5, 1))
        self.page_size_entry = ctk.CTkEntry(nav_content_frame, textvariable=self.page_size_var, width=45, justify=tk.CENTER, font=_nav_font)
        self.page_size_entry.pack(side=tk.LEFT, padx=(1, 2))
        self.page_size_entry.bind("<Return>", self.update_page_size)
        self.page_size_entry.bind("<KP_Enter>", self.update_page_size)
        self.page_size_button = ctk.CTkButton(nav_content_frame, text="Прим.", command=self.update_page_size, width=50, font=_nav_font)
        self.page_size_button.pack(side=tk.LEFT, padx=2)


        # --- Text Editor ---
        editor_frame = ctk.CTkFrame(self.root, fg_color="transparent")
        editor_frame.pack(expand=True, fill=tk.BOTH, padx=10, pady=(0, 5))

        try: editor_font = ctk.CTkFont(family="Consolas", size=self.current_font_size)
        except: editor_font = ctk.CTkFont(family="Courier New", size=self.current_font_size)

        self.editor_textbox = ctk.CTkTextbox(
            editor_frame, wrap=tk.NONE, undo=True, font=editor_font,
            border_width=1, padx=5, pady=5 )

        editor_scrollbar_y = ctk.CTkScrollbar(editor_frame, command=self.editor_textbox.yview)
        editor_scrollbar_y.pack(side=tk.RIGHT, fill=tk.Y)
        editor_scrollbar_x = ctk.CTkScrollbar(editor_frame, command=self.editor_textbox.xview, orientation="horizontal")
        editor_scrollbar_x.pack(side=tk.BOTTOM, fill=tk.X)

        self.editor_textbox.configure(yscrollcommand=editor_scrollbar_y.set, xscrollcommand=editor_scrollbar_x.set)
        self.editor_textbox.pack(expand=True, fill=tk.BOTH, side=tk.LEFT)

        # --- Inner widget and bindings ---
        text_widget = self._get_inner_text_widget()
        if text_widget:
            context_menu = tk.Menu(text_widget, tearoff=0)
            context_menu.add_command(label="Вырезать", command=lambda: text_widget.event_generate("<<Cut>>") if self.can_cut_now() else None)
            context_menu.add_command(label="Копировать", command=lambda: text_widget.event_generate("<<Copy>>") if self.can_copy_now() else None)
            context_menu.add_command(label="Вставить", command=lambda: text_widget.event_generate("<<Paste>>") if self.can_paste_now() else None)
            context_menu.add_separator()
            context_menu.add_command(label="Выделить все",
                                    command=lambda: self.select_all_text(None))

            def show_context_menu(event):
                can_cut = self.can_cut_now()
                can_copy = self.can_copy_now()
                can_paste = self.can_paste_now()

                is_empty = True
                try: is_empty = not bool(text_widget.get("1.0", tk.END + "-1c").strip())
                except: pass

                context_menu.entryconfigure("Вырезать", state=tk.NORMAL if can_cut else tk.DISABLED)
                context_menu.entryconfigure("Копировать", state=tk.NORMAL if can_copy else tk.DISABLED)
                context_menu.entryconfigure("Вставить", state=tk.NORMAL if can_paste else tk.DISABLED)
                context_menu.entryconfigure("Выделить все", state=tk.NORMAL if not is_empty else tk.DISABLED)

                if can_cut or can_copy or can_paste or not is_empty:
                    context_menu.tk_popup(event.x_root, event.y_root)

            text_widget.bind("<Button-3>", show_context_menu) # Right-click
            text_widget.bind("<Button-2>", show_context_menu) # Middle-click (some systems)

            # Global key bindings
            self.root.bind_all("<Control-a>", self.select_all_text); self.root.bind_all("<Control-A>", self.select_all_text)
            self.root.bind_all("<Command-a>", self.select_all_text); self.root.bind_all("<Command-A>", self.select_all_text) # macOS
            self.root.bind_all("<Control-x>", self.cut_text); self.root.bind_all("<Control-X>", self.cut_text)
            self.root.bind_all("<Command-x>", self.cut_text); self.root.bind_all("<Command-X>", self.cut_text) # macOS
            self.root.bind_all("<Control-c>", self.copy_text); self.root.bind_all("<Control-C>", self.copy_text)
            self.root.bind_all("<Command-c>", self.copy_text); self.root.bind_all("<Command-C>", self.copy_text) # macOS
            self.root.bind_all("<Control-v>", self.paste_text); self.root.bind_all("<Control-V>", self.paste_text)
            self.root.bind_all("<Command-v>", self.paste_text); self.root.bind_all("<Command-V>", self.paste_text) # macOS
            self.root.bind_all("<Control-s>", lambda e: self.save_xliff()); self.root.bind_all("<Control-S>", lambda e: self.save_xliff())
            self.root.bind_all("<Command-s>", lambda e: self.save_xliff()); self.root.bind_all("<Command-S>", lambda e: self.save_xliff()) # macOS
            self.root.bind_all("<Control-f>", lambda e: self.search_entry.focus_set() if self.search_entry else None)
            self.root.bind_all("<Control-F>", lambda e: self.search_entry.focus_set() if self.search_entry else None)
            self.root.bind_all("<Command-f>", lambda e: self.search_entry.focus_set() if self.search_entry else None) # macOS
            self.root.bind_all("<Command-F>", lambda e: self.search_entry.focus_set() if self.search_entry else None) # macOS
            self.root.bind_all("<F3>", self.find_next)

            # Bind modification event
            text_widget.bind("<<Modified>>", self.handle_text_modification)
        else:
            print(f"{Fore.RED}Критическая ошибка: Не удалось получить внутренний tk.Text! Функционал будет ограничен.{Style.RESET_ALL}")


    # --- Управление режимами ---
    def set_mode(self, mode, force_update=False):
        """Переключает режим редактора ('markup' или 'edit')."""
        active_color = inactive_color = None
        try:
            active_color = ctk.ThemeManager.theme["CTkButton"]["fg_color"]
            inactive_color = ctk.ThemeManager.theme["CTkButton"]["hover_color"]
        except Exception as e:
             print(f"{Fore.YELLOW}Warning: Could not get theme colors for button state: {e}{Style.RESET_ALL}")
             active_color = ("#3a7ebf", "#1f538d")
             inactive_color = ("#325882", "#14375e")

        if not self.xliff_tree and not force_update:
            if mode == 'markup':
                if self.markup_mode_button and active_color: self.markup_mode_button.configure(fg_color=active_color)
                if self.edit_mode_button and inactive_color: self.edit_mode_button.configure(fg_color=inactive_color)
            elif mode == 'edit':
                if self.markup_mode_button and inactive_color: self.markup_mode_button.configure(fg_color=inactive_color)
                if self.edit_mode_button and active_color: self.edit_mode_button.configure(fg_color=active_color)
            self.current_mode = mode
            self.update_navigation_buttons_state() # Ensure correct button enable/disable state
            return

        if not force_update and mode == self.current_mode: return

        if not force_update and self.xliff_tree:
            if not self.save_current_page_data_if_dirty(prompt_save=True):
                print("Mode change cancelled by user or save error.")
                return

        print(f"Setting mode to: {mode}")
        previous_mode = self.current_mode
        self.current_mode = mode

        general_state = tk.NORMAL if self.xliff_tree else tk.DISABLED

        if mode == 'markup':
            if self.markup_mode_button: self.markup_mode_button.configure(state=tk.DISABLED, fg_color=active_color)
            if self.edit_mode_button: self.edit_mode_button.configure(state=general_state, fg_color=inactive_color)
            if self.editor_textbox: self.editor_textbox.configure(wrap=tk.NONE)
            self.update_status(f"Режим: Разметка XML ({self._get_current_filter_description()})")
        elif mode == 'edit':
            if self.markup_mode_button: self.markup_mode_button.configure(state=general_state, fg_color=inactive_color)
            if self.edit_mode_button: self.edit_mode_button.configure(state=tk.DISABLED, fg_color=active_color)
            if self.editor_textbox: self.editor_textbox.configure(wrap=tk.WORD)
            self.update_status(f"Режим: Редактирование текста ({self._get_current_filter_description()})")
        else:
            print(f"{Fore.RED}Error: Unknown mode '{mode}'. Reverting to '{previous_mode}'.{Style.RESET_ALL}")
            self.current_mode = previous_mode
            self.set_mode(previous_mode, force_update=True)
            return

        if self.xliff_tree and (mode != previous_mode or force_update):
            self._display_current_page()

        self.set_focus_on_editor()


    def handle_text_modification(self, event=None):
        """Обработчик события <<Modified>> от внутреннего tk.Text."""
        inner_widget = self._get_inner_text_widget()
        if inner_widget:
            try:
                is_modified = inner_widget.edit_modified()
                if is_modified:
                    if not self.is_dirty:
                       self.set_dirty_flag(True)
                    if self.save_button and self.save_button.cget('state') == tk.DISABLED:
                        self.save_button.configure(state=tk.NORMAL)

            except tk.TclError: pass


    def on_translator_selected(self, choice):
        """Обновляет выбранный сервис перевода."""
        print(f"Выбран сервис перевода: {choice}")
        self.selected_translator_service = choice

    def on_closing(self):
        """Обработчик события закрытия окна."""
        page_save_ok = self.save_current_page_data_if_dirty(prompt_save=False)
        if not page_save_ok:
            if not messagebox.askokcancel("Ошибка сохранения страницы",
                                          "Не удалось сохранить изменения на текущей странице из-за ошибки.\n"
                                          "Все равно выйти (изменения страницы будут потеряны)?",
                                          icon='warning', parent=self.root):
                return

        if self.is_dirty:
            result = messagebox.askyesnocancel("Выход",
                                               "Есть несохраненные изменения.\n"
                                               "Сохранить их в файл перед выходом?",
                                               icon='warning', parent=self.root)
            if result is True: # Yes
                self.save_xliff()
                if self.is_dirty: # Save failed
                    if messagebox.askokcancel("Ошибка сохранения файла",
                                              "Не удалось сохранить изменения в файл.\n"
                                              "Все равно выйти (все изменения будут потеряны)?",
                                              icon='error', parent=self.root):
                        self.root.destroy()
                    else: return
                else: # Save successful
                    self.root.destroy()
            elif result is False: # No
                if messagebox.askyesno("Подтверждение",
                                       "Вы уверены, что хотите выйти без сохранения изменений?",
                                       icon='warning', parent=self.root):
                    self.root.destroy()
                else: return
            else: # Cancel
                return
        else: # Not dirty
            self.root.destroy()

# --- Запуск приложения ---
def main():
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
        _test_button = ctk.CTkButton(_test_root)
        _test_root.destroy()
        print("Проверка Tkinter и CustomTkinter прошла успешно.")
    except tk.TclError as e:
        if "display" in str(e).lower():
             print(f"{Fore.RED}Ошибка Tkinter: Не удалось подключиться к дисплею.{Style.RESET_ALL}")
             display_available = False
        else:
             print(f"{Fore.RED}Неожиданная ошибка Tcl/Tk при проверке дисплея:{Style.RESET_ALL}\n{e}")
             traceback.print_exc()
             display_available = False
             sys.exit(f"Критическая ошибка Tcl/Tk: {e}")

    if display_available:
        root = None
        try:
            root = ctk.CTk()
            app = XliffEditorApp(root)
            if filepath_from_cli:
                root.after(100, lambda: app.load_xliff(filepath_arg=filepath_from_cli))
            root.mainloop()
        except tk.TclError as e:
             print(f"{Fore.RED}Критическая ошибка Tcl/Tk во время выполнения:{Style.RESET_ALL}")
             traceback.print_exc()
             error_root = tk.Tk()
             error_root.withdraw()
             messagebox.showerror("Критическая ошибка Tcl/Tk", f"Ошибка Tcl/Tk:\n{e}\nПриложение будет закрыто.", parent=root)
             error_root.destroy()
             sys.exit(1)
        except Exception as e:
             print(f"{Fore.RED}Критическая ошибка Python во время выполнения:{Style.RESET_ALL}")
             traceback.print_exc()
             error_root = tk.Tk()
             error_root.withdraw()
             messagebox.showerror("Критическая ошибка Python", f"Ошибка Python:\n{type(e).__name__}: {e}\nПриложение будет закрыто.", parent=root)
             error_root.destroy()
             sys.exit(1)
    else:
         print("Запуск GUI отменен из-за отсутствия или ошибки дисплея.")
         try:
             root_err = tk.Tk(); root_err.withdraw()
             messagebox.showerror("Ошибка запуска", "Не удалось инициализировать графический интерфейс.\nУбедитесь, что дисплей доступен.")
             root_err.destroy()
         except Exception: pass
         sys.exit(1)

if __name__ == "__main__":
    main()

# --- END OF FILE xliff_editor_gui.py ---