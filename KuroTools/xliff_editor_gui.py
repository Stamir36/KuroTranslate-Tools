# --- START OF FILE xliff_editor_gui_v2.py ---

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
        self.root.geometry("1200x800") # Slightly larger default size

        # --- Состояние приложения ---
        self.xliff_tree = None
        self.xliff_root = None
        self.xliff_filepath = ""
        self.all_trans_units = []           # Список ВСЕХ <trans-unit> объектов lxml
        self.unit_status_map = {}           # Словарь {unit_id: 'untranslated' | 'translated' | 'approved'}
        self.unit_id_to_filename_map = {}   # Словарь {unit_id: filename}
        self.available_filenames = [ALL_FILES_FILTER] # Список доступных имен файлов для фильтра
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
        self.stats_button = None
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
        self.selected_filename_filter = ALL_FILES_FILTER
        self.selected_status_filter = DEFAULT_STATUS_FILTER # Reset status filter
        self.current_page_units_map = {}
        self.filtered_display_ids = []
        self.current_page_index = 0
        self.items_per_page = ITEMS_PER_PAGE_DEFAULT # Reset page size
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
        if self.stats_button: self.stats_button.configure(state=tk.DISABLED)
        if self.page_var: self.page_var.set("")
        if self.page_label: self.page_label.configure(text="Страница: - / -")
        if self.file_filter_combobox:
            self.file_filter_combobox.configure(values=[ALL_FILES_FILTER], state=tk.DISABLED)
            self.file_filter_combobox.set(ALL_FILES_FILTER)
        if self.status_filter_combobox:
            self.status_filter_combobox.set(DEFAULT_STATUS_FILTER)
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
        print(f"{Fore.YELLOW}Warning: Could not get inner text widget.{Style.RESET_ALL}")
        return None

    def _check_inner_focus(self):
        """Проверяет, находится ли фокус на внутреннем tk.Text виджете."""
        inner_widget = self._get_inner_text_widget()
        if not inner_widget or not self.main_window: return False
        try: return self.main_window.focus_get() == inner_widget
        except Exception: return False

    # --- Контекстное меню и биндинги ---
    # --- Helper methods for context menu state ---
    def can_cut_now(self):
        """Checks if cutting is currently allowed."""
        target_widget = self._get_inner_text_widget()
        if not target_widget: return False
        is_focused = self._check_inner_focus() # Focus might not be strictly needed for menu, but consistent with shortcut
        return (self.xliff_tree is not None and
                target_widget.cget("state") == tk.NORMAL and
                target_widget.tag_ranges(tk.SEL))

    def can_copy_now(self):
        """Checks if copying is currently allowed."""
        target_widget = self._get_inner_text_widget()
        if not target_widget: return False
        is_focused = self._check_inner_focus() # Focus might not be strictly needed for menu, but consistent with shortcut
        return (target_widget.tag_ranges(tk.SEL)) # Only selection matters for copy

    def can_paste_now(self):
        """Checks if pasting is currently allowed."""
        target_widget = self._get_inner_text_widget()
        if not target_widget: return False
        is_focused = self._check_inner_focus() # Focus might not be strictly needed for menu, but consistent with shortcut
        has_clipboard = False
        try: has_clipboard = bool(self.main_window.clipboard_get())
        except: pass
        return (self.xliff_tree is not None and
                target_widget.cget("state") == tk.NORMAL and
                has_clipboard) # Check if clipboard has content

    def select_all_text(self, event=None):
        # Этот метод не генерирует событие, а делает все сам, оставляем как есть.
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
            return 'break' # Останавливаем дальнейшую обработку Ctrl+A
        return None

    def cut_text(self, event=None):
        target_widget = self._get_inner_text_widget()
        if not target_widget: return 'break' # Блокируем, если виджета нет

        is_focused = self._check_inner_focus()
        # Разрешаем вырезать только если: файл загружен, виджет в фокусе, виджет редактируем, есть выделение
        can_cut = (self.xliff_tree is not None and
                   is_focused and
                   target_widget.cget("state") == tk.NORMAL and
                   target_widget.tag_ranges(tk.SEL)) # Проверяем наличие выделения

        if can_cut:
            print("Cut condition met, allowing default action.")
            # НЕ возвращаем 'break', позволяя стандартному механизму сработать
            return None
        else:
            print("Cut condition NOT met, blocking action.")
            # Возвращаем 'break', чтобы заблокировать стандартное действие
            return 'break'

    def copy_text(self, event=None):
        target_widget = self._get_inner_text_widget()
        if not target_widget: return 'break' # Блокируем, если виджета нет

        is_focused = self._check_inner_focus()
         # Разрешаем копировать если: виджет в фокусе, есть выделение
         # (Не зависит от xliff_tree или state=NORMAL, копировать можно всегда из видимого текста)
        can_copy = (is_focused and
                    target_widget.tag_ranges(tk.SEL)) # Проверяем наличие выделения

        if can_copy:
            print("Copy condition met, allowing default action.")
             # НЕ возвращаем 'break', позволяя стандартному механизму сработать
            return None
        else:
            print("Copy condition NOT met, blocking action.")
            # Возвращаем 'break', чтобы заблокировать стандартное действие (хотя оно и так бы не сработало без выделения)
            return 'break'

    def paste_text(self, event=None):
        target_widget = self._get_inner_text_widget()
        if not target_widget: return 'break' # Блокируем, если виджета нет

        is_focused = self._check_inner_focus()
        # Разрешаем вставку только если: файл загружен, виджет в фокусе, виджет редактируем
        can_paste = (self.xliff_tree is not None and
                     is_focused and
                     target_widget.cget("state") == tk.NORMAL)

        if can_paste:
            print("Paste condition met, allowing default action.")
            # НЕ возвращаем 'break', позволяя стандартному механизму сработать
            return None
        else:
            print("Paste condition NOT met, blocking action.")
            # Возвращаем 'break', чтобы заблокировать стандартное действие
            return 'break'

    def set_focus_on_editor(self):
        """Устанавливает фокус на внутренний текстовый виджет."""
        inner_widget = self._get_inner_text_widget()
        if inner_widget:
            try: inner_widget.focus_set()
            except tk.TclError as e: print(f"Ошибка при установке фокуса: {e}")

    # --- Навигация и размер страницы ---
    def update_page_size(self, *args):
        """Обрабатывает изменение размера страницы."""
        if not self.xliff_tree: return # Не делаем ничего, если файл не загружен
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
                        # Пытаемся сохранить молча, если не получилось - отменяем смену размера
                        if not self.save_current_page_data_if_dirty(prompt_save=False):
                            messagebox.showerror("Ошибка", "Не удалось сохранить изменения. Смена размера отменена.")
                            self.page_size_var.set(str(self.items_per_page))
                            return
                        # Если сохранили или пользователь отказался - сбрасываем флаг модификации виджета
                        if inner_widget:
                            try: inner_widget.edit_modified(False)
                            except tk.TclError: pass

                current_first_item_global_index_in_filtered_list = self.current_page_index * self.items_per_page
                self.items_per_page = new_size
                self.current_page_index = current_first_item_global_index_in_filtered_list // self.items_per_page

                self._display_current_page()
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
        self.update_navigation_buttons_state()

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
                    self.page_var.set(str(self.current_page_index + 1))
                    return
                self.current_page_index = new_page_index
                self._display_current_page()
                self.update_status(f"Переход на страницу {self.current_page_index + 1} ({self._get_current_filter_description()})")
                self.set_focus_on_editor()
            else:
                messagebox.showwarning("Неверный номер", f"Введите номер страницы от 1 до {num_pages}.")
                self.page_var.set(str(self.current_page_index + 1))
        except ValueError:
            messagebox.showwarning("Неверный ввод", "Введите числовое значение номера страницы.")
            self.page_var.set(str(self.current_page_index + 1))
        except Exception as e:
            messagebox.showerror("Ошибка", f"Ошибка при переходе на страницу: {e}\n{traceback.format_exc()}")
            self.page_var.set(str(self.current_page_index + 1))

    def go_to_next_page(self):
        """Переходит на следующую страницу."""
        num_pages = math.ceil(len(self.filtered_display_ids) / self.items_per_page) if self.filtered_display_ids else 1
        if self.current_page_index < num_pages - 1:
            if not self.save_current_page_data_if_dirty(prompt_save=True): return
            self.current_page_index += 1
            self._display_current_page()
            self.update_status(f"Переход на страницу {self.current_page_index + 1} ({self._get_current_filter_description()})")
            self.set_focus_on_editor()

    def go_to_prev_page(self):
        """Переходит на предыдущую страницу."""
        if self.current_page_index > 0:
            if not self.save_current_page_data_if_dirty(prompt_save=True): return
            self.current_page_index -= 1
            self._display_current_page()
            self.update_status(f"Переход на страницу {self.current_page_index + 1} ({self._get_current_filter_description()})")
            self.set_focus_on_editor()

    def _get_current_filter_description(self):
        """Возвращает строку с описанием текущих фильтров."""
        file_filter_text = os.path.basename(self.selected_filename_filter) if self.selected_filename_filter != ALL_FILES_FILTER else "Все"
        status_filter_text = {
            "untranslated": "Неперев.",
            "translated": "Перев.",
            "approved": "Подтв.",
            "all": "Все"
        }.get(self.selected_status_filter, self.selected_status_filter)
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

        # Элементы, зависящие только от загрузки файла
        general_state = tk.NORMAL if self.xliff_tree else tk.DISABLED
        if self.page_size_entry: self.page_size_entry.configure(state=general_state)
        if self.page_size_button: self.page_size_button.configure(state=general_state)
        if self.file_filter_combobox: self.file_filter_combobox.configure(state=tk.NORMAL if self.xliff_tree and len(self.available_filenames) > 1 else tk.DISABLED)
        if self.status_filter_combobox: self.status_filter_combobox.configure(state=general_state)
        if self.search_entry: self.search_entry.configure(state=general_state)
        if self.find_next_button: self.find_next_button.configure(state=general_state if self.search_entry and self.search_entry.get() else tk.DISABLED)
        if self.stats_button: self.stats_button.configure(state=general_state)
        if self.markup_mode_button: self.markup_mode_button.configure(state=tk.DISABLED if self.current_mode == 'markup' else general_state)
        if self.edit_mode_button: self.edit_mode_button.configure(state=tk.DISABLED if self.current_mode == 'edit' else general_state)
        if self.font_size_increase_button: self.font_size_increase_button.configure(state=general_state)
        if self.font_size_decrease_button: self.font_size_decrease_button.configure(state=general_state)


        # Обновление метки страницы
        if has_content:
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
        if 5 <= new_size <= 30: # Ограничение размера
            self.current_font_size = new_size
            # Предполагаем, что шрифт Consolas доступен
            try:
                editor_font = ctk.CTkFont(family="Consolas", size=self.current_font_size)
                self.editor_textbox.configure(font=editor_font)
                print(f"Размер шрифта изменен на {self.current_font_size}")
            except tk.TclError:
                 print(f"{Fore.YELLOW}Предупреждение: Шрифт 'Consolas' не найден. Попробуйте другой (напр., Courier New).{Style.RESET_ALL}")
                 try: # Fallback font
                    editor_font = ctk.CTkFont(family="Courier New", size=self.current_font_size)
                    self.editor_textbox.configure(font=editor_font)
                    print(f"Размер шрифта изменен на {self.current_font_size} (использован Courier New)")
                 except Exception as e:
                     print(f"{Fore.RED}Ошибка установки шрифта: {e}{Style.RESET_ALL}")

        else:
            print(f"Размер шрифта {new_size} вне допустимого диапазона (5-30).")

    # --- Функции для работы с XLIFF ---

    def _is_unit_translated(self, unit):
        """Определяет статус перевода юнита ('untranslated', 'translated', 'approved')."""
        if unit is None: return 'untranslated' # Should not happen

        target_elements = unit.xpath("./xliff:target", namespaces=LXML_NSMAP)
        if not target_elements:
            return 'untranslated'
        else:
            target_node = target_elements[0]
            approved_attr = target_node.get('approved')
            has_content = target_node.xpath("normalize-space(.)") # Checks for non-whitespace text

            if approved_attr == 'yes':
                return 'approved' # Approved overrides content check for this status
            elif has_content:
                return 'translated' # Has content, but not explicitly approved
            else:
                return 'untranslated' # No content and not approved

    def _update_unit_statuses_and_filters(self):
        """Пересчитывает статусы всех юнитов и обновляет доступные фильтры."""
        self.unit_status_map.clear()
        self.unit_id_to_filename_map.clear()
        filenames_in_notes = set()
        status_counts = {'untranslated': 0, 'translated': 0, 'approved': 0}

        for unit in self.all_trans_units:
            unit_id = unit.get("id")
            if not unit_id:
                 print(f"{Fore.YELLOW}Предупреждение: <trans-unit> без 'id'. Пропускается.{Style.RESET_ALL}")
                 continue

            # Статус перевода
            status = self._is_unit_translated(unit)
            self.unit_status_map[unit_id] = status
            status_counts[status] += 1

            # Имя файла из <note>
            note_node = unit.find("xliff:note", namespaces=LXML_NSMAP)
            filename = None
            if note_node is not None and note_node.text:
                match = NOTE_FILE_REGEX.match(note_node.text.strip())
                if match:
                    filename = match.group(1).strip()
                    if filename:
                        self.unit_id_to_filename_map[unit_id] = filename
                        filenames_in_notes.add(filename)

        # Обновляем список файлов для фильтра
        self.available_filenames = [ALL_FILES_FILTER] + sorted(list(filenames_in_notes))
        if self.file_filter_combobox:
            current_file_filter = self.file_filter_combobox.get()
            self.file_filter_combobox.configure(values=self.available_filenames)
            # Восстанавливаем выбор, если он все еще доступен, иначе сбрасываем
            if current_file_filter in self.available_filenames:
                 self.file_filter_combobox.set(current_file_filter)
            else:
                 self.selected_filename_filter = ALL_FILES_FILTER
                 self.file_filter_combobox.set(ALL_FILES_FILTER)

            self.file_filter_combobox.configure(state=tk.NORMAL if len(self.available_filenames) > 1 else tk.DISABLED)
            if len(self.available_filenames) > 1: print(f"Обнаружено {len(self.available_filenames)-1} файлов в <note>.")

        # Обновляем фильтр статуса (пока не меняем выбор, только активируем)
        if self.status_filter_combobox:
            self.status_filter_combobox.configure(state=tk.NORMAL)

        print(f"Статистика статусов: Непереведенные={status_counts['untranslated']}, Переведенные={status_counts['translated']}, Подтвержденные={status_counts['approved']}")
        return status_counts['untranslated'] # Возвращаем кол-во непереведенных для статус-бара

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

        self.reset_state() # Сбрасываем все перед загрузкой

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

            # Определение языков
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

            # Получаем все trans-unit
            self.all_trans_units = self.xliff_root.xpath(".//xliff:trans-unit", namespaces=LXML_NSMAP)
            if not self.all_trans_units:
                print(f"{Fore.YELLOW}Предупреждение: В файле не найдено <trans-unit>.{Style.RESET_ALL}")

            # Обновляем статусы, фильтры и т.д.
            untranslated_count = self._update_unit_statuses_and_filters()

            # Применяем начальные фильтры (по умолчанию: все файлы, непереведенные)
            self.apply_current_filters(reset_page=True)

            self.set_dirty_flag(False)
            self.set_mode(DEFAULT_MODE, force_update=True) # Устанавливаем дефолтный режим

            self.update_status(f"Загружен: {os.path.basename(filepath)} | Всего: {len(self.all_trans_units)} | Неперев.: {untranslated_count} | Языки: {self.detected_source_lang} -> {self.detected_target_lang}")
            self.update_title()
            if self.editor_textbox:
                self.editor_textbox.configure(state=tk.NORMAL)
                self.set_focus_on_editor()
            # update_navigation_buttons_state() вызывается внутри apply_current_filters

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
                return False # Считаем, что сохранить не удалось

        if not textbox_modified: return True # Нет изменений в редакторе

        should_save = True
        if prompt_save:
            mode_text = "разметки" if self.current_mode == 'markup' else "текста"
            filter_desc = self._get_current_filter_description()
            result = messagebox.askyesnocancel("Сохранить изменения?", f"Сохранить изменения на стр. {self.current_page_index + 1} (режим {mode_text}, {filter_desc})?")
            if result is None: return False # Отмена
            if result is False: # Нет (не сохранять)
                should_save = False
                if inner_widget:
                    try: inner_widget.edit_modified(False) # Сбрасываем флаг виджета
                    except tk.TclError: pass
                return True # Возвращаем успех, т.к. пользователь сознательно отказался

        if should_save:
            success = False
            print(f"Сохранение данных страницы {self.current_page_index + 1}...")
            if self.current_mode == 'markup':
                success = self._save_markup_page_data(force_check=True) # force_check нужен
                if not success:
                    messagebox.showerror("Ошибка сохранения", "Не удалось сохранить изменения (разметка). Проверьте корректность XML.")
                    return False
            elif self.current_mode == 'edit':
                success = self._save_edit_page_data(force_check=True) # force_check нужен
                if not success:
                    messagebox.showerror("Ошибка сохранения", "Не удалось сохранить изменения (редактирование).")
                    return False

            if success:
                if inner_widget:
                    try:
                        inner_widget.edit_modified(False) # Сбрасываем флаг виджета после успешного сохранения
                        print(f"Флаг модификации редактора сброшен после сохранения стр. {self.current_page_index + 1}.")
                    except tk.TclError: pass
                # Пересчет статусов и фильтров произойдет внутри _save_..._page_data через apply_current_filters
                return True
            else:
                 # Этого не должно произойти, если предыдущие проверки прошли
                 messagebox.showerror("Ошибка", "Непредвиденная ошибка при сохранении страницы.")
                 return False
        else: # Пользователь выбрал "Нет"
            return True

    def save_xliff(self):
        """Сохраняет все изменения из памяти в XLIFF файл."""
        if self.xliff_tree is None or not self.xliff_filepath:
            messagebox.showwarning("Нет данных", "Сначала загрузите XLIFF файл.")
            return

        # Сначала пытаемся сохранить данные текущей страницы, если они были изменены
        # Не спрашиваем пользователя здесь, просто пытаемся сохранить
        if not self.save_current_page_data_if_dirty(prompt_save=False):
            messagebox.showerror("Ошибка", "Не удалось сохранить изменения текущей страницы. Исправьте ошибки перед сохранением файла.")
            return

        # Проверяем is_dirty еще раз, т.к. save_current_page_data_if_dirty мог его установить
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

            # Просто записываем текущее дерево lxml
            self.xliff_tree.write(
                output_buffer,
                pretty_print=True,
                encoding='utf-8',
                xml_declaration=True,
            )
            xml_content = output_buffer.getvalue()

            # Проверка корректности перед записью (опционально, но полезно)
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

            self.set_dirty_flag(False) # Сбрасываем флаг ТОЛЬКО при успешном сохранении
            # Сбрасываем флаг модификации редактора, т.к. все сохранено
            inner_widget = self._get_inner_text_widget()
            if inner_widget:
                try: inner_widget.edit_modified(False)
                except tk.TclError: pass

            # Обновляем статус с актуальным числом непереведенных
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
                     self.editor_textbox.edit_modified(False)
                     editor_state = tk.NORMAL if self.xliff_tree else tk.DISABLED
                     self.editor_textbox.configure(state=editor_state)
                 except Exception as e: print(f"Ошибка вставки в обертку: {e}")
            return

        try:
            editor_state = tk.NORMAL if self.xliff_tree else tk.DISABLED
            self.editor_textbox.configure(state=tk.NORMAL)
            target_widget.configure(state=tk.NORMAL)
            target_widget.delete("1.0", tk.END)

            # Удаляем старые теги подсветки
            for tag in target_widget.tag_names():
                if tag.startswith("Token_") or tag == "search_highlight": # Удаляем и теги поиска
                    try: target_widget.tag_delete(tag)
                    except tk.TclError: pass # Игнорируем ошибку, если тега уже нет

            if not PYGMENTS_AVAILABLE or TEXT_HIGHLIGHT_CONFIG["lexer"] is None or self.current_mode != 'markup':
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
                    target_widget.delete("1.0", tk.END) # Очищаем перед вставкой без подсветки
                    target_widget.insert("1.0", text)

            target_widget.edit_modified(False) # Сбрасываем флаг модификации
            self.editor_textbox.configure(state=editor_state)
            target_widget.configure(state=editor_state)
            self.last_search_pos = "1.0" # Сбрасываем позицию поиска при смене страницы/текста

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
        original_status = self.status_label.cget("text") if self.status_label else "Перевод..."
        self.update_status(f"Перевод стр. {self.current_page_index + 1} ({source_lang_for_translator}->{target_lang_for_translator}) (0%)...")

        translated_count = 0; error_count = 0; units_processed = 0
        any_change_made_in_memory = False
        total_units = len(self.current_page_units_map)
        updated_unit_ids = set() # ID юнитов, которые были изменены

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
            self.update_status(original_status)
            return

        # Используем карту текущей страницы
        for unit_id, unit in self.current_page_units_map.items():
            source_node = unit.find("xliff:source", namespaces=LXML_NSMAP)
            source_text_parts = [text for text in source_node.itertext()] if source_node is not None else []
            source_text = "".join(source_text_parts).strip()

            if not source_text:
                print(f"  - Пропуск ID {unit_id}: пустой <source>.")
                units_processed += 1; continue

            target_node = unit.find("xliff:target", namespaces=LXML_NSMAP)
            original_target_text = "".join(target_node.itertext()).strip() if target_node is not None else ""

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
                        else: unit.append(target_node) # Append if no source/note

                    # Обновляем, только если текст реально изменился
                    if original_target_text != translated_text:
                        target_node.clear()
                        target_node.text = translated_text
                        if 'approved' in target_node.attrib: del target_node.attrib['approved'] # Сбрасываем 'approved'
                        any_change_made_in_memory = True
                        updated_unit_ids.add(unit_id)

                    translated_count += 1
                else:
                    print(f"  - {Fore.YELLOW}Предупреждение: Пустой перевод для ID {unit_id}.{Style.RESET_ALL}")
                    error_count += 1
            except Exception as e:
                print(f"  - {Fore.RED}Ошибка перевода ID {unit_id}: {e}{Style.RESET_ALL}")
                error_count += 1
                if "TooManyRequests" in str(e) or "timed out" in str(e) or "429" in str(e):
                    print(f"{Fore.YELLOW}    -> Обнаружена ошибка сети/лимита запросов. Пауза 5 секунд...{Style.RESET_ALL}")
                    time.sleep(5)
                elif "TranslationNotFound" in str(e):
                    print(f"{Fore.YELLOW}    -> Перевод не найден для этого текста.{Style.RESET_ALL}")

            units_processed += 1
            progress = int((units_processed / total_units) * 100)
            self.update_status(f"Перевод стр. {self.current_page_index + 1} ({source_lang_for_translator}->{target_lang_for_translator}) ({progress}%)...")

        final_status_part1 = f"Перевод ({self.selected_translator_service}) завершен."
        final_status_part2 = f"Успешно: {translated_count}, Ошибки/Пропущено: {error_count}."
        print(final_status_part1, final_status_part2)

        if any_change_made_in_memory:
            print("Изменения внесены в память.")
            self.set_dirty_flag(True) # Устанавливаем глобальный флаг изменений

            # Обновляем статусы измененных юнитов
            for unit_id in updated_unit_ids:
                unit = next((u for u in self.all_trans_units if u.get("id") == unit_id), None)
                if unit:
                    self.unit_status_map[unit_id] = self._is_unit_translated(unit) # Пересчитываем статус

            # Переприменяем фильтры и обновляем отображение
            self.apply_current_filters(reset_page=False)

            # Сбрасываем флаг модификации редактора
            inner_widget = self._get_inner_text_widget()
            if inner_widget:
                try: inner_widget.edit_modified(False)
                except tk.TclError: pass

            # Обновляем статус и навигацию (apply_current_filters уже вызвал update_navigation_buttons_state)
            untranslated_count = sum(1 for status in self.unit_status_map.values() if status == 'untranslated')
            self.update_status(f"{final_status_part1} {final_status_part2} | Всего: {len(self.all_trans_units)} | Неперев.: {untranslated_count}")

        else:
            print("Не было внесено изменений в память (возможно, переводы совпали или были ошибки).")
            self.update_navigation_buttons_state() # Восстанавливаем кнопку перевода
            untranslated_count = sum(1 for status in self.unit_status_map.values() if status == 'untranslated')
            self.update_status(f"{final_status_part1} {final_status_part2} | Нет изменений. | Неперев.: {untranslated_count}")

    # --- Функции фильтрации ---

    def on_file_filter_change(self, event=None):
        """Обработчик изменения выбора в комбобоксе фильтра файлов."""
        if not self.file_filter_combobox or not self.xliff_tree: return

        new_filter = self.file_filter_combobox.get()
        if new_filter == self.selected_filename_filter:
            return # Ничего не изменилось

        if not self.save_current_page_data_if_dirty(prompt_save=True):
            print("Смена фильтра файла отменена из-за несохраненных изменений.")
            self.file_filter_combobox.set(self.selected_filename_filter) # Вернуть старое значение
            return

        print(f"Смена фильтра файла на: {new_filter}")
        self.selected_filename_filter = new_filter
        self.apply_current_filters(reset_page=True)
        self.set_focus_on_editor()

    def on_status_filter_change(self, event=None):
        """Обработчик изменения выбора в комбобоксе фильтра статуса."""
        if not self.status_filter_combobox or not self.xliff_tree: return

        # Маппинг отображаемых имен на внутренние ключи
        status_map_display_to_internal = {
            "Непереведенные": "untranslated",
            "Переведенные": "translated",
            "Подтвержденные": "approved",
            "Все статусы": "all",
        }
        selected_display_value = self.status_filter_combobox.get()
        new_filter = status_map_display_to_internal.get(selected_display_value, "all") # Fallback to 'all'

        if new_filter == self.selected_status_filter:
            return # Ничего не изменилось

        if not self.save_current_page_data_if_dirty(prompt_save=True):
            print("Смена фильтра статуса отменена из-за несохраненных изменений.")
            # Найти отображаемое значение для старого фильтра
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
            print(f"Применение фильтров: Файл='{self.selected_filename_filter}', Статус='{self.selected_status_filter}'")
            # 1. Фильтруем по файлу (если не "Все файлы")
            if self.selected_filename_filter == ALL_FILES_FILTER:
                ids_after_file_filter = list(self.unit_status_map.keys()) # Все ID
            else:
                ids_after_file_filter = [
                    unit_id for unit_id, filename in self.unit_id_to_filename_map.items()
                    if filename == self.selected_filename_filter
                ]
                # Добавляем ID без имени файла, если выбран фильтр "Все файлы" (на всякий случай)
                if self.selected_filename_filter == ALL_FILES_FILTER:
                     ids_without_filename = set(self.unit_status_map.keys()) - set(self.unit_id_to_filename_map.keys())
                     ids_after_file_filter.extend(list(ids_without_filename))


            # 2. Фильтруем по статусу (если не "Все статусы")
            if self.selected_status_filter == "all":
                self.filtered_display_ids = ids_after_file_filter
            else:
                self.filtered_display_ids = [
                    unit_id for unit_id in ids_after_file_filter
                    if self.unit_status_map.get(unit_id) == self.selected_status_filter
                ]

            # Сортируем результат по порядку в исходном файле (важно!)
            original_order = {unit.get("id"): i for i, unit in enumerate(self.all_trans_units) if unit.get("id")}
            self.filtered_display_ids.sort(key=lambda unit_id: original_order.get(unit_id, float('inf')))

            print(f"Найдено юнитов после фильтрации: {len(self.filtered_display_ids)}")

        if reset_page:
            self.current_page_index = 0

        # Убедимся, что current_page_index не выходит за пределы нового списка
        num_pages = math.ceil(len(self.filtered_display_ids) / self.items_per_page) if self.filtered_display_ids else 1
        self.current_page_index = max(0, min(self.current_page_index, num_pages - 1))

        # Обновляем отображение текущей страницы с учетом нового фильтра
        self._display_current_page()

        # Обновляем статус и навигацию
        total_units = len(self.all_trans_units)
        untranslated_count = sum(1 for status in self.unit_status_map.values() if status == 'untranslated')
        filter_desc = self._get_current_filter_description()
        self.update_status(f"{filter_desc} | Отображено: {len(self.filtered_display_ids)} | Всего: {total_units} | Неперев.: {untranslated_count}")
        self.update_navigation_buttons_state() # Обновит метку страницы и кнопки


    # --- Функции отображения страниц ---

    def _display_current_page(self):
        """Вызывает нужный метод отображения в зависимости от текущего режима."""
        if self.current_mode == 'markup':
            self._display_markup_page()
        elif self.current_mode == 'edit':
            self._display_edit_page()
        else:
            print(f"Ошибка: Неизвестный режим отображения '{self.current_mode}'")
        # Сбрасываем поиск при смене страницы
        self.last_search_pos = "1.0"
        inner_widget = self._get_inner_text_widget()
        if inner_widget:
            try: inner_widget.tag_remove("search_highlight", "1.0", tk.END)
            except tk.TclError: pass


    def _display_markup_page(self):
        """Отображает текущую страницу в режиме разметки XML (с учетом фильтров)."""
        if self.editor_textbox is None: return

        self.editor_textbox.configure(state=tk.NORMAL) # Включаем для очистки/вставки
        self.current_page_units_map.clear()

        if not self.filtered_display_ids:
            self._set_editor_text_highlighted("<нет строк для отображения (учитывая фильтры)>")
            self.update_navigation_buttons_state()
            return

        # Индекс уже проверен в apply_current_filters
        self.update_navigation_buttons_state() # Обновит метку и кнопки навигации

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
        self.editor_textbox.yview_moveto(0.0) # Прокрутка вверх


    def _display_edit_page(self):
        """Отображает текущую страницу в режиме простого текста (с учетом фильтров)."""
        if self.editor_textbox is None: return

        self.editor_textbox.configure(state=tk.NORMAL)
        self.current_page_units_map.clear()
        target_widget = self._get_inner_text_widget()

        # Убираем XML теги подсветки
        if PYGMENTS_AVAILABLE and target_widget:
            for tag in target_widget.tag_names():
                if tag.startswith("Token_"):
                    try: target_widget.tag_delete(tag)
                    except tk.TclError: pass

        if not self.filtered_display_ids:
            self._set_editor_text_highlighted("<нет строк для отображения (учитывая фильтры)>")
            self.update_navigation_buttons_state()
            return

        # Индекс уже проверен в apply_current_filters
        self.update_navigation_buttons_state()

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
        self._set_editor_text_highlighted(full_text_block) # Вставляем без XML подсветки
        self.editor_textbox.yview_moveto(0.0)


    # --- Функции сохранения страниц ---

    def _save_markup_page_data(self, force_check=False):
        """Парсит XML из редактора (разметка) и обновляет lxml В ПАМЯТИ."""
        inner_widget = self._get_inner_text_widget()
        if not self.current_page_units_map or self.current_mode != 'markup': return True

        textbox_modified = False
        if inner_widget:
            try: textbox_modified = inner_widget.edit_modified()
            except tk.TclError: pass
        if not force_check and not textbox_modified: return True # Нет изменений

        edited_xml_string = self.editor_textbox.get("1.0", "end-1c").strip() if self.editor_textbox else ""
        if not edited_xml_string: # Если редактор пуст, но был модифицирован (например, все удалили)
             print(f"{Fore.YELLOW}Предупреждение: Редактор разметки пуст. Изменения не будут применены к юнитам этой страницы.{Style.RESET_ALL}")
             # TODO: Возможно, стоит добавить логику удаления юнитов, если они были удалены из редактора? Пока нет.
             return True # Считаем успешным, но ничего не делаем

        root_ns_decl = f"xmlns:xliff='{LXML_NSMAP['xliff']}'" if LXML_NSMAP.get('xliff') else ""
        xml_to_parse = f"<root {root_ns_decl}>{edited_xml_string}</root>"
        any_change_made_in_memory = False
        updated_ids_on_page = set()

        try:
            parser = ET.XMLParser(remove_blank_text=False, strip_cdata=False, resolve_entities=False)
            edited_root = ET.fromstring(xml_to_parse, parser=parser)
            edited_units = edited_root.xpath("./xliff:trans-unit", namespaces=LXML_NSMAP)

            if not edited_units and edited_xml_string: # Парсинг успешен, но юнитов нет
                 raise ValueError("Не найдено <trans-unit> в отредактированном тексте.")

            found_ids_in_editor = set()
            id_to_edited_unit = {}
            for edited_unit in edited_units:
                unit_id = edited_unit.get("id")
                if not unit_id: raise ValueError("<trans-unit> без 'id' в редакторе.")
                if unit_id in found_ids_in_editor: raise ValueError(f"Дублирующийся ID '{unit_id}' в редакторе.")
                found_ids_in_editor.add(unit_id)
                id_to_edited_unit[unit_id] = edited_unit

            id_to_original_unit_map = {unit.get("id"): unit for unit in self.all_trans_units if unit.get("id")}
            ids_processed_on_page = set()

            # Итерация по ID, которые *должны* были быть на этой странице
            for unit_id in self.current_page_units_map.keys():
                ids_processed_on_page.add(unit_id)
                original_unit = id_to_original_unit_map.get(unit_id)
                edited_unit = id_to_edited_unit.get(unit_id)

                if original_unit is None:
                    print(f"{Fore.RED}Критическая ошибка: Оригинальный <trans-unit> ID '{unit_id}' не найден!{Style.RESET_ALL}")
                    continue

                if edited_unit is None:
                    print(f"{Fore.YELLOW}Предупреждение: <trans-unit> ID '{unit_id}' (ожидался) не найден в редакторе. Пропуск.{Style.RESET_ALL}")
                    continue # Не обновляем юнит, которого нет в редакторе

                # Сравниваем строки для определения изменений
                try:
                    # Используем каноникализацию C14N для более надежного сравнения XML
                    original_unit_str = ET.tostring(original_unit, method='c14n').strip()
                    edited_unit_str = ET.tostring(edited_unit, method='c14n').strip()
                except Exception as ser_err:
                    print(f"{Fore.YELLOW}Предупреждение: Не удалось выполнить C14N для сравнения ID {unit_id}, используем обычное tostring: {ser_err}{Style.RESET_ALL}")
                    try: # Fallback to pretty print comparison
                       original_unit_str = ET.tostring(original_unit, encoding='unicode', pretty_print=True).strip()
                       edited_unit_str = ET.tostring(edited_unit, encoding='unicode', pretty_print=True).strip()
                    except Exception as ser_err2:
                       print(f"{Fore.RED}Ошибка сериализации при сравнении ID {unit_id}: {ser_err2}{Style.RESET_ALL}")
                       continue # Пропускаем этот юнит

                if original_unit_str != edited_unit_str:
                    parent = original_unit.getparent()
                    if parent is not None:
                        try:
                            # Замена элемента в дереве
                            parent.replace(original_unit, edited_unit)

                            # Обновляем ссылку в all_trans_units (важно!)
                            try:
                                idx_in_all = self.all_trans_units.index(original_unit)
                                self.all_trans_units[idx_in_all] = edited_unit
                            except ValueError: # Если index не сработал (редко), ищем по ID
                                found = False
                                for i, u in enumerate(self.all_trans_units):
                                    if u.get("id") == unit_id:
                                        self.all_trans_units[i] = edited_unit
                                        found = True; break
                                if not found: print(f"{Fore.RED}Критическая ошибка: Не удалось обновить all_trans_units для ID '{unit_id}'.{Style.RESET_ALL}")

                            # Обновляем статус и карту имени файла для измененного юнита
                            self.unit_status_map[unit_id] = self._is_unit_translated(edited_unit)
                            note_node = edited_unit.find("xliff:note", namespaces=LXML_NSMAP)
                            new_filename = None
                            if note_node is not None and note_node.text:
                                match = NOTE_FILE_REGEX.match(note_node.text.strip())
                                if match: new_filename = match.group(1).strip()
                            if new_filename: self.unit_id_to_filename_map[unit_id] = new_filename
                            elif unit_id in self.unit_id_to_filename_map:
                                del self.unit_id_to_filename_map[unit_id] # Удаляем, если note изменился и стал не файловым

                            any_change_made_in_memory = True
                            updated_ids_on_page.add(unit_id)
                        except Exception as replace_err:
                             print(f"{Fore.RED}Ошибка при замене <trans-unit> ID {unit_id}: {replace_err}{Style.RESET_ALL}")
                    else:
                        print(f"{Fore.RED}Критическая ошибка: Не найден родитель для <trans-unit> ID {unit_id}. Замена невозможна.{Style.RESET_ALL}")

            # Проверяем ID, которые были в редакторе, но не ожидались на этой странице
            new_ids_in_editor = found_ids_in_editor - ids_processed_on_page
            if new_ids_in_editor:
                print(f"{Fore.YELLOW}Предупреждение: ID из редактора не ожидались на этой странице и были проигнорированы: {', '.join(new_ids_in_editor)}.{Style.RESET_ALL}")

            if any_change_made_in_memory:
                print(f"Обновлено {len(updated_ids_on_page)} строк в памяти (разметка).")
                self.set_dirty_flag(True)
                self.apply_current_filters(reset_page=False) # Обновит filtered_display_ids и дисплей
                untranslated_count = sum(1 for status in self.unit_status_map.values() if status == 'untranslated')
                self.update_status(f"Изменения стр. {self.current_page_index+1} сохранены в памяти. Всего: {len(self.all_trans_units)} | Неперев.: {untranslated_count}")
            else:
                print("Изменений на странице не обнаружено (разметка).")
            return True # Успешное сохранение (или нет изменений)

        except ET.XMLSyntaxError as e:
            messagebox.showerror("Ошибка парсинга XML", f"Не удалось разобрать XML из редактора:\n{e}")
            return False
        except ValueError as ve:
            messagebox.showerror("Ошибка данных", f"Ошибка в структуре отредакт. текста:\n{ve}")
            return False
        except Exception as e:
            messagebox.showerror("Ошибка обновления", f"Ошибка при обновлении данных (разметка):\n{e}\n{traceback.format_exc()}")
            return False

    def _save_edit_page_data(self, force_check=False):
        """Сохраняет изменения из редактора (текст) В ПАМЯТЬ."""
        inner_widget = self._get_inner_text_widget()
        if not self.current_page_units_map or self.current_mode != 'edit': return True

        textbox_modified = False
        if inner_widget:
            try: textbox_modified = inner_widget.edit_modified()
            except tk.TclError: pass
        if not force_check and not textbox_modified: return True

        edited_text = self.editor_textbox.get("1.0", "end-1c") if self.editor_textbox else ""
        lines = edited_text.split('\n')
        parsed_targets = {}; current_id = None; current_target_lines = []; in_target_section = False

        try:
            # Парсинг текста из редактора (формат ID:, SOURCE:, TARGET:, ---)
            for line in lines:
                line_strip = line.strip()
                if line.startswith("ID: "):
                    if current_id is not None and in_target_section:
                        parsed_targets[current_id] = "\n".join(current_target_lines).rstrip()
                    current_id = line[4:].strip() or None
                    current_target_lines = []
                    in_target_section = False
                elif line.startswith("SOURCE: "):
                    in_target_section = False # Сбрасываем флаг, если встретили SOURCE
                elif line.startswith("TARGET: "):
                    if current_id is None: continue # Игнорируем TARGET без ID
                    in_target_section = True
                    # Берем текст после "TARGET: " (8 символов)
                    current_target_lines.append(line[8:])
                elif line_strip == '-'*30:
                    if current_id is not None and in_target_section:
                        parsed_targets[current_id] = "\n".join(current_target_lines).rstrip()
                    current_id = None
                    current_target_lines = []
                    in_target_section = False
                elif in_target_section and current_id is not None:
                    current_target_lines.append(line) # Добавляем строки, относящиеся к TARGET

            # Сохраняем последний таргет, если файл закончился без разделителя
            if current_id is not None and in_target_section:
                parsed_targets[current_id] = "\n".join(current_target_lines).rstrip()

        except Exception as e:
            messagebox.showerror("Ошибка парсинга текста", f"Ошибка разбора текста редактора:\n{e}\n{traceback.format_exc()}")
            return False

        any_change_made_in_memory = False
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

                if current_target_text != new_target_text:
                    if target_node is None:
                        target_node = ET.Element(f"{{{LXML_NSMAP['xliff']}}}target")
                        source_node = original_unit.find("xliff:source", namespaces=LXML_NSMAP)
                        insert_point = source_node or original_unit.find("xliff:note", namespaces=LXML_NSMAP)
                        if insert_point is not None: insert_point.addnext(target_node)
                        else: original_unit.append(target_node)

                    target_node.clear() # Очищаем содержимое (включая дочерние теги, если были)
                    target_node.text = new_target_text if new_target_text else None # Устанавливаем текст
                    if 'approved' in target_node.attrib: del target_node.attrib['approved'] # Сбрасываем approved

                    # Обновляем статус юнита
                    self.unit_status_map[unit_id] = self._is_unit_translated(original_unit) # Передаем обновленный original_unit

                    any_change_made_in_memory = True
                    updated_ids_on_page.add(unit_id)
            else:
                # ID был на странице, но не найден в распарсенном тексте (возможно, удален?)
                # Пока ничего не делаем, но можно добавить логику удаления, если нужно
                print(f"{Fore.YELLOW}Предупреждение: ID '{unit_id}' (ожидался) не найден в тексте редактора. Изменения для него не сохранены.{Style.RESET_ALL}")


        ids_only_in_editor = set(parsed_targets.keys()) - ids_processed_on_page
        if ids_only_in_editor:
            print(f"{Fore.YELLOW}Предупреждение: ID найдены в редакторе, но не ожидались на этой странице: {', '.join(ids_only_in_editor)}. Они были проигнорированы.{Style.RESET_ALL}")


        if any_change_made_in_memory:
            print(f"Обновлено {len(updated_ids_on_page)} строк в памяти (редактирование).")
            self.set_dirty_flag(True)
            self.apply_current_filters(reset_page=False) # Обновит filtered_display_ids и дисплей
            untranslated_count = sum(1 for status in self.unit_status_map.values() if status == 'untranslated')
            self.update_status(f"Изменения стр. {self.current_page_index+1} сохранены в памяти. Всего: {len(self.all_trans_units)} | Неперев.: {untranslated_count}")

        else:
            print("Изменений на странице не обнаружено (редактирование).")
        return True # Успех (или нет изменений)

    # --- Функция отображения статистики ---
    def show_statistics_window(self):
        """Отображает окно со статистикой перевода."""
        if not self.xliff_tree:
            messagebox.showinfo("Нет данных", "Сначала загрузите XLIFF файл.", parent=self.root)
            return

        total_units = len(self.all_trans_units)
        counts = {'untranslated': 0, 'translated': 0, 'approved': 0}
        for status in self.unit_status_map.values():
            counts[status] = counts.get(status, 0) + 1 # Считаем по актуальной карте

        untranslated_count = counts['untranslated']
        translated_count = counts['translated']
        approved_count = counts['approved']
        # Считаем общий прогресс как (переведенные + подтвержденные) / всего
        overall_translated = translated_count + approved_count
        progress_value = (overall_translated / total_units) if total_units > 0 else 0

        stats_win = ctk.CTkToplevel(self.root)
        stats_win.title("Статистика")
        stats_win.geometry("420x320") # Немного больше для доп. статуса
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
        # Файл
        ctk.CTkLabel(info_frame, text="Файл:", anchor="w").grid(row=row, column=0, sticky='w', pady=3)
        file_label = ctk.CTkLabel(info_frame, text=os.path.basename(self.xliff_filepath), anchor="e", wraplength=270)
        file_label.grid(row=row, column=1, sticky='e', pady=3, padx=(10,0)); row += 1
        # Языки
        ctk.CTkLabel(info_frame, text="Языки:", anchor="w").grid(row=row, column=0, sticky='w', pady=3)
        ctk.CTkLabel(info_frame, text=f"{self.detected_source_lang} → {self.detected_target_lang}", anchor="e").grid(row=row, column=1, sticky='e', pady=3, padx=(10,0)); row += 1
        # Статистика
        ctk.CTkLabel(info_frame, text="Всего строк (trans-unit):", anchor="w").grid(row=row, column=0, sticky='w', pady=3)
        ctk.CTkLabel(info_frame, text=f"{total_units}", anchor="e").grid(row=row, column=1, sticky='e', pady=3, padx=(10,0)); row += 1
        ctk.CTkLabel(info_frame, text="Не переведено:", anchor="w").grid(row=row, column=0, sticky='w', pady=3)
        ctk.CTkLabel(info_frame, text=f"{untranslated_count}", anchor="e").grid(row=row, column=1, sticky='e', pady=3, padx=(10,0)); row += 1
        ctk.CTkLabel(info_frame, text="Переведено:", anchor="w").grid(row=row, column=0, sticky='w', pady=3)
        ctk.CTkLabel(info_frame, text=f"{translated_count}", anchor="e").grid(row=row, column=1, sticky='e', pady=3, padx=(10,0)); row += 1
        #ctk.CTkLabel(info_frame, text="Подтверждено ('approved'):", anchor="w").grid(row=row, column=0, sticky='w', pady=3)
        #ctk.CTkLabel(info_frame, text=f"{approved_count}", anchor="e").grid(row=row, column=1, sticky='e', pady=3, padx=(10,0)); row += 1
        ctk.CTkLabel(info_frame, text="Общий прогресс:", anchor="w").grid(row=row, column=0, sticky='w', pady=3)
        ctk.CTkLabel(info_frame, text=f"{progress_value*100:.2f}%", anchor="e").grid(row=row, column=1, sticky='e', pady=3, padx=(10,0)); row += 1

        stats_progress_bar = ctk.CTkProgressBar(stats_win, orientation="horizontal", height=15)
        stats_progress_bar.pack(pady=(15, 10), padx=15, fill='x')
        stats_progress_bar.set(progress_value)

        stats_win.focus_set()
        stats_win.bind("<Escape>", lambda e: stats_win.destroy())

        # Центрирование окна
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

        # Удаляем предыдущую подсветку
        try: target_widget.tag_remove("search_highlight", "1.0", tk.END)
        except tk.TclError: pass

        try:
            # Ищем от последней позиции + 1 символ, чтобы не найти то же самое
            start_pos = target_widget.index(f"{self.last_search_pos}+1c")
            match_pos = target_widget.search(search_term, start_pos, stopindex=tk.END, nocase=True) # nocase=True для регистронезависимого поиска

            if match_pos:
                end_pos = f"{match_pos}+{len(search_term)}c"
                print(f"Найдено '{search_term}' на позиции {match_pos}")
                # Настраиваем тег подсветки (если еще не настроен)
                try: target_widget.tag_config("search_highlight", background="yellow", foreground="black")
                except tk.TclError: pass # Ignore if already configured
                # Применяем тег
                target_widget.tag_add("search_highlight", match_pos, end_pos)
                target_widget.see(match_pos) # Прокручиваем к найденному
                self.last_search_pos = match_pos # Обновляем последнюю позицию
                self.update_status(f"Найдено: '{search_term}'")
                self.set_focus_on_editor() # Возвращаем фокус в редактор
                target_widget.tag_raise(tk.SEL) # Поднимаем выделение над подсветкой, если оно есть
            else:
                # Если не нашли от текущей позиции, пробуем с начала
                self.last_search_pos = "1.0" # Сбрасываем позицию
                match_pos = target_widget.search(search_term, self.last_search_pos, stopindex=tk.END, nocase=True)
                if match_pos:
                    end_pos = f"{match_pos}+{len(search_term)}c"
                    print(f"Найдено '{search_term}' с начала на позиции {match_pos}")
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
                    self.last_search_pos = "1.0" # Сбрасываем для следующего поиска

        except tk.TclError as e:
            print(f"Ошибка поиска Tcl: {e}")
            self.update_status("Ошибка во время поиска.")
        except Exception as e:
             print(f"Ошибка поиска: {e}")
             traceback.print_exc()
             self.update_status("Ошибка поиска.")


    def on_search_entry_change(self, *args):
        """Активирует/деактивирует кнопку поиска при изменении текста в поле."""
        search_term = self.search_entry.get() if self.search_entry else ""
        state = tk.NORMAL if search_term and self.xliff_tree else tk.DISABLED
        if self.find_next_button:
             self.find_next_button.configure(state=state)
        # Сбрасываем позицию при изменении текста поиска
        self.last_search_pos = "1.0"
        target_widget = self._get_inner_text_widget()
        if target_widget:
             try: target_widget.tag_remove("search_highlight", "1.0", tk.END)
             except tk.TclError: pass

    # --- Создание виджетов ---
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
        self.edit_mode_button.pack(side=tk.LEFT, padx=(0, 15)) # Increased spacing

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
            self.on_translator_selected(DEFAULT_TRANSLATOR_SERVICE) # Set initial value
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

        # Stats Button
        self.stats_button = ctk.CTkButton(left_controls, text="Статистика", command=self.show_statistics_window, width=90)
        self.stats_button.pack(side=tk.LEFT, padx=(0, 5))


        # --- Right Control Frame (Filters, Open) ---
        right_controls = ctk.CTkFrame(top_frame, fg_color="transparent")
        right_controls.grid(row=0, column=2, padx=(5, 0), sticky="e")

        # File Filter
        ctk.CTkLabel(right_controls, text="Файл:").pack(side=tk.LEFT, padx=(0, 3))
        self.file_filter_combobox = ctk.CTkComboBox(
            right_controls, values=[ALL_FILES_FILTER], command=self.on_file_filter_change,
            width=160, state=tk.DISABLED)
        self.file_filter_combobox.pack(side=tk.LEFT, padx=(0, 10))
        self.file_filter_combobox.set(ALL_FILES_FILTER)

        # Status Filter
        ctk.CTkLabel(right_controls, text="Статус:").pack(side=tk.LEFT, padx=(0, 3))
        status_filter_options = ["Непереведенные", "Переведенные", "Подтвержденные", "Все статусы"]
        status_map_internal_to_display = {"untranslated": "Непереведенные", "translated": "Переведенные", "approved": "Подтвержденные", "all": "Все статусы"}
        self.status_filter_combobox = ctk.CTkComboBox(
            right_controls, values=status_filter_options, command=self.on_status_filter_change,
            width=130, state=tk.DISABLED)
        self.status_filter_combobox.pack(side=tk.LEFT, padx=(0, 15))
        self.status_filter_combobox.set(status_map_internal_to_display.get(DEFAULT_STATUS_FILTER)) # Set initial display value

        # Open Button
        self.open_button = ctk.CTkButton(right_controls, text="Открыть XLIFF...", command=self.load_xliff, width=120)
        self.open_button.pack(side=tk.LEFT)

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
        nav_content_frame.pack(anchor=tk.CENTER) # Center navigation controls

        _nav_font = ctk.CTkFont(size=11)
        self.prev_button = ctk.CTkButton(nav_content_frame, text="<< Пред.", command=self.go_to_prev_page, width=70, font=_nav_font)
        self.prev_button.pack(side=tk.LEFT, padx=(0, 2))
        self.page_label = ctk.CTkLabel(nav_content_frame, text="Страница: - / -", width=180, font=_nav_font, anchor=tk.CENTER) # Wider label
        self.page_label.pack(side=tk.LEFT, padx=2)
        self.page_entry = ctk.CTkEntry(nav_content_frame, textvariable=self.page_var, width=45, justify=tk.CENTER, font=_nav_font)
        self.page_entry.pack(side=tk.LEFT, padx=1)
        self.page_entry.bind("<Return>", self.go_to_page)
        self.go_button = ctk.CTkButton(nav_content_frame, text="Перейти", command=self.go_to_page, width=60, font=_nav_font)
        self.go_button.pack(side=tk.LEFT, padx=2)
        self.next_button = ctk.CTkButton(nav_content_frame, text="След. >>", command=self.go_to_next_page, width=70, font=_nav_font)
        self.next_button.pack(side=tk.LEFT, padx=(2, 15))
        page_size_label = ctk.CTkLabel(nav_content_frame, text="Строк:", font=_nav_font)
        page_size_label.pack(side=tk.LEFT, padx=(5, 1))
        self.page_size_entry = ctk.CTkEntry(nav_content_frame, textvariable=self.page_size_var, width=45, justify=tk.CENTER, font=_nav_font)
        self.page_size_entry.pack(side=tk.LEFT, padx=(1, 2))
        self.page_size_entry.bind("<Return>", self.update_page_size)
        self.page_size_button = ctk.CTkButton(nav_content_frame, text="Прим.", command=self.update_page_size, width=50, font=_nav_font)
        self.page_size_button.pack(side=tk.LEFT, padx=2)


        # --- Text Editor ---
        editor_frame = ctk.CTkFrame(self.root, fg_color="transparent")
        editor_frame.pack(expand=True, fill=tk.BOTH, padx=10, pady=(0, 5))

        try: editor_font = ctk.CTkFont(family="Consolas", size=self.current_font_size)
        except: editor_font = ctk.CTkFont(family="Courier New", size=self.current_font_size) # Fallback

        self.editor_textbox = ctk.CTkTextbox(
            editor_frame, wrap=tk.NONE, undo=True, font=editor_font,
            border_width=1, padx=5, pady=5 )

        editor_scrollbar_y = ctk.CTkScrollbar(editor_frame, command=self.editor_textbox.yview)
        editor_scrollbar_y.pack(side=tk.RIGHT, fill=tk.Y)
        editor_scrollbar_x = ctk.CTkScrollbar(editor_frame, command=self.editor_textbox.xview, orientation="horizontal")
        editor_scrollbar_x.pack(side=tk.BOTTOM, fill=tk.X) # Add horizontal scrollbar

        self.editor_textbox.configure(yscrollcommand=editor_scrollbar_y.set, xscrollcommand=editor_scrollbar_x.set)
        self.editor_textbox.pack(expand=True, fill=tk.BOTH, side=tk.LEFT)

        # --- Внутренний виджет и биндинги ---
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
                can_paste = self.can_paste_now() # Use the refined check

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

            # Global key bindings (use bind_all on the root window)
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
            self.root.bind_all("<Control-f>", lambda e: self.search_entry.focus_set()); self.root.bind_all("<Control-F>", lambda e: self.search_entry.focus_set())
            self.root.bind_all("<Command-f>", lambda e: self.search_entry.focus_set()); self.root.bind_all("<Command-F>", lambda e: self.search_entry.focus_set()) # macOS
            self.root.bind_all("<F3>", self.find_next) # F3 for Find Next

            text_widget.bind("<<Modified>>", self.handle_text_modification)
        else:
            print(f"{Fore.RED}Критическая ошибка: Не удалось получить внутренний tk.Text! Функционал будет ограничен.{Style.RESET_ALL}")

    # --- Управление режимами ---
    def set_mode(self, mode, force_update=False):
        """Переключает режим редактора ('markup' или 'edit')."""
        # Определяем цвета для активной/неактивной кнопки
        # Делаем это здесь, т.к. тема может быть не готова при инициализации
        active_color = inactive_color = None
        try:
            active_color = ctk.ThemeManager.theme["CTkButton"]["fg_color"]
            inactive_color = ctk.ThemeManager.theme["CTkButton"]["hover_color"]
        except Exception as e:
             print(f"{Fore.YELLOW}Warning: Could not get theme colors for button state: {e}{Style.RESET_ALL}")
             # Fallback colors might be needed here if the above fails consistently

        if not self.xliff_tree and not force_update:
            # Просто обновляем вид кнопок, если файл не загружен
            if mode == 'markup':
                if self.markup_mode_button and active_color: self.markup_mode_button.configure(fg_color=active_color)
                if self.edit_mode_button and inactive_color: self.edit_mode_button.configure(fg_color=inactive_color)
            elif mode == 'edit':
                if self.markup_mode_button and inactive_color: self.markup_mode_button.configure(fg_color=inactive_color)
                if self.edit_mode_button and active_color: self.edit_mode_button.configure(fg_color=active_color)
            self.current_mode = mode # Устанавливаем режим, даже если нет файла
            return

        if not force_update and mode == self.current_mode: return # Режим не изменился

        if not force_update and self.xliff_tree:
            # Сначала сохраняем текущую страницу
            if not self.save_current_page_data_if_dirty(prompt_save=True):
                print("Смена режима отменена пользователем или из-за ошибки сохранения.")
                return

        print(f"Установка режима: {mode}")
        previous_mode = self.current_mode
        self.current_mode = mode

        general_state = tk.NORMAL if self.xliff_tree else tk.DISABLED

        if self.editor_textbox:
            if mode == 'markup':
                if self.markup_mode_button: self.markup_mode_button.configure(state=tk.DISABLED, fg_color=active_color)
                if self.edit_mode_button: self.edit_mode_button.configure(state=general_state, fg_color=inactive_color)
                self.editor_textbox.configure(wrap=tk.NONE) # XML без переноса
                self.update_status(f"Режим: Разметка XML ({self._get_current_filter_description()})")
            elif mode == 'edit':
                if self.markup_mode_button: self.markup_mode_button.configure(state=general_state, fg_color=inactive_color)
                if self.edit_mode_button: self.edit_mode_button.configure(state=tk.DISABLED, fg_color=active_color)
                self.editor_textbox.configure(wrap=tk.WORD) # Текст с переносом
                self.update_status(f"Режим: Редактирование текста ({self._get_current_filter_description()})")
            else: # Неизвестный режим
                print(f"{Fore.RED}Ошибка: Неизвестный режим '{mode}'. Возврат к '{previous_mode}'.{Style.RESET_ALL}")
                self.current_mode = previous_mode
                # Рекурсивный вызов для восстановления состояния кнопок
                self.set_mode(previous_mode, force_update=True)
                return

            # Обновляем отображение, если файл загружен и режим действительно изменился
            if self.xliff_tree and (mode != previous_mode or force_update):
                self._display_current_page()
                inner_widget = self._get_inner_text_widget()
                if inner_widget:
                    try: inner_widget.edit_modified(False) # Сбрасываем флаг после смены режима/отображения
                    except tk.TclError: pass

            self.set_focus_on_editor()
        else: # Если виджет редактора еще не создан (ранний вызов)
             if mode == 'markup':
                 if self.markup_mode_button: self.markup_mode_button.configure(state=tk.DISABLED, fg_color=active_color)
                 if self.edit_mode_button: self.edit_mode_button.configure(state=tk.NORMAL, fg_color=inactive_color)
             elif mode == 'edit':
                 if self.markup_mode_button: self.markup_mode_button.configure(state=tk.NORMAL, fg_color=inactive_color)
                 if self.edit_mode_button: self.edit_mode_button.configure(state=tk.DISABLED, fg_color=active_color)

    def handle_text_modification(self, event=None):
        """Обработчик события <<Modified>> от внутреннего tk.Text."""
        inner_widget = self._get_inner_text_widget()
        if inner_widget:
            try:
                if inner_widget.edit_modified():
                    # Устанавливаем is_dirty только если флаг еще не установлен
                    # Это предотвращает лишние вызовы update_title и configure
                    if not self.is_dirty:
                       self.set_dirty_flag(True)
                    # Включаем кнопку сохранения, если она выключена (она может быть уже включена)
                    if self.save_button and self.save_button.cget('state') == tk.DISABLED:
                        self.save_button.configure(state=tk.NORMAL)

            except tk.TclError: pass # Игнорируем ошибки, если виджет уничтожается

    def on_translator_selected(self, choice):
        """Обновляет выбранный сервис перевода."""
        print(f"Выбран сервис перевода: {choice}")
        self.selected_translator_service = choice

    def on_closing(self):
        """Обработчик события закрытия окна."""
        # Пытаемся сохранить текущую страницу без запроса
        page_save_ok = self.save_current_page_data_if_dirty(prompt_save=False)
        if not page_save_ok:
            if not messagebox.askokcancel("Ошибка сохранения страницы",
                                          "Не удалось сохранить изменения на текущей странице из-за ошибки.\n"
                                          "Все равно выйти (изменения страницы будут потеряны)?",
                                          icon='warning', parent=self.root):
                return # Отмена выхода

        if self.is_dirty:
            result = messagebox.askyesnocancel("Выход",
                                               "Есть несохраненные изменения.\n"
                                               "Сохранить их в файл перед выходом?",
                                               icon='warning', parent=self.root)
            if result is True: # Да, сохранить
                self.save_xliff()
                # Проверяем, сохранилось ли (is_dirty должен стать False)
                if self.is_dirty:
                    if messagebox.askokcancel("Ошибка сохранения файла",
                                              "Не удалось сохранить изменения в файл.\n"
                                              "Все равно выйти (все изменения будут потеряны)?",
                                              icon='error', parent=self.root):
                        self.root.destroy()
                    else: return # Отмена выхода
                else:
                    self.root.destroy() # Успешно сохранено, выходим
            elif result is False: # Нет, не сохранять
                if messagebox.askyesno("Подтверждение",
                                       "Вы уверены, что хотите выйти без сохранения изменений?",
                                       icon='warning', parent=self.root):
                    self.root.destroy()
                else: return # Отмена выхода
            else: # Отмена
                return
        else: # Нет несохраненных изменений
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
        # Быстрая проверка доступности Tk и CTk
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
             sys.exit(f"Критическая ошибка Tcl/Tk: {e}") # Exit if critical non-display error

    if display_available:
        root = None
        try:
            root = ctk.CTk()
            app = XliffEditorApp(root)
            if filepath_from_cli:
                # Загружаем файл после инициализации главного цикла
                root.after(100, lambda: app.load_xliff(filepath_arg=filepath_from_cli))
            root.mainloop()
        except tk.TclError as e:
             print(f"{Fore.RED}Критическая ошибка Tcl/Tk во время выполнения:{Style.RESET_ALL}")
             traceback.print_exc()
             messagebox.showerror("Критическая ошибка Tcl/Tk", f"Ошибка Tcl/Tk:\n{e}\nПриложение будет закрыто.", parent=root) # Show error if possible
             sys.exit(1)
        except Exception as e:
             print(f"{Fore.RED}Критическая ошибка Python во время выполнения:{Style.RESET_ALL}")
             traceback.print_exc()
             messagebox.showerror("Критическая ошибка Python", f"Ошибка Python:\n{type(e).__name__}: {e}\nПриложение будет закрыто.", parent=root) # Show error if possible
             sys.exit(1)
    else:
         print("Запуск GUI отменен из-за отсутствия или ошибки дисплея.")
         # Попытка показать системное сообщение об ошибке, если Tk частично доступен
         try:
             root_err = tk.Tk(); root_err.withdraw()
             messagebox.showerror("Ошибка запуска", "Не удалось инициализировать графический интерфейс.\nУбедитесь, что дисплей доступен.")
             root_err.destroy()
         except Exception: pass # Ignore if even this fails
         sys.exit(1)

if __name__ == "__main__":
    main()

# --- END OF FILE xliff_editor_gui_v2.py ---