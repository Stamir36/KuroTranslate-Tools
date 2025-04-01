import struct
import disasm.ED9InstructionsSet as ED9InstructionsSet
import disasm.script as script
import disasm.function as function
from lib.parser import process_data, readint, readintoffset, readtextoffset, remove2MSB, get_actual_value_str
from lib.packer import write_dword_in_byte_array # Предполагаем, что lib.packer доступен
import traceback
from lib.crc32 import compute_crc32 # Предполагаем, что lib.crc32 доступен
import math # Добавлен импорт math для FLOAT

current_stack = []
dict_stacks = {}#Key: Label, Value: State of the stack at the jump
variable_names = {}#Key: Stack Index (относительно начала функции), Value: Symbol (PARAM_X или VAR_Y)

stack_invalid = False #Whenever there is a EXIT, we at least need a Label right after
current_addr_scripts_var = 0
current_addr_structs = 0
current_addr_code = 0

# --- Используем глобальные переменные для текущего состояния ---
# Это не идеальный подход, но соответствует оригинальной структуре
# Лучше было бы передавать их как аргументы или использовать класс ассемблера
current_script = None
current_function = None
# --------------------------------------------------------------

# Счетчик функций, чтобы присваивать ID, если их нет
function_id_counter = 0

functions_sorted_by_id = []
# Массивы для отложенной записи адресов строк
strings_offsets_code          = []
strings_offsets_struct_params = []
strings_offsets_script_var    = []
strings_offsets_fun_varout    = []
strings_offsets_fun_varin     = []
strings_offsets_fun_names     = []

# Словарь для меток JUMP
jump_dict = {} # Key: String ("Loc_XXX") Value: jump_target object
label_addresses = {} # Key: String ("Loc_XXX") Value: address in bin_code_section

# Список для адресов возврата из CALL
return_addr_vector = [] # Список объектов jump_target

bin_code_section = bytearray([])

# Адреса секций (будут вычислены в compile)
start_functions_headers_section =  0x18
start_script_variables          = -1
start_functions_var_in          = -1
start_functions_var_out         = -1
start_structs_section           = -1
start_structs_params_section    = -1
start_code_section              = -1
start_strings_section           = -1

# --- Класс для хранения информации о переходах ---
class jump_target: # Переименован из jump для ясности
    def __init__(self):
        self.addr_references = [] # Адреса в bin_code_section, где нужно записать указатель
        self.addr_destination = -1 # Адрес назначения в bin_code_section

# --- Получение индекса функции по имени ---
def retrieve_index_by_fun_name(name):
    global current_script
    if not current_script or not current_script.functions:
        return -1 # Возвращаем -1, если скрипт или список функций не инициализирован
    for f in current_script.functions:
        if f.name == name:
            return f.id
    print(f"ПРЕДУПРЕЖДЕНИЕ: Функция с именем '{name}' не найдена!")
    return -1 # Функция не найдена

# --- Функции кодирования типов данных ---
def UNDEF(value: int)->int:
    # Проверяем, не пришло ли уже закодированное значение
    if (value & 0xC0000000) != 0: return value
    return value & 0x3FFFFFFF

def INT(value: int)->int:
    # Убираем ошибочную проверку "уже закодировано" для отрицательных чисел
    # if isinstance(value, int) and (value & 0xC0000000) != 0: return value # УДАЛЕНО

    if not isinstance(value, int):
        print(f"ПРЕДУПРЕЖДЕНИЕ: INT() получил не целое число: {value}. Попытка преобразования.")
        try: value = int(value)
        except (ValueError, TypeError):
             print(f"ОШИБКА: Не удалось преобразовать {value} в int для INT(). Возвращаю 0.")
             value = 0

    # --- Ключевое изменение: обработка отрицательных чисел ---
    if value < 0:
        original_value = value
        value = value & 0xFFFFFFFF
        print(f"[DEBUG INT] Negative input, after & 0xFFFFFFFF: {value} (original: {original_value})") # DEBUG

    masked_value = value & 0x3FFFFFFF
    print(f"[DEBUG INT] After & 0x3FFFFFFF mask: {masked_value}") # DEBUG
    final_value = masked_value | 0x40000000
    print(f"[DEBUG INT] Final value after | 0x40000000: {final_value}") # DEBUG
    return final_value

def FLOAT(value: float)->int:
    # Проверяем, не пришло ли уже закодированное значение (маловероятно для float)
    # if isinstance(value, int) and (value & 0xC0000000) != 0: return value
    try:
         # Используем <f для little-endian float
         float_bytes = struct.pack("<f", value)
         float_uint = struct.unpack("<I", float_bytes)[0]
         # Сдвиг для ED9 не требуется, как в Ys IX/X ?
         # Если нужен сдвиг: float_uint = float_uint >> 2
         return (float_uint & 0x3FFFFFFF) | 0x80000000
    except (TypeError, struct.error) as e:
         print(f"ОШИБКА: Не удалось упаковать FLOAT значение '{value}': {e}")
         return 0x80000000 # Возвращаем базовый float(0) с тегом?

def STR(value: int)->int:
    if (value & 0xC0000000) != 0: return value
    return (value & 0x3FFFFFFF) | 0xC0000000

# --- Поиск символа (переменной/параметра) ---
def find_symbol_in_stack(symbol):
    global variable_names
    # Ищем по значению (имени) и возвращаем ключ (индекс)
    try:
        # Возвращаем первый найденный ключ
        return list(variable_names.keys())[list(variable_names.values()).index(symbol)]
    except ValueError:
        raise ValueError(f"Символ '{symbol}' не найден в текущем словаре переменных: {variable_names}")

# --- Добавление структуры ---
def add_struct(id, nb_sth1, array2):
    global current_function
    if current_function is None:
         print("ОШИБКА: Попытка добавить структуру до установки текущей функции (set_current_function).")
         return
    mysterious_struct = {
        "id": id,
        "nb_sth1": nb_sth1,
        "array2": array2,
        }
    current_function.structs.append(mysterious_struct)

# --- Добавление функции ---
def add_function(name, input_args, output_args, b0, b1):
    global current_script, current_function, function_id_counter, functions_sorted_by_id
    if current_script is None:
        print("ОШИБКА: Попытка добавить функцию до создания заголовка скрипта (create_script_header).")
        # Инициализируем current_script, если он еще не создан
        current_script = script.script()
        print("ПРЕДУПРЕЖДЕНИЕ: Объект скрипта не был инициализирован, создаю пустой.")

    # Создаем новый объект функции
    new_func = function.function()

    new_func.id = function_id_counter # Присваиваем текущий ID
    function_id_counter += 1 # Увеличиваем счетчик для следующей функции

    new_func.name = name
    new_func.hash = compute_crc32(name)
    new_func.input_args = input_args if input_args is not None else []
    new_func.output_args = output_args if output_args is not None else []
    new_func.b0 = b0
    new_func.b1 = b1
    new_func.start = -1 # Адрес будет установлен позже
    new_func.instructions = [] # Инструкции будут добавлены позже
    new_func.structs = [] # Структуры добавляются через add_struct

    current_script.functions.append(new_func)
    # Добавляем в список для сортировки
    functions_sorted_by_id.append(new_func)
    # Обновляем current_function (не обязательно, но может быть полезно)
    current_function = new_func


# --- Установка текущей функции для добавления кода ---
def set_current_function(name):
    global current_function, current_function_number # current_function_number не используется, можно убрать
    global current_stack, variable_names, stack_invalid
    global bin_code_section, current_addr_code # Сбрасываем адрес кода для новой функции

    func_id = retrieve_index_by_fun_name(name)
    if func_id == -1:
        print(f"ОШИБКА: Не удается установить текущую функцию '{name}', она не была добавлена через add_function.")
        current_function = None # Сбрасываем текущую функцию
        return

    current_function = functions_sorted_by_id[func_id]
    if current_function.start != -1:
        print(f"ПРЕДУПРЕЖДЕНИЕ: Повторный вызов set_current_function для '{name}'. Перезапись адреса начала кода.")

    # Сбрасываем адрес кода относительно начала секции кода
    current_addr_code = len(bin_code_section)
    current_function.start = current_addr_code # Запоминаем адрес начала кода этой функции

    print(f"--- Установлена текущая функция: {name} (ID: {func_id}), Адрес начала кода: {hex(current_addr_code)} ---")

    # Сбрасываем состояние для декомпилированных инструкций
    stack_invalid = False
    variable_names.clear()
    current_stack.clear()

    # Заполняем начальное состояние для декомпилированных инструкций (если они используются)
    # Это нужно для AssignVar, LoadVar и т.д.
    for i in range(len(current_function.input_args)):
        # В стек кладем индекс параметра (0, 1, ...)
        current_stack.append(i)
        # В variables_names ключ - индекс параметра, значение - имя PARAM_X
        variable_names[i] = "PARAM_" + str(i)


# --- Компиляция ---
def compile():
    global current_script, bin_code_section
    global start_script_variables, start_functions_var_in, start_functions_var_out
    global start_structs_section, start_structs_params_section
    global start_code_section, start_strings_section
    global strings_offsets_code, strings_offsets_struct_params, strings_offsets_script_var
    global strings_offsets_fun_varout, strings_offsets_fun_varin, strings_offsets_fun_names
    global jump_dict, label_addresses, return_addr_vector

    if not current_script:
         print("ОШИБКА: Скрипт не инициализирован (вызовите create_script_header). Компиляция невозможна.")
         return

    print("\n--- Начало компиляции ---")

    bin_function_header_section = bytearray([])
    bin_script_header_section   = bytearray([])
    bin_fun_input_vars_section  = bytearray([])
    bin_fun_output_vars_section = bytearray([])
    bin_structs_section         = bytearray([])
    bin_structs_params_section  = bytearray([])
    bin_script_var_section      = bytearray([])
    bin_string_section          = bytearray([])

    # Вычисляем размеры и адреса секций
    print("Вычисление адресов секций...")
    start_functions_var_out = start_functions_headers_section + 0x20 * len(current_script.functions)

    total_in = sum(len(f.input_args) for f in current_script.functions)
    total_out = sum(len(f.output_args) for f in current_script.functions)
    total_structs = sum(len(f.structs) for f in current_script.functions)
    size_total_params_structs = sum(len(s["array2"]) * 4 for f in current_script.functions for s in f.structs)

    start_functions_var_in = start_functions_var_out + total_out * 4
    start_structs_section = start_functions_var_in + total_in * 4
    start_structs_params_section = start_structs_section + 0xC * total_structs # 0xC байт на заголовок структуры
    start_script_variables = start_structs_params_section + size_total_params_structs
    start_code_section = start_script_variables + (len(current_script.script_variables_in) + len(current_script.script_variables_out)) * 8 # 8 байт на переменную
    start_strings_section = start_code_section + len(bin_code_section)

    print(f"Адрес заголовков функций: {hex(start_functions_headers_section)}")
    print(f"Адрес выходных переменных функций: {hex(start_functions_var_out)}")
    print(f"Адрес входных переменных функций: {hex(start_functions_var_in)}")
    print(f"Адрес заголовков структур: {hex(start_structs_section)}")
    print(f"Адрес параметров структур: {hex(start_structs_params_section)}")
    print(f"Адрес переменных скрипта: {hex(start_script_variables)}")
    print(f"Адрес начала кода: {hex(start_code_section)}")
    print(f"Адрес начала строк: {hex(start_strings_section)}")

    # Собираем заголовок скрипта
    print("Сборка заголовка скрипта...")
    fourCC = b"#scp"
    header_b = bytearray(fourCC)
    header_b += struct.pack("<I", start_functions_headers_section)
    header_b += struct.pack("<I", len(current_script.functions))
    header_b += struct.pack("<I", start_script_variables if current_script.script_variables_in or current_script.script_variables_out else 0) # Указатель 0, если переменных нет
    header_b += struct.pack("<I", len(current_script.script_variables_in))
    header_b += struct.pack("<I", len(current_script.script_variables_out))

    # Собираем секции данных (переменные скрипта, функции, структуры)
    print("Сборка секций данных...")
    current_addr_fun_var_in = start_functions_var_in
    current_addr_fun_var_out = start_functions_var_out
    current_addr_structs = start_structs_section
    current_addr_structs_params = start_structs_params_section
    current_addr_script_vars = start_script_variables

    # Переменные скрипта
    for i, vin_scp in enumerate(current_script.script_variables_in):
        if len(vin_scp) != 2: print(f"ПРЕДУПРЕЖДЕНИЕ: Неверный формат script_variables_in[{i}]")
        for j, v in enumerate(vin_scp):
            addr_to_write = start_script_variables + i * 8 + j * 4
            if isinstance(v, str):
                bin_script_var_section += struct.pack("<I", 0) # Placeholder
                strings_offsets_script_var.append((addr_to_write, v))
            else:
                bin_script_var_section += struct.pack("<I", v)
    for i, vout_scp in enumerate(current_script.script_variables_out):
         if len(vout_scp) != 2: print(f"ПРЕДУПРЕЖДЕНИЕ: Неверный формат script_variables_out[{i}]")
         for j, v in enumerate(vout_scp):
            addr_to_write = start_script_variables + len(current_script.script_variables_in) * 8 + i * 8 + j * 4
            if isinstance(v, str):
                bin_script_var_section += struct.pack("<I", 0) # Placeholder
                strings_offsets_script_var.append((addr_to_write, v))
            else:
                 bin_script_var_section += struct.pack("<I", v)

    # Заголовки и данные функций/структур
    functions_sorted_by_id.sort(key=lambda f: f.id) # Убедимся, что порядок по ID
    current_header_offset = 0
    for f in functions_sorted_by_id:
        header_f = bytearray()
        # Проверяем, был ли установлен адрес начала кода
        if f.start == -1:
             print(f"ПРЕДУПРЕЖДЕНИЕ: Адрес начала кода для функции '{f.name}' не установлен (set_current_function не вызывался?). Устанавливаю 0.")
             start_addr = start_code_section # Или 0? Лучше адрес начала секции
        else:
             start_addr = start_code_section + f.start

        header_f += struct.pack("<I", start_addr)
        vars_val = len(f.input_args) + (f.b0 << 8) + (f.b1 << 16) + (len(f.output_args) << 24)
        header_f += struct.pack("<I", vars_val)
        header_f += struct.pack("<I", current_addr_fun_var_out if f.output_args else 0)
        header_f += struct.pack("<I", current_addr_fun_var_in if f.input_args else 0)
        header_f += struct.pack("<I", len(f.structs))
        header_f += struct.pack("<I", current_addr_structs if f.structs else 0)
        header_f += struct.pack("<I", f.hash)
        # Сохраняем адрес для записи указателя на имя функции
        strings_offsets_fun_names.append((start_functions_headers_section + current_header_offset + 0x1C, f.name))
        header_f += struct.pack("<I", 0) # Placeholder для имени функции
        bin_function_header_section += header_f
        current_header_offset += 0x20 # Размер заголовка функции

        # Входные переменные функции
        for vin in f.input_args:
            addr_to_write = current_addr_fun_var_in
            if isinstance(vin, str):
                bin_fun_input_vars_section += struct.pack("<I", 0) # Placeholder
                strings_offsets_fun_varin.append((addr_to_write, vin))
            else:
                bin_fun_input_vars_section += struct.pack("<I", vin)
            current_addr_fun_var_in += 4

        # Выходные переменные функции
        for vout in f.output_args:
             addr_to_write = current_addr_fun_var_out
             if isinstance(vout, str):
                bin_fun_output_vars_section += struct.pack("<I", 0) # Placeholder
                strings_offsets_fun_varout.append((addr_to_write, vout))
             else:
                bin_fun_output_vars_section += struct.pack("<I", vout)
             current_addr_fun_var_out += 4

        # Структуры функции
        for s in f.structs:
            bin_structs_section += struct.pack("<i", s["id"]) # id может быть отрицательным
            bin_structs_section += struct.pack("<H", s["nb_sth1"])
            # Проверяем, четное ли количество элементов в array2
            if len(s["array2"]) % 2 != 0:
                 print(f"ПРЕДУПРЕЖДЕНИЕ: Нечетное количество элементов ({len(s['array2'])}) в array2 структуры {s['id']} функции '{f.name}'.")
            # Записываем количество пар
            bin_structs_section += struct.pack("<H", len(s["array2"]) // 2)
            bin_structs_section += struct.pack("<I", current_addr_structs_params if s["array2"] else 0)
            current_addr_structs += 0xC
            # Параметры структуры
            for el in s["array2"]:
                addr_to_write = current_addr_structs_params
                if isinstance(el, str):
                    bin_structs_params_section += struct.pack("<I", 0) # Placeholder
                    strings_offsets_struct_params.append((addr_to_write, el))
                else:
                    bin_structs_params_section += struct.pack("<I", el)
                current_addr_structs_params += 4

    # Заполняем адреса переходов
    print("Заполнение адресов переходов...")
    # Сначала вычисляем все адреса меток
    for label, jump_data in jump_dict.items():
         if label not in label_addresses:
              print(f"ОШИБКА: Метка '{label}' используется в JUMP/JUMPIF, но не определена через Label().")
              # Можно установить адрес назначения в 0 или конец кода, чтобы избежать падения
              label_addresses[label] = len(bin_code_section) # Указываем на конец кода
         jump_data.addr_destination = label_addresses[label] # Сохраняем реальный адрес

    # Записываем адреса в код
    for label, jump_data in jump_dict.items():
        dest_addr_in_file = start_code_section + jump_data.addr_destination
        for ref_addr in jump_data.addr_references:
            try:
                write_dword_in_byte_array("<I", bin_code_section, ref_addr, dest_addr_in_file)
            except IndexError:
                 print(f"ОШИБКА: Неверный адрес ссылки ({hex(ref_addr)}) для метки '{label}'.")

    # Записываем адреса возврата
    for ret_data in return_addr_vector:
         dest_addr_in_file = start_code_section + ret_data.addr_destination
         for ref_addr in ret_data.addr_references:
              try:
                  # Адрес возврата не кодируется как STR/INT и т.д.
                  write_dword_in_byte_array("<I", bin_code_section, ref_addr, dest_addr_in_file)
              except IndexError:
                  print(f"ОШИБКА: Неверный адрес ссылки ({hex(ref_addr)}) для адреса возврата.")


    # Собираем строки и обновляем указатели
    print("Сборка секции строк и обновление указателей...")
    current_string_offset = 0 # Смещение внутри секции строк

    # Функция для записи строки и обновления указателя
    def write_string_and_update_pointers(string_list, base_section, encoding="utf-8"):
        nonlocal current_string_offset, bin_string_section, bin_file # Указываем, что меняем внешние переменные
        for addr_in_header, text in string_list:
            # Кодируем строку и добавляем нулевой байт
            try:
                output_bytes = text.encode(encoding) + b"\0"
            except UnicodeEncodeError:
                 print(f"ПРЕДУПРЕЖДЕНИЕ: Не удалось закодировать строку '{text}' в {encoding}. Использую 'replace'.")
                 output_bytes = text.encode(encoding, errors='replace') + b"\0"

            # Текущий адрес строки в файле
            string_addr_in_file = start_strings_section + current_string_offset
            # Добавляем байты строки в секцию строк
            bin_string_section += output_bytes
            # Записываем указатель на строку (с тегом STR) в нужное место
            # Указатель записывается либо в секцию кода, либо в другую секцию данных
            try:
                 if base_section == bin_code_section and addr_in_header < len(bin_code_section):
                     write_dword_in_byte_array("<I", bin_code_section, addr_in_header, STR(string_addr_in_file))
                 elif addr_in_header < len(bin_file): # Если указатель в уже собранной части файла
                     write_dword_in_byte_array("<I", bin_file, addr_in_header, STR(string_addr_in_file))
                 else:
                      # Это должно быть в одной из секций данных, которые будут добавлены позже
                      # Но безопаснее проверить и записать в bin_file, если адрес корректен
                      print(f"ПРЕДУПРЕЖДЕНИЕ: Не удалось определить секцию для указателя на строку по адресу {hex(addr_in_header)}.")

            except IndexError:
                  print(f"ОШИБКА: Неверный адрес ({hex(addr_in_header)}) для записи указателя на строку '{text}'.")

            # Увеличиваем смещение строки
            current_string_offset += len(output_bytes)

    # Собираем основной файл ДО секции строк
    bin_file = header_b + bin_function_header_section + bin_fun_output_vars_section + bin_fun_input_vars_section
    bin_file += bin_structs_section + bin_structs_params_section
    bin_file += bin_script_var_section + bin_code_section # Добавляем код

    # Записываем строки и обновляем указатели в соответствующих секциях
    write_string_and_update_pointers(strings_offsets_code, bin_code_section)
    write_string_and_update_pointers(strings_offsets_fun_names, bin_file) # Указатели в заголовках функций
    write_string_and_update_pointers(strings_offsets_fun_varout, bin_file) # Указатели в данных переменных
    write_string_and_update_pointers(strings_offsets_fun_varin, bin_file)
    write_string_and_update_pointers(strings_offsets_struct_params, bin_file)
    write_string_and_update_pointers(strings_offsets_script_var, bin_file)


    # Добавляем секцию строк к файлу
    bin_file += bin_string_section

    # Записываем финальный файл
    output_filename = current_script.name + ".dat"
    print(f"Запись финального файла: {output_filename}...")
    try:
        with open(output_filename, "wb") as dat_file:
            dat_file.write(bin_file)
        print(f"Файл {output_filename} успешно скомпилирован.")
    except IOError as e:
        print(f"ОШИБКА: Не удалось записать файл {output_filename}: {e}")

# --- Инициализация скрипта ---
def create_script_header(name, varin, varout):
    global current_script, function_id_counter, functions_sorted_by_id
    global bin_code_section, current_addr_code
    global strings_offsets_code, jump_dict, label_addresses, return_addr_vector
    global strings_offsets_struct_params, strings_offsets_script_var
    global strings_offsets_fun_varout, strings_offsets_fun_varin, strings_offsets_fun_names

    print(f"\nИнициализация скрипта: {name}")
    current_script = script.script() # Создаем новый объект скрипта
    current_script.name = name
    current_script.script_variables_in = varin if varin is not None else []
    current_script.script_variables_out = varout if varout is not None else []
    current_script.functions = [] # Очищаем список функций для нового скрипта

    # Сбрасываем глобальные состояния компиляции
    function_id_counter = 0
    functions_sorted_by_id = []
    bin_code_section = bytearray([])
    current_addr_code = 0
    strings_offsets_code = []
    jump_dict = {}
    label_addresses = {}
    return_addr_vector = []
    strings_offsets_struct_params = []
    strings_offsets_script_var    = []
    strings_offsets_fun_varout    = []
    strings_offsets_fun_varin     = []
    strings_offsets_fun_names     = []

# --- Инструкции ассемблера ---

# Добавляем проверку current_function во все инструкции, изменяющие bin_code_section
def check_current_function(instr_name):
     global current_function
     if current_function is None:
          print(f"ОШИБКА: Попытка добавить инструкцию '{instr_name}' до вызова set_current_function.")
          return False
     return True

def PUSHUNDEFINED(value):
    global current_addr_code, bin_code_section, current_stack
    if not check_current_function("PUSHUNDEFINED"): return
    current_stack.append(current_addr_code) # Используем адрес как ID для стека декомпилятора
    b_arg = struct.pack("<I", UNDEF(value)) # Применяем UNDEF здесь
    result = bytearray([0, 4]) + b_arg # Опкод 0, размер 4
    bin_code_section += result
    current_addr_code += len(result)

def PUSHCALLERFUNCTIONINDEX():
    global current_function
    if not check_current_function("PUSHCALLERFUNCTIONINDEX"): return
    if current_function:
        PUSHUNDEFINED(current_function.id)
    else:
         print("ОШИБКА: current_function не установлен для PUSHCALLERFUNCTIONINDEX")

def PUSHSTRING(value):
    global current_addr_code, bin_code_section, current_stack, strings_offsets_code
    if not check_current_function("PUSHSTRING"): return
    current_stack.append(current_addr_code)
    b_arg = struct.pack("<I", 0) # Placeholder для адреса строки
    result = bytearray([0, 4]) + b_arg # Опкод 0, размер 4
    bin_code_section += result
    # Запоминаем адрес в коде, где нужно будет вставить указатель на строку, и саму строку
    strings_offsets_code.append((current_addr_code + 2, value)) # +2 чтобы пропустить опкод и размер
    current_addr_code += len(result)

def PUSHRETURNADDRESS(value_label): # Принимает метку (строку)
    global current_addr_code, bin_code_section, current_stack, jump_dict, label_addresses
    if not check_current_function("PUSHRETURNADDRESS"): return

    current_stack.append(current_addr_code)
    b_arg = struct.pack("<I", 0) # Placeholder
    result = bytearray([0, 4]) + b_arg # Опкод 0, размер 4 (адрес всегда 4 байта)
    bin_code_section += result
    addr_to_patch = current_addr_code + 2 # Адрес для записи указателя

    # Используем jump_dict для отложенной записи адреса метки
    if value_label not in jump_dict:
        jump_dict[value_label] = jump_target()
    jump_dict[value_label].addr_references.append(addr_to_patch)

    current_addr_code += len(result)

def PUSHFLOAT(value):
    global current_addr_code, bin_code_section, current_stack
    if not check_current_function("PUSHFLOAT"): return
    current_stack.append(current_addr_code)
    b_arg = struct.pack("<I", FLOAT(value)) # Кодируем как FLOAT
    result = bytearray([0, 4]) + b_arg
    bin_code_section += result
    current_addr_code += len(result)

def PUSHINTEGER(value):
    global current_addr_code, bin_code_section, current_stack
    if not check_current_function("PUSHINTEGER"): return
    current_stack.append(current_addr_code)
    b_arg = struct.pack("<I", INT(value)) # Кодируем как INT
    result = bytearray([0, 4]) + b_arg
    bin_code_section += result
    current_addr_code += len(result)

def POP(value):
    global current_addr_code, bin_code_section, current_stack
    if not check_current_function("POP"): return
    popped_els = value // 4
    # Снимаем со стека (для симуляции декомпилятора)
    actual_pops = min(popped_els, len(current_stack))
    if actual_pops < popped_els:
        print(f"ПРЕДУПРЕЖДЕНИЕ: POP({value}) пытается снять {popped_els} эл., но в стеке {len(current_stack)}")
    for _ in range(actual_pops):
        current_stack.pop()

    b_arg = struct.pack("<B", value)
    result = bytearray([1]) + b_arg
    bin_code_section += result
    current_addr_code += len(result)

def RETRIEVEELEMENTATINDEX(value):
    global current_addr_code, bin_code_section, current_stack
    if not check_current_function("RETRIEVEELEMENTATINDEX"): return
    current_stack.append(current_addr_code) # Добавляем элемент на виртуальный стек
    b_arg = struct.pack("<i", value) # Значение знаковое
    result = bytearray([2]) + b_arg
    bin_code_section += result
    current_addr_code += len(result)

def RETRIEVEELEMENTATINDEX2(value):
    global current_addr_code, bin_code_section, current_stack
    if not check_current_function("RETRIEVEELEMENTATINDEX2"): return
    current_stack.append(current_addr_code)
    b_arg = struct.pack("<i", value)
    result = bytearray([3]) + b_arg
    bin_code_section += result
    current_addr_code += len(result)

def PUSHCONVERTINTEGER(value):
    global current_addr_code, bin_code_section, current_stack
    if not check_current_function("PUSHCONVERTINTEGER"): return
    current_stack.append(current_addr_code)
    b_arg = struct.pack("<i", value)
    result = bytearray([4]) + b_arg
    bin_code_section += result
    current_addr_code += len(result)

def PUTBACKATINDEX(value):
    global current_addr_code, bin_code_section, current_stack
    if not check_current_function("PUTBACKATINDEX"): return
    # Симуляция стека для декомпилированных инструкций
    if current_stack:
        val_to_put = current_stack.pop() # Снимаем значение
        target_idx_in_stack = len(current_stack) + (value // 4) # Вычисляем целевой индекс
        if 0 <= target_idx_in_stack < len(current_stack):
            current_stack[target_idx_in_stack] = val_to_put # Кладём значение по индексу
        else:
            print(f"ПРЕДУПРЕЖДЕНИЕ: PUTBACKATINDEX({value}) указывает на неверный индекс {target_idx_in_stack} (размер стека {len(current_stack)})")
            # Кладем обратно на всякий случай? Или нет? Лучше не класть.
            # current_stack.append(val_to_put) # Не добавляем обратно
    else:
        print(f"ПРЕДУПРЕЖДЕНИЕ: PUTBACKATINDEX({value}) вызван при пустом стеке.")

    b_arg = struct.pack("<i", value)
    result = bytearray([5]) + b_arg
    bin_code_section += result
    current_addr_code += len(result)

def PUTBACK(value):
    global current_addr_code, bin_code_section, current_stack
    if not check_current_function("PUTBACK"): return
     # Симуляция стека (сложнее, т.к. индекс берется со стека)
    if current_stack:
         current_stack.pop() # Снимаем значение, которое будет записано
    else:
         print(f"ПРЕДУПРЕЖДЕНИЕ: PUTBACK({value}) вызван при пустом стеке.")

    b_arg = struct.pack("<i", value)
    result = bytearray([6]) + b_arg
    bin_code_section += result
    current_addr_code += len(result)

def LOAD32(value):
    global current_addr_code, bin_code_section, current_stack
    if not check_current_function("LOAD32"): return
    current_stack.append(current_addr_code)
    b_arg = struct.pack("<i", value)
    result = bytearray([7]) + b_arg
    bin_code_section += result
    current_addr_code += len(result)

def STORE32(value):
    global current_addr_code, bin_code_section, current_stack
    if not check_current_function("STORE32"): return
    if current_stack: current_stack.pop()
    else: print(f"ПРЕДУПРЕЖДЕНИЕ: STORE32({value}) вызван при пустом стеке.")
    b_arg = struct.pack("<i", value)
    result = bytearray([8]) + b_arg
    bin_code_section += result
    current_addr_code += len(result)

def LOADRESULT(value):
    global current_addr_code, bin_code_section, current_stack
    if not check_current_function("LOADRESULT"): return
    current_stack.append(current_addr_code)
    b_arg = struct.pack("<B", value)
    result = bytearray([9]) + b_arg
    bin_code_section += result
    current_addr_code += len(result)
    # Возвращаем адрес для совместимости со старым кодом (хотя он не используется)
    # return current_addr_code - len(result) # Адрес начала инструкции

def SAVERESULT(value):
    global current_addr_code, bin_code_section, current_stack
    if not check_current_function("SAVERESULT"): return
    if current_stack: current_stack.pop()
    else: print(f"ПРЕДУПРЕЖДЕНИЕ: SAVERESULT({value}) вызван при пустом стеке.")
    b_arg = struct.pack("<B", value)
    result = bytearray([0x0A]) + b_arg
    bin_code_section += result
    current_addr_code += len(result)

def JUMP(label_name): # Принимает имя метки
    global current_addr_code, bin_code_section, jump_dict
    if not check_current_function("JUMP"): return
    b_arg = struct.pack("<I", 0) # Placeholder для адреса
    result = bytearray([0x0B]) + b_arg
    bin_code_section += result
    addr_to_patch = current_addr_code + 1 # Адрес, куда записать указатель

    if label_name not in jump_dict:
        jump_dict[label_name] = jump_target()
    jump_dict[label_name].addr_references.append(addr_to_patch)

    current_addr_code += len(result)
    # Логика dict_stacks для декомпиляции здесь не нужна

def Label(label_name): # Определяет адрес метки
    global current_addr_code, label_addresses
    if not check_current_function("Label"): return # Label вызывается внутри контекста функции
    print(f"    Определена метка: {label_name} по адресу {hex(current_addr_code)}")
    if label_name in label_addresses:
        print(f"ПРЕДУПРЕЖДЕНИЕ: Метка '{label_name}' определена повторно!")
    label_addresses[label_name] = current_addr_code
    # Логика dict_stacks для декомпиляции здесь не нужна

def CALL(function_ref): # Принимает ИМЯ или ИНДЕКС функции
    global current_addr_code, bin_code_section, current_stack
    if not check_current_function("CALL"): return

    func_index = -1
    if isinstance(function_ref, str):
        func_index = retrieve_index_by_fun_name(function_ref)
        if func_index == -1:
             print(f"ОШИБКА: CALL не может найти функцию '{function_ref}'. Записываю индекс 0.")
             func_index = 0 # Записываем 0 в случае ошибки
    elif isinstance(function_ref, int):
        func_index = function_ref # Если передан индекс напрямую (из дизассемблера)
    else:
        print(f"ОШИБКА: CALL получил неверный тип ссылки на функцию: {type(function_ref)}. Записываю индекс 0.")
        func_index = 0

    # Симуляция стека для декомпиляции
    if func_index >= 0 and func_index < len(functions_sorted_by_id):
         varin = len(functions_sorted_by_id[func_index].input_args)
         pops_needed = varin + 2
         actual_pops = min(pops_needed, len(current_stack))
         if actual_pops < pops_needed:
              print(f"ПРЕДУПРЕЖДЕНИЕ: CALL для функции {func_index} требует снять {pops_needed} эл., но в стеке {len(current_stack)}")
         for _ in range(actual_pops): current_stack.pop()
    else:
         print(f"ПРЕДУПРЕЖДЕНИЕ: Не удалось симулировать стек для CALL с индексом {func_index}")


    # Упаковываем индекс как <H (ushort)
    try:
        b_arg = struct.pack("<H", func_index)
    except struct.error as e:
        print(f"ОШИБКА struct.pack для CALL с индексом {func_index}: {e}. Записываю 0.")
        b_arg = struct.pack("<H", 0) # Записываем 0 в случае ошибки

    result = bytearray([0x0C]) + b_arg
    bin_code_section += result
    current_addr_code += len(result) # Опкод (1) + Индекс (2) = 3 байта

def EXIT():
    global current_addr_code, bin_code_section, stack_invalid, current_stack
    if not check_current_function("EXIT"): return
    stack_invalid = True # Для декомпилятора
    current_stack.clear() # Очищаем стек симуляции
    result = bytearray([0x0D])
    bin_code_section += result
    current_addr_code += len(result)

def JUMPIFFALSE(label_name): # Принимает имя метки
    global current_addr_code, bin_code_section, current_stack, jump_dict
    if not check_current_function("JUMPIFFALSE"): return
    # Снимаем условие со стека симуляции
    if current_stack: current_stack.pop()
    else: print("ПРЕДУПРЕЖДЕНИЕ: JUMPIFFALSE вызван при пустом стеке.")

    b_arg = struct.pack("<I", 0) # Placeholder
    result = bytearray([0x0F]) + b_arg
    bin_code_section += result
    addr_to_patch = current_addr_code + 1

    if label_name not in jump_dict:
        jump_dict[label_name] = jump_target()
    jump_dict[label_name].addr_references.append(addr_to_patch)

    current_addr_code += len(result)
    # Логика dict_stacks не нужна здесь

def JUMPIFTRUE(label_name): # Принимает имя метки
    global current_addr_code, bin_code_section, current_stack, jump_dict
    if not check_current_function("JUMPIFTRUE"): return
    if current_stack: current_stack.pop()
    else: print("ПРЕДУПРЕЖДЕНИЕ: JUMPIFTRUE вызван при пустом стеке.")

    b_arg = struct.pack("<I", 0) # Placeholder
    result = bytearray([0x0E]) + b_arg
    bin_code_section += result
    addr_to_patch = current_addr_code + 1

    if label_name not in jump_dict:
        jump_dict[label_name] = jump_target()
    jump_dict[label_name].addr_references.append(addr_to_patch)

    current_addr_code += len(result)
    # Логика dict_stacks не нужна здесь


# --- Бинарные и унарные операторы ---
# (ADD, SUBTRACT, ..., XOR1)
# Логика стека для них проста: pop/push нужного количества
def execute_binary_op(opcode):
     global current_addr_code, bin_code_section, current_stack
     if not check_current_function(f"Op_{hex(opcode)}"): return
     if len(current_stack) >= 2:
          current_stack.pop()
          current_stack.pop()
          current_stack.append(current_addr_code)
     else: print(f"ПРЕДУПРЕЖДЕНИЕ: Недостаточно операндов для опкода {hex(opcode)}")
     result = bytearray([opcode])
     bin_code_section += result
     current_addr_code += len(result)

def execute_unary_op(opcode):
     global current_addr_code, bin_code_section, current_stack
     if not check_current_function(f"Op_{hex(opcode)}"): return
     if current_stack:
          current_stack.pop()
          current_stack.append(current_addr_code)
     else: print(f"ПРЕДУПРЕЖДЕНИЕ: Пустой стек для опкода {hex(opcode)}")
     result = bytearray([opcode])
     bin_code_section += result
     current_addr_code += len(result)

def ADD(): execute_binary_op(0x10)
def SUBTRACT(): execute_binary_op(0x11)
def MULTIPLY(): execute_binary_op(0x12)
def DIVIDE(): execute_binary_op(0x13)
def MODULO(): execute_binary_op(0x14)
def EQUAL(): execute_binary_op(0x15)
def NONEQUAL(): execute_binary_op(0x16)
def GREATERTHAN(): execute_binary_op(0x17)
def GREATEROREQ(): execute_binary_op(0x18)
def LOWERTHAN(): execute_binary_op(0x19)
def LOWEROREQ(): execute_binary_op(0x1A)
def AND_(): execute_binary_op(0x1B)
def OR1(): execute_binary_op(0x1C)
def OR2(): execute_binary_op(0x1D)
def OR3(): execute_binary_op(0x1E)
def NEGATIVE(): execute_unary_op(0x1F)
def ISFALSE(): execute_unary_op(0x20)
def XOR1(): execute_unary_op(0x21)


def CALLFROMANOTHERSCRIPT(str1, str2, var):
    global current_addr_code, bin_code_section, current_stack, strings_offsets_code
    if not check_current_function("CALLFROMANOTHERSCRIPT"): return

    result = bytearray([0x22])
    # Placeholder для str1
    result += struct.pack("<I", 0)
    strings_offsets_code.append((current_addr_code + 1, str1))
    # Placeholder для str2
    result += struct.pack("<I", 0)
    strings_offsets_code.append((current_addr_code + 5, str2))
    # Количество аргументов var
    result += struct.pack("<B", var)
    bin_code_section += result

    # Симуляция стека
    pops_needed = var + 5 # 2 строки + 1 байт var + ??? (почему 5?) - ЛОГИКА СОМНИТЕЛЬНА
    # В оригинале было +5, оставим пока так, но это странно. Должно быть +2 строки + 1 var = 3?
    # Или 5 - это зарезервированные слоты стека?
    actual_pops = min(pops_needed, len(current_stack))
    if actual_pops < pops_needed: print(f"ПРЕДУПРЕЖДЕНИЕ: CALLFROMANOTHERSCRIPT требует снять {pops_needed} эл., но в стеке {len(current_stack)}")
    for _ in range(actual_pops): current_stack.pop()

    current_addr_code += len(result) # 1 + 4 + 4 + 1 = 10 байт

def CALLFROMANOTHERSCRIPT2(str1, str2, var):
    global current_addr_code, bin_code_section, current_stack, strings_offsets_code
    # Симуляция стека здесь не нужна, т.к. он восстанавливается (в декомпилированной версии)
    if not check_current_function("CALLFROMANOTHERSCRIPT2"): return

    result = bytearray([0x23])
    result += struct.pack("<I", 0); strings_offsets_code.append((current_addr_code + 1, str1))
    result += struct.pack("<I", 0); strings_offsets_code.append((current_addr_code + 5, str2))
    result += struct.pack("<B", var)
    bin_code_section += result
    current_addr_code += len(result)

def RUNCMD(var, command_name):
    global current_addr_code, bin_code_section
    if not check_current_function("RUNCMD"): return

    # Получаем ID и опкод по имени команды
    command_key = None
    if command_name in ED9InstructionsSet.reverse_commands_dict:
         command_key = ED9InstructionsSet.reverse_commands_dict[command_name]
    else:
         print(f"ОШИБКА: Неизвестное имя команды '{command_name}' в RUNCMD.")
         # Используем заглушку (0, 0)?
         command_key = (0, 0)

    id_struct, op_code = command_key
    result = bytearray([0x24])
    result += struct.pack("<B", id_struct)
    result += struct.pack("<B", op_code)
    result += struct.pack("<B", var) # Количество аргументов
    bin_code_section += result
    current_addr_code += len(result)

def PUSHRETURNADDRESSFROMANOTHERSCRIPT(label_name): # Принимает метку
    global current_addr_code, bin_code_section, current_stack, jump_dict
    if not check_current_function("PUSHRETURNADDRESSFROMANOTHERSCRIPT"): return

    # Симуляция стека (добавляем 5 элементов)
    base_idx = len(current_stack)
    for i in range(5): current_stack.append(base_idx + i)

    b_arg = struct.pack("<I", 0) # Placeholder
    result = bytearray([0x25]) + b_arg
    bin_code_section += result
    addr_to_patch = current_addr_code + 1

    if label_name not in jump_dict:
        jump_dict[label_name] = jump_target()
    jump_dict[label_name].addr_references.append(addr_to_patch)

    current_addr_code += len(result)

def ADDLINEMARKER(value):
    global current_addr_code, bin_code_section
    if not check_current_function("ADDLINEMARKER"): return
    b_arg = struct.pack("<H", value)
    result = bytearray([0x26]) + b_arg
    bin_code_section += result
    current_addr_code += len(result)

def POP2(value):
    global current_addr_code, bin_code_section, current_stack
    if not check_current_function("POP2"): return
    # Симуляция стека
    popped_els = value
    actual_pops = min(popped_els, len(current_stack))
    if actual_pops < popped_els: print(f"ПРЕДУПРЕЖДЕНИЕ: POP2({value}) пытается снять {popped_els} эл., но в стеке {len(current_stack)}")
    for _ in range(actual_pops): current_stack.pop()

    b_arg = struct.pack("<B", value)
    result = bytearray([0x27]) + b_arg
    bin_code_section += result
    current_addr_code += len(result)

def DEBUG(value):
    global current_addr_code, bin_code_section
    if not check_current_function("DEBUG"): return
    b_arg = struct.pack("<i", value) # знаковое?
    result = bytearray([0x28]) + b_arg
    bin_code_section += result
    current_addr_code += len(result)


# --- Функции для декомпилированного кода (заглушки или реальная логика) ---
# Они должны вызывать соответствующие инструкции ассемблера (PUSHINTEGER, ADD и т.д.)
class instr:
    """Представляет операцию в выражении декомпилятора."""
    def __init__(self, id, params):
       self.id = id
       self.params = params

def Command(command_name, inputs):
    """Декомпилированная версия команды."""
    if not check_current_function("Command"): return
    print(f"  Вызов Command: {command_name}, Inputs: {inputs}") # Отладка
    # Обрабатываем входы (выражения) в правильном порядке
    # (обратный для стека)
    if isinstance(inputs, list):
         # Входы уже должны быть в порядке вызова (не reverse)
        for expr in inputs:
            compile_expr(expr)
    elif inputs is not None: # Если один вход
         compile_expr(inputs)

    # Вызываем RUNCMD с количеством входов
    input_count = len(inputs) if isinstance(inputs, list) else (1 if inputs is not None else 0)
    RUNCMD(input_count, command_name)
    # Декомпилятор часто добавляет POP после Command
    # POP(input_count * 4) # Добавлять ли POP здесь? Зависит от стиля декомпиляции.


def AssignVar(symbol, expr):
    """Декомпилированная версия присваивания."""
    global current_stack, variable_names
    if not check_current_function("AssignVar"): return
    print(f"  Вызов AssignVar: {symbol} = {expr}") # Отладка

    # 1. Вычисляем выражение (результат окажется на вершине стека)
    compile_expr(expr)

    # 2. Определяем индекс символа в текущем контексте
    target_index = -1
    if symbol.startswith("PARAM_"):
         try: target_index = int(symbol.split('_')[1])
         except: pass
    else:
         # Ищем существующую переменную или создаем новую
         found = False
         for idx, name in variable_names.items():
              if name == symbol:
                   target_index = idx
                   found = True
                   break
         if not found:
              # Новая переменная, ее индекс = текущий размер стека - 1 (т.к. результат уже на стеке)
              target_index = len(current_stack) - 1
              if target_index < len(current_function.input_args):
                  print(f"ОШИБКА: Попытка создать переменную '{symbol}', но индекс {target_index} занят параметром.")
                  # Что делать? Пока просто запишем по этому индексу
              print(f"    Создана новая переменная '{symbol}' с индексом {target_index}")
              variable_names[target_index] = symbol

    if target_index == -1:
         print(f"ОШИБКА: Не удалось определить индекс для символа '{symbol}' в AssignVar.")
         # Убираем значение со стека, чтобы избежать ошибок дальше?
         if current_stack: POP(4)
         return

    # 3. Используем PUTBACKATINDEX, чтобы переместить значение с вершины стека
    #    в нужную позицию (target_index).
    #    Смещение = (целевой_индекс - (текущий_размер_стека - 1)) * 4
    current_top_index = len(current_stack) - 1
    if current_top_index == target_index:
         # Значение уже на месте (на вершине), ничего делать не нужно
         print(f"    AssignVar: Значение для '{symbol}' уже на вершине стека (индекс {target_index}).")
         pass
    elif current_top_index > target_index:
         offset = (target_index - current_top_index) * 4
         print(f"    AssignVar: Перемещение значения для '{symbol}' с вершины на индекс {target_index} (смещение {offset}).")
         PUTBACKATINDEX(offset)
    else: # target_index > current_top_index - это ошибка, стек меньше ожидаемого
         print(f"ОШИБКА: Стек ({current_top_index}) меньше целевого индекса ({target_index}) для AssignVar '{symbol}'.")
         # Убираем значение со стека
         if current_stack: POP(4)


def SetVarToAnotherVarValue(symbolout, input):
    """Декомпилированная версия (для обратной совместимости)."""
    # Просто преобразуем в AssignVar(symbolout, LoadVar(input))
    print(f"  Вызов SetVarToAnotherVarValue: {symbolout} = {input}") # Отладка
    AssignVar(symbolout, LoadVar(input))


def WriteAtIndex(value_in_expr, index_expr):
    """Декомпилированная версия."""
    global current_stack, variable_names
    if not check_current_function("WriteAtIndex"): return
    print(f"  Вызов WriteAtIndex: Value={value_in_expr}, Index={index_expr}") # Отладка

    # 1. Вычисляем выражение для индекса
    compile_expr(index_expr)
    # 2. Вычисляем выражение для значения
    compile_expr(value_in_expr)
    # 3. Вызываем PUTBACK с нужным смещением
    # Значение на вершине, индекс под ним. Смещение от указателя (после снятия значения) до индекса = -4.
    PUTBACK(-4)


def compile_expr(input_expr):
    """Рекурсивно компилирует выражение декомпилятора."""
    global current_stack
    # print(f"    Компиляция выражения: {input_expr}") # Отладочный print (может быть много)

    if input_expr is None:
        print("ПРЕДУПРЕЖДЕНИЕ: compile_expr получил None.")
        return

    # 1. Список: это оператор [op1, op2, instr] или [op1, instr]
    if isinstance(input_expr, list):
        if not input_expr:
             print("ПРЕДУПРЕЖДЕНИЕ: compile_expr получил пустой список.")
             return
        # Компилируем операнды рекурсивно
        num_operands = len(input_expr) - 1
        for i in range(num_operands):
            compile_expr(input_expr[i])
        # Выполняем оператор (последний элемент списка)
        operator_instr = input_expr[-1]
        if isinstance(operator_instr, instr):
            op_code = operator_instr.id
            # Вызываем соответствующую функцию ассемблера
            if op_code == 0x10: ADD()
            elif op_code == 0x11: SUBTRACT()
            elif op_code == 0x12: MULTIPLY()
            elif op_code == 0x13: DIVIDE()
            elif op_code == 0x14: MODULO()
            elif op_code == 0x15: EQUAL()
            elif op_code == 0x16: NONEQUAL()
            elif op_code == 0x17: GREATERTHAN()
            elif op_code == 0x18: GREATEROREQ()
            elif op_code == 0x19: LOWERTHAN()
            elif op_code == 0x1A: LOWEROREQ()
            elif op_code == 0x1B: AND_()
            elif op_code == 0x1C: OR1()
            elif op_code == 0x1D: OR2()
            elif op_code == 0x1E: OR3()
            elif op_code == 0x1F: NEGATIVE()
            elif op_code == 0x20: ISFALSE()
            elif op_code == 0x21: XOR1()
            else: print(f"ОШИБКА: Неизвестный ID оператора {op_code} в compile_expr.")
        else: print(f"ОШИБКА: Последний элемент в списке выражения не является instr: {operator_instr}")

    # 2. Объект instr: это LoadVar, LoadInt и т.д.
    elif isinstance(input_expr, instr):
        op_code = input_expr.id
        params = input_expr.params
        if op_code == 2: # LoadVar
            symbol = params[0]
            idx = find_symbol_in_stack(symbol)
            offset = (idx - len(current_stack)) * 4 # Смещение от текущего верха стека
            RETRIEVEELEMENTATINDEX(offset)
        elif op_code == 3: # LoadVar2
            symbol = params[0]
            idx = find_symbol_in_stack(symbol)
            offset = (idx - len(current_stack)) * 4
            RETRIEVEELEMENTATINDEX2(offset)
        elif op_code == 4: # LoadInt (в декомпиляторе это PUSHCONVERTINTEGER)
            PUSHCONVERTINTEGER(params[0])
        elif op_code == 7: # Load32
            LOAD32(params[0])
        elif op_code == 9: # LoadResult
            LOADRESULT(params[0])
        elif op_code == 0x22: # CallerID (PUSHCALLERFUNCTIONINDEX)
            PUSHCALLERFUNCTIONINDEX()
        elif op_code == 0x23: # ReturnAddress (PUSHRETURNADDRESS)
            PUSHRETURNADDRESS(params[0]) # params[0] - это метка (строка)
        elif op_code == 0x29: # TopVar - используется как маркер, ничего не генерирует
             print(f"    Обработка TopVar для '{params[0]}' (ничего не генерируется).")
             pass
        else: print(f"ОШИБКА: Неизвестный ID инструкции {op_code} в compile_expr.")

    # 3. Строка: это PUSHSTRING
    elif isinstance(input_expr, str):
        PUSHSTRING(input_expr)

    # 4. Число (int/float) или UNDEF/INT/FLOAT: это PUSH
    elif isinstance(input_expr, (int, float)):
         # Пытаемся определить, было ли значение обернуто в INT/FLOAT/UNDEF
         # Это сложно сделать надежно без передачи типа из декомпилятора.
         # Пока предполагаем, что если пришло чистое число, это INT или FLOAT.
         if isinstance(input_expr, float):
              PUSHFLOAT(input_expr)
         else: # Считаем int по умолчанию
              PUSHINTEGER(input_expr) # Используем PUSHINTEGER (INT)
    else:
         # Может быть результат UNDEF(), INT(), FLOAT() - передаем как есть в PUSHUNDEFINED
         # Это не совсем верно, т.к. тип теряется, но лучше чем ничего.
         # Правильнее было бы передавать тип из декомпилятора.
         print(f"ПРЕДУПРЕЖДЕНИЕ: compile_expr получил неизвестный тип {type(input_expr)}, значение {input_expr}. Использую PUSHUNDEFINED.")
         PUSHUNDEFINED(input_expr)


# --- Функции-обертки для декомпилированного кода ---
def LoadVar(symbol): return instr(2, [symbol])
def LoadVar2(symbol): return instr(3, [symbol])
def LoadInt(value): return instr(4, [value]) # Соответствует PUSHCONVERTINTEGER
def Load32(index): return instr(7, [index])
def LoadResult(index): return instr(9, [index])
def CallerID(): return instr(0x22, [])
def ReturnAddress(loc): return instr(0x23, [loc])
def TopVar(symbol): return instr(0x29, [symbol]) # Маркер

def add(op1, op2): return [op1, op2, instr(0x10, [])]
def subtract(op1, op2): return [op1, op2, instr(0x11, [])]
def multiply(op1, op2): return [op1, op2, instr(0x12, [])]
def divide(op1, op2): return [op1, op2, instr(0x13, [])]
def modulo(op1, op2): return [op1, op2, instr(0x14, [])]
def equal(op1, op2): return [op1, op2, instr(0x15, [])]
def nonequal(op1, op2): return [op1, op2, instr(0x16, [])]
def greaterthan(op1, op2): return [op1, op2, instr(0x17, [])]
def greateroreq(op1, op2): return [op1, op2, instr(0x18, [])]
def lowerthan(op1, op2): return [op1, op2, instr(0x19, [])]
def loweroreq(op1, op2): return [op1, op2, instr(0x1A, [])]
def and_(op1, op2): return [op1, op2, instr(0x1B, [])]
def or1(op1, op2): return [op1, op2, instr(0x1C, [])]
def or2(op1, op2): return [op1, op2, instr(0x1D, [])]
def or3(op1, op2): return [op1, op2, instr(0x1E, [])]
def negative(op1): return [op1, instr(0x1F, [])]
def isfalse(op1): return [op1, instr(0x20, [])]
def xor1(op1): return [op1, instr(0x21, [])]

def Return():
    if not check_current_function("Return"): return
    # Очистка стека не нужна здесь, EXIT сделает свое дело
    EXIT()

# --- Остальные функции для декомпилятора (если они используются) ---
# def CreateVar(symbol, value): pass # Не используется, AssignVar покрывает это
# def SetVar(symbolout, symbolin): pass # Используем AssignVar(symbolout, LoadVar(symbolin))

def CallFunction(fun_name, inputs):
    global current_function, current_addr_code, return_addr_vector
    if not check_current_function("CallFunction"): return
    print(f"  Вызов CallFunction: {fun_name}, Inputs: {inputs}") # Отладка

    # 1. PUSH ID текущей функции
    PUSHCALLERFUNCTIONINDEX() # Используем специальную функцию
    # 2. PUSH адрес возврата (адрес *после* инструкции CALL)
    # Сохраняем текущий адрес кода, где будет placeholder адреса возврата
    push_return_addr_placeholder = current_addr_code + 2 # +2 от PUSHUNDEFINED(0) ниже
    PUSHUNDEFINED(0) # Placeholder для адреса возврата

    # 3. Компилируем входные аргументы
    CallFunctionWithoutReturnAddr(fun_name, inputs) # Эта функция вызовет CALL(fun_name)

    # 4. Регистрируем адрес возврата
    # Адрес назначения - текущий адрес кода (конец инструкции CALL)
    return_target = jump_target()
    return_target.addr_references.append(push_return_addr_placeholder)
    return_target.addr_destination = current_addr_code # Адрес после CALL
    return_addr_vector.append(return_target)

def CallFunctionWithoutReturnAddr(fun_name, inputs):
    if not check_current_function("CallFunctionWithoutReturnAddr"): return
    print(f"  Вызов CallFunctionWithoutReturnAddr: {fun_name}, Inputs: {inputs}") # Отладка
    # Компилируем входные аргументы (они должны быть в правильном порядке)
    if isinstance(inputs, list):
        for expr in inputs:
            compile_expr(expr)
    elif inputs is not None:
        compile_expr(inputs)
    # Вызываем инструкцию CALL
    CALL(fun_name) # Передаем имя функции, CALL сам найдет индекс


def JumpWhenTrue(loc, condition):
    if not check_current_function("JumpWhenTrue"): return
    print(f"  Вызов JumpWhenTrue: Loc={loc}, Condition={condition}") # Отладка
    compile_expr(condition)
    JUMPIFTRUE(loc) # Передаем имя метки

def JumpWhenFalse(loc, condition):
    if not check_current_function("JumpWhenFalse"): return
    print(f"  Вызов JumpWhenFalse: Loc={loc}, Condition={condition}") # Отладка
    compile_expr(condition)
    JUMPIFFALSE(loc) # Передаем имя метки

def CallFunctionFromAnotherScript(file, fun, inputs):
    global current_function, current_addr_code, return_addr_vector
    if not check_current_function("CallFunctionFromAnotherScript"): return
    print(f"  Вызов CallFunctionFromAnotherScript: File={file}, Fun={fun}, Inputs={inputs}") # Отладка

    # 1. Добавляем инструкцию 0x25 (PUSHRETURNADDRESSFROMANOTHERSCRIPT)
    # Адрес назначения будет текущим адресом кода *после* вызова CALLFROMANOTHERSCRIPT
    push_return_addr_placeholder = current_addr_code + 1 # Адрес для записи в опкод 0x25
    PUSHRETURNADDRESSFROMANOTHERSCRIPT("DUMMY_LABEL") # Используем временную метку, она не важна

    # 2. Компилируем входные аргументы и вызываем 0x22
    CallFunctionFromAnotherScriptWithoutReturnAddr(file, fun, inputs)

    # 3. Регистрируем адрес возврата для 0x25
    return_target = jump_target()
    return_target.addr_references.append(push_return_addr_placeholder)
    return_target.addr_destination = current_addr_code # Адрес после CALLFROMANOTHERSCRIPT
    return_addr_vector.append(return_target)


def CallFunctionFromAnotherScriptWithoutReturnAddr(file, fun, inputs):
    if not check_current_function("CallFunctionFromAnotherScriptWithoutReturnAddr"): return
    print(f"  Вызов CallFunctionFromAnotherScriptWithoutReturnAddr: File={file}, Fun={fun}, Inputs={inputs}") # Отладка
    input_count = 0
    if isinstance(inputs, list):
        input_count = len(inputs)
        for expr in inputs:
            compile_expr(expr)
    elif inputs is not None:
        input_count = 1
        compile_expr(inputs)
    CALLFROMANOTHERSCRIPT(file, fun, input_count)

def CallFunctionFromAnotherScript2(file, fun, inputs):
    global current_stack, current_function
    if not check_current_function("CallFunctionFromAnotherScript2"): return
    print(f"  Вызов CallFunctionFromAnotherScript2: File={file}, Fun={fun}, Inputs={inputs}") # Отладка

    # --- Эта функция требует особого обращения со стеком ---
    # Сохраняем текущий стек (индексы)
    stack_before_call = current_stack.copy()
    input_count = 0

    # 1. Вычисляем и сохраняем аргументы через SAVERESULT
    if isinstance(inputs, list):
        input_count = len(inputs)
        # Важно: аргументы вычисляются в том порядке, в котором они переданы
        for i, expr in enumerate(inputs):
            compile_expr(expr)
            SAVERESULT(i + 1) # SAVERESULT использует индексы 1, 2, ...
    elif inputs is not None:
        input_count = 1
        compile_expr(inputs)
        SAVERESULT(1)

    # 2. Очищаем текущий стек (кроме параметров функции?)
    # Это рискованно, если на стеке были другие важные вещи.
    # В декомпилированной версии предполагаем, что стек нужно очистить.
    if len(stack_before_call) > len(current_function.input_args):
         # POP только переменных, созданных в этой функции
         vars_to_pop = len(stack_before_call) - len(current_function.input_args)
         if vars_to_pop > 0:
              print(f"    POP({vars_to_pop * 4}) перед CALLFROMANOTHERSCRIPT2")
              POP(vars_to_pop * 4)

    # 3. Загружаем сохраненные аргументы через LOADRESULT (в обратном порядке)
    for i in range(input_count, 0, -1):
        LOADRESULT(i)

    # 4. Вызываем саму инструкцию 0x23
    CALLFROMANOTHERSCRIPT2(file, fun, input_count)

    # 5. Восстанавливаем стек симуляции (для декомпилятора)
    # current_stack = stack_before_call # Восстанавливаем исходный стек симуляции
    # После вызова 0x23 стек не меняется, так что восстанавливать не нужно
    # Но нужно откатить изменения в self.variable_names, если LOAD/SAVE создали временные
    # Это сложно сделать надежно без более глубокой интеграции.

# --- END OF FILE ED9Assembler.py ---