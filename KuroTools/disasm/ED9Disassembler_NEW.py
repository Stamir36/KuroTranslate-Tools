# --- START OF FILE ED9Disassembler.py ---

import math
import struct
import os
import sys # Добавлен импорт sys
from pathlib import Path
from lib.parser import process_data, readint, readintoffset, readtextoffset, remove2MSB, get_actual_value_str
from disasm.script import script
import disasm.ED9InstructionsSet as ED9InstructionsSet
import traceback
from processcle import processCLE

def get_var_symbol(var_names, stack) -> str:
    # Эта функция больше не используется напрямую в исправленной логике,
    # но оставляем её на случай, если она нужна в других частях.
    idx = len(stack) - 1
    if idx < 0:
         return "INVALID_STACK_INDEX"
    if idx not in var_names:
        var_names[idx] = "VAR_" + str(idx) # Используем индекс как имя по умолчанию
    return var_names[idx]

class ED9Disassembler(object):
    def __init__(self, markers, decomp):
        self.markers = markers
        self.decomp = decomp
        self.smallest_data_ptr = -1
        self.dict_stacks = {}
        self.instruction_stacks = {}
        self.variables_names = {}
        self.stream = None
        # Добавляем счетчик временных переменных для уникальности
        self.temp_var_counter = 0
        # Добавляем input_args для доступа в методах
        self.input_args = []


    def get_unique_temp_var_name(self, base_index, addr):
        """Генерирует уникальное имя для временной переменной."""
        self.temp_var_counter += 1
        # Можно добавить адрес для большей информативности при отладке
        # return f"TEMP_VAR_{base_index}_AT_{hex(addr)}_{self.temp_var_counter}"
        return f"TEMP_VAR_{self.temp_var_counter}" # Более короткий вариант

    def parse(self, path):
        print(f"    [DEBUG parse] Начало для {path}") # <-- Точка в начале parse
        filename = Path(path).stem
        filesize = os.path.getsize(path)

        # --- Инициализация потока ---
        self.stream = None
        # ---------------------------

        try:
            print(f"    [DEBUG parse] Открытие файла {path}...")
            self.stream = open(path, "rb")
            magic = self.stream.read(4)
            if magic != b"#scp":
                self.stream.close() # Закрываем перед расшифровкой
                print(f"    [DEBUG parse] Файл зашифрован, вызов processCLE...")
                try:
                    with open(path, mode='rb') as encrypted_file: fileContent = encrypted_file.read()
                    decrypted_file = processCLE(fileContent)
                    print(f"    [DEBUG parse] processCLE завершен, перезапись файла...")
                    with open(path, "w+b") as outputfile: outputfile.write(decrypted_file)
                    filesize = os.path.getsize(path) # Обновляем размер
                    print(f"    [DEBUG parse] Повторное открытие файла...")
                    self.stream = open(path, "rb") # Открываем заново
                except Exception as cle_error:
                     print(f"    [DEBUG parse] Ошибка при расшифровке файла {path}: {cle_error}")
                     # Нет необходимости закрывать self.stream здесь, он уже закрыт или не был открыт повторно
                     raise # Пробрасываем ошибку дальше, чтобы batch скрипт ее обработал
            else:
                 print(f"    [DEBUG parse] Файл не зашифрован, переход в начало.")
                 self.stream.seek(0)

            # --- Сброс состояния ---
            print(f"    [DEBUG parse] Сброс состояния...")
            self.temp_var_counter = 0
            self.smallest_data_ptr = filesize
            self.dict_stacks = {}
            self.instruction_stacks = {}
            self.variables_names = {}
            ED9InstructionsSet.locations_dict = {}
            ED9InstructionsSet.location_counter = 0
            ED9InstructionsSet.smallest_data_ptr = sys.maxsize
            # ------------------------

            print(f"    [DEBUG parse] Создание объекта script...")
            # Передаем self.stream, который теперь гарантированно открыт (или была ошибка выше)
            self.script = script(self.stream, filename, markers=self.markers)
            print(f"    [DEBUG parse] Объект script создан, вызов write_script...")
            self.write_script()
            print(f"    [DEBUG parse] write_script завершен.") # <-- Точка после write_script
        finally:
             # Гарантированно закрываем файл, если он был открыт
             if self.stream and not self.stream.closed:
                 print(f"    [DEBUG parse] Закрытие файла в finally.")
                 self.stream.close()
        print(f"    [DEBUG parse] Завершение для {path}") # <-- Точка в конце parse


    def write_script(self):
        print(f"      [DEBUG write_script] Начало для {self.script.name}...")
        # Сбрасываем счетчик временных переменных перед записью скрипта
        self.temp_var_counter = 0

        output_py_filepath = self.script.name + ".py"

        with open(output_py_filepath, "wt", encoding='utf8') as python_file:
            python_file.write("from disasm.ED9Assembler import *\n\n")
            python_file.write("def script():\n")
            python_file.write("\n    create_script_header(\n")
            python_file.write("\tname= \"" + self.script.name+"\",\n")
            python_file.write("\tvarin= " + "[")
            # ... (остальная часть записи заголовка) ...
            for id_in in range(len(self.script.script_variables_in) - 1):
                python_file.write("[")
                python_file.write(self.wrap_conversion(self.script.script_variables_in[id_in][0]) + ", ")
                python_file.write(self.wrap_conversion(self.script.script_variables_in[id_in][1]))
                python_file.write("],")
            if (len(self.script.script_variables_in) != 0):
                python_file.write("[")
                python_file.write(self.wrap_conversion(self.script.script_variables_in[len(self.script.script_variables_in) - 1][0]) + ", ")
                python_file.write(self.wrap_conversion(self.script.script_variables_in[len(self.script.script_variables_in) - 1][1]))
                python_file.write("]")

            python_file.write("],\n")

            python_file.write("\tvarout= " + "[")
            for id_in in range(len(self.script.script_variables_out) - 1):
                python_file.write("[")
                python_file.write(self.wrap_conversion(self.script.script_variables_out[id_in][0]) + ", ")
                python_file.write(self.wrap_conversion(self.script.script_variables_out[id_in][1]))
                python_file.write("],")
            if (len(self.script.script_variables_out) != 0):
                python_file.write("[")
                python_file.write(self.wrap_conversion(self.script.script_variables_out[len(self.script.script_variables_out) - 1][0]) + ", ")
                python_file.write(self.wrap_conversion(self.script.script_variables_out[len(self.script.script_variables_out) - 1][1]))
                python_file.write("]")
            python_file.write("],\n")
            python_file.write("    )\n")

            functions_sorted_by_addr = self.script.functions.copy()
            functions_sorted_by_addr.sort(key=lambda fun: fun.start)

            for f in self.script.functions:
                 python_file.write(self.add_function_str(f))

            print(f"      [DEBUG write_script] Начало цикла декомпиляции функций...")
            if (self.decomp == False):
                for f in functions_sorted_by_addr:
                    print(f"        [DEBUG write_script] Дизассемблирование функции {f.name}...")
                    self.add_return_addresses(f) # add_return_addresses может модифицировать инструкции
                    python_file.write(self.disassemble_function(f))
                    print(f"        [DEBUG write_script] Дизассемблирование {f.name} завершено.")
            else:
                for f in functions_sorted_by_addr:
                    print(f"        [DEBUG write_script] Декомпиляция функции {f.name}...")
                    # Сброс состояния для функции
                    self.variables_names = {}
                    self.dict_stacks = {}
                    self.instruction_stacks = []
                    self.temp_var_counter = 0
                    self.input_args = f.input_args # Сохраняем параметры текущей функции
                    for in_id in range(len(f.input_args)):
                        self.variables_names[in_id] = f"PARAM_{in_id}"

                    print(f"          [DEBUG write_script] Вызов decompile_function для {f.name}...")
                    decompiled_code = self.decompile_function(f)
                    print(f"          [DEBUG write_script] decompile_function для {f.name} завершен.")
                    python_file.write(decompiled_code)
                    print(f"          [DEBUG write_script] Запись кода для {f.name} завершена.")

            python_file.write("\n    compile()")
            python_file.write("\n\nscript()")
        print(f"      [DEBUG write_script] Завершение для {self.script.name}.")


    def add_function_str(self, function)->str:
        # ... (код без изменений) ...
        result = "    add_function(\n"
        result = result + "\tname= " + "\"" + function.name + "\",\n"
        result = result + "\tinput_args  = " + "["
        for id_in in range(len(function.input_args) - 1):
            result = result + self.wrap_conversion(function.input_args[id_in]) + ", "
        if (len(function.input_args) != 0):
            result = result + self.wrap_conversion(function.input_args[len(function.input_args) - 1])
        result = result + "],\n"

        result = result + "\toutput_args = " + "["
        for id_in in range(len(function.output_args) - 1):
            result = result + self.wrap_conversion(function.output_args[id_in]) + ", "
        if (len(function.output_args) != 0):
            result = result + self.wrap_conversion(function.output_args[len(function.output_args) - 1])
        result = result + "],\n"

        result = result + "\tb0= " +  str(hex(function.b0)) + ",\n"
        result = result + "\tb1= " +  str(hex(function.b1)) + ",\n"
        result = result + "    )\n\n"
        return result


    def update_stack(self, instruction, stack, instruction_id):
        # ... (код с проверками на IndexError) ...
        try:
            functions = self.script.functions

            if instruction.op_code == 0x26:
                pass
            else:

                op_code = instruction.op_code
                #print(str(hex(op_code)), " ", str(stack), " ", str(hex(instruction.addr)))
                if (op_code == 1):

                    popped_els = int(instruction.operands[0].value/4)
                    # --- Защита от pop из пустого стека ---
                    actual_pops = min(popped_els, len(stack))
                    if actual_pops < popped_els:
                         print(f"ПРЕДУПРЕЖДЕНИЕ (update_stack): Попытка снять {popped_els} элементов, но в стеке только {len(stack)} по адресу {hex(instruction.addr)}")
                    for i in range(actual_pops):
                        stack.pop()
                    # --- Конец защиты ---

                elif (op_code == 0) or (op_code == 4):
                    # В стек кладем индекс стека, а не ID инструкции
                    stack.append(len(stack)) # Новый элемент будет иметь этот индекс
                elif (op_code == 2) or (op_code == 3):
                    stack.append(len(stack))
                elif (op_code == 5):
                    if stack: stack.pop()
                    else: print(f"ПРЕДУПРЕЖДЕНИЕ (update_stack): POP для опкода 5 из пустого стека по адресу {hex(instruction.addr)}")
                elif (op_code == 6):
                    if stack: stack.pop()
                    else: print(f"ПРЕДУПРЕЖДЕНИЕ (update_stack): POP для опкода 6 из пустого стека по адресу {hex(instruction.addr)}")
                elif (op_code == 7):
                    stack.append(len(stack))
                elif (op_code == 8):
                    if stack: stack.pop()
                    else: print(f"ПРЕДУПРЕЖДЕНИЕ (update_stack): POP для опкода 8 из пустого стека по адресу {hex(instruction.addr)}")
                elif (op_code == 9):
                    stack.append(len(stack))
                elif (op_code == 0x0A):
                    if stack: stack.pop()
                    else: print(f"ПРЕДУПРЕЖДЕНИЕ (update_stack): POP для опкода 0x0A из пустого стека по адресу {hex(instruction.addr)}")
                elif (op_code == 0x0B):
                    pass
                elif (op_code == 0x0D):
                     stack.clear() # Очищаем стек при EXIT
                elif (op_code == 0x0C):
                    index_fun = instruction.operands[0].value
                    # --- Добавлена проверка индекса ---
                    if 0 <= index_fun < len(functions):
                        called_fun = functions[index_fun]
                        varin = len(called_fun.input_args)
                        pops_needed = varin + 2
                        actual_pops = min(pops_needed, len(stack))
                        if actual_pops < pops_needed:
                            print(f"ПРЕДУПРЕЖДЕНИЕ (update_stack): CALL {called_fun.name} требует снять {pops_needed}, но в стеке {len(stack)} по адресу {hex(instruction.addr)}")
                        for i in range(actual_pops):
                            stack.pop()
                    else:
                         print(f"ОШИБКА (update_stack): Неверный индекс функции {index_fun} для CALL по адресу {hex(instruction.addr)}. Стек не изменен.")

                elif (op_code == 0x0E):
                    if stack: stack.pop()
                    else: print(f"ПРЕДУПРЕЖДЕНИЕ (update_stack): POP для опкода 0x0E из пустого стека по адресу {hex(instruction.addr)}")
                elif (op_code == 0x0F):
                    if stack: stack.pop()
                    else: print(f"ПРЕДУПРЕЖДЕНИЕ (update_stack): POP для опкода 0x0F из пустого стека по адресу {hex(instruction.addr)}")
                elif ((op_code >= 0x10) and(op_code <= 0x1E)):
                     if len(stack) >= 2:
                         stack.pop()
                         stack.pop()
                         stack.append(len(stack)) # Индекс нового элемента
                     else:
                          print(f"ПРЕДУПРЕЖДЕНИЕ (update_stack): Недостаточно операндов ({len(stack)}) для бинарной операции {hex(op_code)} по адресу {hex(instruction.addr)}")
                          if stack: stack[-1] = len(stack) -1 # Помечаем верхний элемент как результат?

                elif ((op_code >= 0x1F) and (op_code <= 0x21)):
                    if stack:
                        stack.pop()
                        stack.append(len(stack)) # Индекс нового элемента
                    else:
                         print(f"ПРЕДУПРЕЖДЕНИЕ (update_stack): Пустой стек для унарной операции {hex(op_code)} по адресу {hex(instruction.addr)}")

                elif (op_code == 0x22):
                    varin = instruction.operands[2].value
                    pops_needed = varin + 5
                    actual_pops = min(pops_needed, len(stack))
                    if actual_pops < pops_needed:
                         print(f"ПРЕДУПРЕЖДЕНИЕ (update_stack): CALLFROMANOTHERSCRIPT требует снять {pops_needed}, но в стеке {len(stack)} по адресу {hex(instruction.addr)}")
                    for i in range(actual_pops):
                        stack.pop()
                elif (op_code == 0x23):
                    pass # Стек не меняется

                elif (op_code == 0x24):
                    pass # Стек не меняется (POP идет отдельно)

                elif (op_code == 0x25):
                      base_idx = len(stack)
                      stack.append(base_idx)
                      stack.append(base_idx + 1)
                      stack.append(base_idx + 2)
                      stack.append(base_idx + 3)
                      stack.append(base_idx + 4)
                elif (op_code == 0x27):
                    count = instruction.operands[0].value
                    actual_pops = min(count, len(stack))
                    if actual_pops < count:
                         print(f"ПРЕДУПРЕЖДЕНИЕ (update_stack): POP2 требует снять {count}, но в стеке {len(stack)} по адресу {hex(instruction.addr)}")
                    for i in range(actual_pops):
                        stack.pop()
        except IndexError:
             print(f"ПРЕДУПРЕЖДЕНИЕ (update_stack): Попытка доступа к элементу стека по неверному индексу по адресу {hex(instruction.addr)}, опкод {hex(op_code)}. Размер стека: {len(stack)}")
        except Exception as err:
            print(f"ПРЕДУПРЕЖДЕНИЕ (update_stack): Неожиданная ошибка по адресу {hex(instruction.addr)}, опкод {hex(op_code)}: {err}")


    def add_var_to_stack(self, instruction, stack)->str:
        # --- ИСПРАВЛЕННАЯ ЛОГИКА из прошлого ответа ---
        result = ""
        top_stack_index = len(stack) - 1 # Индекс верхнего элемента ДО выполнения инструкции (5 или 6)
        offset = instruction.operands[0].value

        # Индекс целевого элемента относительно начала стека (0 для первого параметра)
        base_stack_size_for_offset = len(stack) - 1
        target_runtime_index = base_stack_size_for_offset + (offset // 4)

        # --- Получаем имя переменной с вершины стека ---
        top_var_name = "UNKNOWN_TOP"
        if top_stack_index >= 0:
             # Используем индекс параметра, если он < len(self.input_args)
             current_top_index_in_vars = stack[top_stack_index] # Получаем ИНДЕКС из стека
             if current_top_index_in_vars < len(self.input_args): # Это параметр
                 top_var_name = self.variables_names.get(current_top_index_in_vars, f"PARAM_{current_top_index_in_vars}?")
             else: # Это переменная
                 top_var_name = self.variables_names.get(current_top_index_in_vars, self.get_unique_temp_var_name(current_top_index_in_vars, instruction.addr))
                 if current_top_index_in_vars not in self.variables_names:
                      self.variables_names[current_top_index_in_vars] = top_var_name
        else:
             print(f"ПРЕДУПРЕЖДЕНИЕ (add_var_to_stack): Пустой стек при обработке {hex(instruction.op_code)} по адресу {hex(instruction.addr)}")

        # --- Получаем имя целевой переменной/параметра ---
        target_var_name = "UNKNOWN_TARGET"
        if target_runtime_index < 0:
            param_index = -target_runtime_index - 1
            if param_index < len(self.input_args):
                 target_var_name = self.variables_names.get(param_index, f"PARAM_{param_index}?")
            else:
                 print(f"ОШИБКА (add_var_to_stack): Неверный индекс параметра {param_index} (из смещения {offset}) по адресу {hex(instruction.addr)}")
                 target_var_name = f"INVALID_PARAM_{param_index}"
        else:
            target_var_name = self.variables_names.get(target_runtime_index, self.get_unique_temp_var_name(target_runtime_index, instruction.addr))
            if target_runtime_index not in self.variables_names:
                 self.variables_names[target_runtime_index] = target_var_name

        # Формируем строку вывода
        if instruction.op_code == 5: # PUTBACKATINDEX
            result = f"AssignVar(\"{target_var_name}\", TopVar(\"{top_var_name}\"))"
            if target_runtime_index >= len(self.input_args):
                 if not top_var_name.startswith("TEMP_VAR_") and not top_var_name.startswith("UNKNOWN_"):
                      self.variables_names[target_runtime_index] = top_var_name
                 elif target_var_name.startswith("TEMP_VAR_") or target_var_name.startswith("UNKNOWN_"):
                      self.variables_names[target_runtime_index] = top_var_name

        elif instruction.op_code == 6: # PUTBACK
            result = f"WriteAtIndex(TopVar(\"{top_var_name}\"), index=LoadVar(\"{target_var_name}\"))"

        return result


    def get_expression_str(self, instructions, instr_id, stack)->str:
         # --- ИСПРАВЛЕННАЯ ЛОГИКА из прошлого ответа ---
        # print(f"            [DEBUG get_expression_str] Начало с инструкции {instr_id} по адресу {hex(instructions[instr_id].addr)}")
        result = ""
        parameters_str = []
        start_instr_id = instr_id
        # Определяем границы выражения и симулируем стек
        last_valid_instruction_index = start_instr_id - 1
        expected_stack_after_expr = len(stack)
        processed_instr_count_in_expr = 0
        temp_i = start_instr_id
        try:
             while temp_i < len(instructions):
                 current_instr = instructions[temp_i]
                 op = current_instr.op_code
                 current_sim_stack_size = expected_stack_after_expr

                 if op in {0, 2, 3, 4, 7, 9}: expected_stack_after_expr += 1
                 elif 0x10 <= op <= 0x1E:
                     if current_sim_stack_size < 2: break
                     expected_stack_after_expr -= 1
                 elif 0x1F <= op <= 0x21:
                     if current_sim_stack_size < 1: break
                     pass
                 else: break

                 last_valid_instruction_index = temp_i
                 processed_instr_count_in_expr += 1
                 temp_i += 1
        except Exception as sim_e:
            print(f"Ошибка симуляции выражения по адресу {hex(instructions[instr_id].addr)}: {sim_e}")
            last_valid_instruction_index = instr_id - 1
            processed_instr_count_in_expr = 0
            expected_stack_after_expr = len(stack)

        if processed_instr_count_in_expr == 0:
             # print(f"            [DEBUG get_expression_str] Выражение не найдено (processed_instr_count_in_expr == 0)")
             return (None, -1)

        # print(f"            [DEBUG get_expression_str] Симуляция: выражение от {start_instr_id} до {last_valid_instruction_index}")

        # Собираем строку выражения
        copy_stack_for_params = stack.copy()
        for i in range(start_instr_id, last_valid_instruction_index + 1):
            instruction = instructions[i]
            op_code = instruction.op_code
            param_part = "ERROR_PARAM"
            try:
                if op_code == 0: param_part = self.wrap_conversion(instruction.operands[0].value)
                elif op_code == 2 or op_code == 3:
                    offset = instruction.operands[0].value
                    base_index = len(copy_stack_for_params) + (offset // 4)
                    var_name = "UNKNOWN_VAR"
                    # --- ИСПРАВЛЕНО: Индекс извлекаем из стека! ---
                    actual_stack_index = -1
                    stack_idx_for_offset = len(copy_stack_for_params) + (offset // 4) # Индекс относительно начала стека
                    if stack_idx_for_offset < 0: # Ссылка на параметр
                         param_idx = -stack_idx_for_offset -1
                         var_name = self.variables_names.get(param_idx, f"PARAM_{param_idx}?")
                    elif stack_idx_for_offset >= 0: # Ссылка на переменную
                         actual_stack_index = stack_idx_for_offset
                         var_name = self.variables_names.get(actual_stack_index, self.get_unique_temp_var_name(actual_stack_index, instruction.addr))
                         if actual_stack_index not in self.variables_names:
                              self.variables_names[actual_stack_index] = var_name

                    # if base_index < 0:
                    #     param_idx = -base_index - 1
                    #     var_name = self.variables_names.get(param_idx, f"PARAM_{param_idx}?")
                    # elif base_index >= 0 :
                    #      actual_stack_index = base_index # Индекс в variables_names
                    #      var_name = self.variables_names.get(actual_stack_index, self.get_unique_temp_var_name(actual_stack_index, instruction.addr))
                    #      if actual_stack_index not in self.variables_names:
                    #           self.variables_names[actual_stack_index] = var_name
                    # --- Конец исправления ---

                    load_func = "LoadVar" if op_code == 2 else "LoadVar2"
                    param_part = f"{load_func}(\"{var_name}\")"
                elif op_code == 4: param_part = f"LoadInt({instruction.operands[0].value})"
                elif op_code == 7: param_part = f"Load32({instruction.operands[0].value})"
                elif op_code == 9: param_part = f"LoadResult({instruction.operands[0].value})"
                elif 0x10 <= op_code <= 0x1E:
                    lowercase_name = instruction.name.lower().strip('_')
                    if len(parameters_str) < 2: raise IndexError("Недостаточно операндов для бинарной операции")
                    right = parameters_str.pop()
                    left = parameters_str.pop()
                    param_part = f"{lowercase_name}({left}, {right})"
                elif 0x1F <= op_code <= 0x21:
                    lowercase_name = instruction.name.lower()
                    if not parameters_str: raise IndexError("Недостаточно операндов для унарной операции")
                    operand_val = parameters_str.pop()
                    param_part = f"{lowercase_name}({operand_val})"

                parameters_str.append(param_part)
                # Обновляем симулированный стек для сборки параметров
                self.update_stack(instruction, copy_stack_for_params, i)
            except Exception as param_e:
                 print(f"ОШИБКА при сборке части выражения для опкода {hex(op_code)} по адресу {hex(instruction.addr)}: {param_e}")
                 parameters_str.append(f"ERROR_AT_{hex(instruction.addr)}")
                 break

        final_expression_str = parameters_str[0] if parameters_str else "INVALID_EXPRESSION"

        # Определяем имя переменной для результата
        result_stack_index = expected_stack_after_expr - 1
        output_var_name = "UNKNOWN_RESULT_VAR"
        if result_stack_index < 0:
             output_var_name = "INVALID_RESULT_INDEX"
        # --- ИСПРАВЛЕНО: Используем индекс параметра, если он < len(self.input_args) ---
        elif result_stack_index < len(self.input_args):
             output_var_name = self.variables_names.get(result_stack_index, f"PARAM_{result_stack_index}?")
        # --- Конец исправления ---
        else:
             output_var_name = self.variables_names.get(result_stack_index, self.get_unique_temp_var_name(result_stack_index, instructions[last_valid_instruction_index].addr))
             if result_stack_index not in self.variables_names:
                  self.variables_names[result_stack_index] = output_var_name


        # print(f"            [DEBUG get_expression_str] Результат: AssignVar(\"{output_var_name}\", ...), инструкций: {processed_instr_count_in_expr}")
        return (f"AssignVar(\"{output_var_name}\", {final_expression_str})", processed_instr_count_in_expr - 1)


    def get_instruction_number_for_expression(self, instructions, start)->int:
        # ... (код без изменений) ...
        i = start
        expected_operands = 1
        instr_count = 0
        while i >= 0 and expected_operands > 0:
            instruction = instructions[i]
            op_code = instruction.op_code
            instr_count += 1
            if op_code in {0, 2, 3, 4, 7, 9}:
                expected_operands -= 1
            elif 0x10 <= op_code <= 0x1E:
                expected_operands += 1
            elif 0x1F <= op_code <= 0x21:
                pass
            elif op_code == 0x26:
                 instr_count -= 1
                 pass
            else:
                instr_count -= 1
                break
            i -= 1

        if expected_operands > 0 and i < 0:
            print(f"Предупреждение (get_instruction_number): Не найдены все операнды для выражения, начинающегося с {hex(instructions[start].addr)}")
            return 1

        return instr_count


    def get_param_str_from_instructions(self, instructions, start, end)->str:
         # --- ИСПРАВЛЕННАЯ ЛОГИКА из прошлого ответа ---
        result = ""
        parameters_str = []
        # Используем копию стека *до* первой инструкции параметра
        current_sim_stack = self.instruction_stacks[start].copy() if start < len(self.instruction_stacks) else []

        for i in range(start, end + 1):
            instruction = instructions[i]
            op_code = instruction.op_code
            param_part = "UNKNOWN_PARAM_PART"

            try:
                if op_code == 0: param_part = self.wrap_conversion(instruction.operands[0].value)
                elif op_code == 2 or op_code == 3:
                    offset = instruction.operands[0].value
                    # --- ИСПРАВЛЕНО: Расчет индекса ---
                    base_index = len(current_sim_stack) + (offset // 4)
                    var_name = "UNKNOWN_VAR"
                    if base_index < 0:
                        param_idx = -base_index - 1
                        var_name = self.variables_names.get(param_idx, f"PARAM_{param_idx}?")
                    elif base_index >= 0:
                         actual_stack_index = base_index # Индекс для словаря имен
                         var_name = self.variables_names.get(actual_stack_index, f"TEMP_PARAM_{actual_stack_index}_AT_{hex(instruction.addr)}")
                         # Не сохраняем временное имя здесь
                    # --- Конец исправления ---
                    load_func = "LoadVar" if op_code == 2 else "LoadVar2"
                    param_part = f"{load_func}(\"{var_name}\")"

                elif op_code == 4: param_part = f"LoadInt({instruction.operands[0].value})"
                elif op_code == 7: param_part = f"Load32({instruction.operands[0].value})"
                elif op_code == 9: param_part = f"LoadResult({instruction.operands[0].value})"
                elif 0x10 <= op_code <= 0x1E:
                    lowercase_name = instruction.name.lower().strip('_')
                    if len(parameters_str) < 2: raise IndexError("Недостаточно операндов для бинарной операции")
                    right = parameters_str.pop()
                    left = parameters_str.pop()
                    param_part = f"{lowercase_name}({left}, {right})"
                elif 0x1F <= op_code <= 0x21:
                    lowercase_name = instruction.name.lower()
                    if not parameters_str: raise IndexError("Недостаточно операндов для унарной операции")
                    operand_val = parameters_str.pop()
                    param_part = f"{lowercase_name}({operand_val})"
                else:
                     print(f"Предупреждение (get_param_str): Неожиданный опкод {hex(op_code)} при сборке параметров по адресу {hex(instruction.addr)}.")
                     try: param_part = instruction.to_string(self.stream)
                     except Exception: param_part = f"UNEXPECTED_OP_{hex(op_code)}"

                parameters_str.append(param_part)
                # Обновляем симулированный стек
                self.update_stack(instruction, current_sim_stack, i)

            except Exception as param_e:
                 print(f"ОШИБКА при сборке части параметра для опкода {hex(op_code)} по адресу {hex(instruction.addr)}: {param_e}")
                 parameters_str.append(f"ERROR_AT_{hex(instruction.addr)}")
                 break

        parameters_str.reverse()
        result = ", ".join(parameters_str)
        return result

    # --- Остальные методы без изменений ---
    def make_function_py_header(self, function)->str:
        # ... (код без изменений) ...
        result = "#-------------------------\n"
        result = result + "#original file addr: " + str(hex(function.start)) + "\n"
        result = result + "    set_current_function(\""+ function.name + "\")\n"
        for id_strct in range(len(function.structs)):
            result = result + "    add_struct(\n"
            result = result + "\tid = " + str((function.structs[id_strct]["id"]))+",\n"
            result = result + "\tnb_sth1 = " + str(hex(function.structs[id_strct]["nb_sth1"]))+",\n"

            result = result + "\tarray2 = ["
            for id_in in range(len(function.structs[id_strct]["array2"]) - 1):
                result = result + self.wrap_conversion(function.structs[id_strct]["array2"][id_in]) + ", "
            if (len(function.structs[id_strct]["array2"]) != 0):
                result = result + self.wrap_conversion(function.structs[id_strct]["array2"][len(function.structs[id_strct]["array2"])- 1])
            result = result + "],\n"

            result = result + "    )\n\n"
        return result

    def disassemble_instructions(self, function)->str:
        # ... (код без изменений) ...
        result = "#Instructions " + function.name + "\n\n"
        for instruction in function.instructions:
            if instruction.addr in ED9InstructionsSet.locations_dict:
                result = result + "\n    Label(\""+ED9InstructionsSet.locations_dict[instruction.addr]+"\")\n\n"
            if instruction.op_code == 0x26 and self.markers == False: #Line Marker, we can separate with a new line
                result = result + "\n"
            else:
                result = result + "    " + instruction.to_string(self.stream) + "\n"
        return result

    def disassemble_function(self, function) -> str:
        # ... (код без изменений) ...
        fun_header = self.make_function_py_header(function)
        instructions = self.disassemble_instructions(function)

        return fun_header + instructions

    def wrap_conversion(self, value: int)->str:
        # ... (код без изменений) ...
        if not isinstance(value, int):
            if isinstance(value, str): return "\"" + value.replace('\\', '\\\\').replace('"', '\\"') + "\""
            return str(value)

        removeLSB = value & 0xC0000000
        actual_value = remove2MSB(value)
        MSB = removeLSB >> 0x1E
        if (MSB == 3):
            try:
                if self.stream is None or self.stream.closed:
                     print(f"Предупреждение (wrap_conversion): Поток файла закрыт при попытке чтения строки по адресу {hex(actual_value)}")
                     return f"\"ERROR_STREAM_CLOSED_{hex(actual_value)}\""
                text = readtextoffset(self.stream, actual_value).replace("\n", "\\n")
                text = text.replace('"', '\\"')
                return "\"" + text + "\""
            except Exception as e:
                 print(f"Предупреждение (wrap_conversion): Не удалось прочитать строку по адресу {hex(actual_value)}: {e}")
                 return f"\"ERROR_READING_STR_{hex(actual_value)}\""
        elif (MSB == 2):
            actual_value = actual_value << 2
            try:
                 float_val = struct.unpack("<f", struct.pack("<I", actual_value))[0]
                 return f"FLOAT({float_val:.8g})"
            except struct.error:
                 print(f"Предупреждение (wrap_conversion): Ошибка unpack для float {hex(actual_value)}")
                 return f"FLOAT(ERROR_{hex(actual_value)})"
        elif (MSB == 1):
            return "INT(" + str(int(actual_value)) + ")"
        else:
            return "UNDEF(" + str(hex(int(actual_value))) + ")"

# --- find_start_function_call без изменений ---
def find_start_function_call(instructions, instruction_id, varin)->int:
    # ... (код без изменений) ...
    counter_in = varin
    instruction_counter = -1
    while instruction_id + instruction_counter >= 0 and counter_in > 0 :
        current_instruction = instructions[instruction_id + instruction_counter]
        op_code = current_instruction.op_code

        if op_code == 0x26:
            instruction_counter -= 1
            continue

        if op_code == 0: counter_in -= 1
        elif op_code == 1:
             popped_bytes = current_instruction.operands[0].value
             popped_params = popped_bytes // 4
             counter_in += popped_params
        elif op_code == 2: counter_in -= 1
        elif op_code == 3: counter_in -= 1
        elif op_code == 4: counter_in -= 1
        elif op_code == 5: counter_in += 1
        elif op_code == 6: counter_in += 1
        elif op_code == 7: counter_in -= 1
        elif op_code == 8: counter_in += 1
        elif op_code == 9: counter_in -= 1
        elif op_code == 0x0A: counter_in += 1
        elif op_code == 0x0D: break
        elif op_code == 0x0C: break
        elif op_code == 0x0E: counter_in += 1
        elif op_code == 0x0F: counter_in += 1
        elif 0x10 <= op_code <= 0x1E: counter_in += 1
        elif 0x1F <= op_code <= 0x21: pass
        elif op_code == 0x22: break
        elif op_code == 0x23: break
        elif op_code == 0x24: break
        elif op_code == 0x25: counter_in -= 5
        elif op_code == 0x27:
             count = current_instruction.operands[0].value
             counter_in += count

        instruction_counter -= 1

    start_offset = instruction_counter + 1

    if instruction_id + instruction_counter < 0 and counter_in > 0:
        print(f"Предупреждение (find_start): Не найдены все параметры ({counter_in} осталось) для вызова в {hex(instructions[instruction_id].addr)}. Предполагается начало с индекса 0.")
        start_offset = -instruction_id

    current_idx = instruction_id + start_offset -1
    while current_idx >= 0 and instructions[current_idx].op_code == 0x26:
        start_offset -= 1
        current_idx -= 1

    remaining_params = counter_in if counter_in > 0 else 0

    return (start_offset, remaining_params)

# --- END OF FILE ED9Disassembler.py ---import math
import struct
import os
from pathlib import Path
from lib.parser import process_data, readint, readintoffset, readtextoffset, remove2MSB, get_actual_value_str
from disasm.script import script
import disasm.ED9InstructionsSet as ED9InstructionsSet
import traceback
from processcle import processCLE

def get_var_symbol(var_names, stack) -> str:
    if len(stack)-1 not in var_names:
        var_names[len(stack)-1] = "VAR_" + str(len(stack)-1)
        output = var_names[len(stack)-1]
    else:
        output = var_names[len(stack)-1]
    return output

class ED9Disassembler(object):
    def __init__(self, markers, decomp):
        self.markers = markers
        self.decomp = decomp
        self.smallest_data_ptr = -1
        self.dict_stacks = {}
        self.instruction_stacks = {}
        self.variables_names = {}
        self.stream = None

    def parse(self, path):
        filename = Path(path).stem
        filesize = os.path.getsize(path)

        self.stream = open(path, "rb")
        magic = self.stream.read(4)
        if magic != b"#scp":
            with open(path, mode='rb') as encrypted_file: 
                fileContent = encrypted_file.read()
            decrypted_file = processCLE(fileContent)
            with open(path, "w+b") as outputfile:
                outputfile.write(decrypted_file)
            filesize = os.path.getsize(path)
            self.stream = open(path, "rb")
            
        self.stream.seek(0)
        self.smallest_data_ptr = filesize
        self.script = script(self.stream, filename, markers = self.markers)
        self.write_script()


    def write_script(self):
        python_file = open(self.script.name + ".py", "wt",encoding='utf8')
        python_file.write("from disasm.ED9Assembler import *\n\n")
        python_file.write("def script():\n")
        python_file.write("\n    create_script_header(\n")
        python_file.write("\tname= \"" + self.script.name+"\",\n")
        python_file.write("\tvarin= " + "[")
        for id_in in range(len(self.script.script_variables_in) - 1):
            python_file.write("[")
            python_file.write(self.wrap_conversion(self.script.script_variables_in[id_in][0]) + ", ")
            python_file.write(self.wrap_conversion(self.script.script_variables_in[id_in][1])) 
            python_file.write("],")
        if (len(self.script.script_variables_in) != 0):
            python_file.write("[")
            python_file.write(self.wrap_conversion(self.script.script_variables_in[len(self.script.script_variables_in) - 1][0]) + ", ")
            python_file.write(self.wrap_conversion(self.script.script_variables_in[len(self.script.script_variables_in) - 1][1])) 
            python_file.write("]")
            
        python_file.write("],\n")

        python_file.write("\tvarout= " + "[")
        for id_in in range(len(self.script.script_variables_out) - 1):
            python_file.write("[")
            python_file.write(self.wrap_conversion(self.script.script_variables_out[id_in][0]) + ", ")
            python_file.write(self.wrap_conversion(self.script.script_variables_out[id_in][1])) 
            python_file.write("],")
        if (len(self.script.script_variables_out) != 0):
            python_file.write("[")
            python_file.write(self.wrap_conversion(self.script.script_variables_out[len(self.script.script_variables_out) - 1][0]) + ", ")
            python_file.write(self.wrap_conversion(self.script.script_variables_out[len(self.script.script_variables_out) - 1][1])) 
            python_file.write("]")
        python_file.write("],\n")

        python_file.write("    )\n")

        functions_sorted_by_addr = self.script.functions.copy()
        functions_sorted_by_addr.sort(key=lambda fun: fun.start) 

        for f in self.script.functions:
            python_file.write(self.add_function_str(f))

        if (self.decomp == False):
            for f in functions_sorted_by_addr:
                self.add_return_addresses(f)
                python_file.write(self.disassemble_function(f))
        else:
            for f in functions_sorted_by_addr:
                python_file.write(self.decompile_function(f))

        python_file.write("\n    compile()")
        python_file.write("\n\nscript()")
        python_file.close()


    def add_function_str(self, function)->str:

        result = "    add_function(\n"
        result = result + "\tname= " + "\"" + function.name + "\",\n"
        result = result + "\tinput_args  = " + "["
        for id_in in range(len(function.input_args) - 1):
            result = result + self.wrap_conversion(function.input_args[id_in]) + ", "
        if (len(function.input_args) != 0):
            result = result + self.wrap_conversion(function.input_args[len(function.input_args) - 1]) 
        result = result + "],\n"

        result = result + "\toutput_args = " + "["
        for id_in in range(len(function.output_args) - 1):
            result = result + self.wrap_conversion(function.output_args[id_in]) + ", "
        if (len(function.output_args) != 0):
            result = result + self.wrap_conversion(function.output_args[len(function.output_args) - 1]) 
        result = result + "],\n"

        result = result + "\tb0= " +  str(hex(function.b0)) + ",\n"
        result = result + "\tb1= " +  str(hex(function.b1)) + ",\n"
        result = result + "    )\n\n"
        return result

    def update_stack(self, instruction, stack, instruction_id):
        try:
            functions = self.script.functions

            if instruction.op_code == 0x26: 
                pass  
            else: 
                
                op_code = instruction.op_code
                #print(str(hex(op_code)), " ", str(stack), " ", str(hex(instruction.addr)))
                if (op_code == 1): 

                    popped_els = int(instruction.operands[0].value/4)
                    for i in range(popped_els):
                        stack.pop()

                elif (op_code == 0) or (op_code == 4):
                    
                    stack.append(instruction_id)
                elif (op_code == 2) or (op_code == 3):
                    stack.append(instruction_id)
                elif (op_code == 5): 
                    stack.pop()
                elif (op_code == 6):  #We pop
                    #index1 = int(len(stack) + instruction.operands[0].value/4)
                    #index2 = stack[index1]
                    #stack[index2] = instruction_id
                    stack.pop()
                elif (op_code == 7): 
                    stack.append(instruction_id)
                elif (op_code == 8): 
                    stack.pop()
                elif (op_code == 9): 
                    stack.append(instruction_id)
                elif (op_code == 0x0A): 
                    stack.pop()
                elif (op_code == 0x0B):
                    pass
                elif (op_code == 0x0D):
                    pass 
                elif (op_code == 0x0C): 
                    index_fun = instruction.operands[0].value
                    called_fun = functions[index_fun]
                    varin = len(called_fun.input_args)
                    for i in range(varin + 2): 
                        stack.pop()
                elif (op_code == 0x0E): 
                    stack.pop()
                elif (op_code == 0x0F):
                    stack.pop()
                elif ((op_code >= 0x10) and(op_code <= 0x1E)):
                    stack.pop() 
                    stack.pop()
                    stack.append(instruction_id)
                elif ((op_code >= 0x1F) and (op_code <= 0x21)): 
                    stack.pop()
                    stack.append(instruction_id)
                elif (op_code == 0x22):
                    varin = instruction.operands[2].value
                    for i in range(varin + 5): 
                        stack.pop()
                elif (op_code == 0x23):
                    pass
                    
                elif (op_code == 0x24):
                    varin = instruction.operands[0].value
                    
                elif (op_code == 0x25):
                      stack.append(instruction_id)
                      stack.append(instruction_id)
                      stack.append(instruction_id)
                      stack.append(instruction_id)
                      stack.append(instruction_id)
                elif (op_code == 0x27):
                    count = instruction.operands[0].value
                    for i in range(count):
                        stack.pop()
        except Exception as err:
            print("WARNING: Something unexpected happening at address ", hex(instruction.addr))
            #print(err, traceback.format_exc())
                
    def add_var_to_stack(self, instruction, stack)->str:
        result = ""
        if len(stack)-1 not in self.variables_names:
            self.variables_names[len(stack)-1] = "VAR_" + str(len(stack)-1)
            output = self.variables_names[len(stack)-1]
        else:
            #The variable already exists, it can also happen in a push, in that case it becomes a SetVar
            output = self.variables_names[len(stack)-1]

        if (instruction.op_code == 5):
            index_referred = int((len(stack)) + instruction.operands[0].value/4 - 1)
            input = output
            output = self.variables_names[index_referred]
            result = "SetVarToAnotherVarValue(\""+ output + "\", input=\"" + input + "\")"
        elif (instruction.op_code == 6):
            index_referred = int((len(stack)) + instruction.operands[0].value/4 - 1)
            index_str = self.variables_names[index_referred]
            top_of_the_stack = self.variables_names[len(stack) - 1]
            result = "WriteAtIndex(\""+ top_of_the_stack + "\", index=\"" + index_str + "\")"
   
        return result


    def get_expression_str(self, instructions, instr_id, stack)->str:#from the first operand to the last operator if any
        result = ""
        parameters_str = []
        i = instr_id
        copy_stack = stack.copy()
        checkpoint = instr_id
        checkpoint_str = 0
        stack_checkpoint = copy_stack.copy()
        counter_exp = 0
        while i < len(instructions):
            instruction = instructions[i]
            op_code = instruction.op_code 
            if (op_code == 0):
                counter_exp = counter_exp + 1
                parameters_str.append(self.wrap_conversion(instruction.operands[0].value)) 
            elif (op_code == 2): 
                counter_exp = counter_exp + 1
                
                idx = int(len(copy_stack) + instruction.operands[0].value/4)
                variable_name = self.variables_names[idx]
                parameters_str.append("LoadVar(\""+ variable_name + "\")")
            elif (op_code == 3): 
                counter_exp = counter_exp + 1
                idx = int(len(copy_stack) + instruction.operands[0].value/4)
                variable_name = self.variables_names[idx]
                parameters_str.append("LoadVar2(\""+ variable_name + "\")")
            elif (op_code == 4): 
                counter_exp = counter_exp + 1
                parameters_str.append("LoadInt("+ str(instruction.operands[0].value) + ")")
            elif (op_code == 5): 
                break
            elif (op_code == 6): 
                break
            elif (op_code == 7): 
                counter_exp = counter_exp + 1
                parameters_str.append("Load32("+ str(instruction.operands[0].value) + ")")
            elif (op_code == 8): 
                break
            elif (op_code == 9): 
                counter_exp = counter_exp + 1
                parameters_str.append("LoadResult("+ str(instruction.operands[0].value) + ")")
            elif (op_code == 0x0A): 
                break
            elif (op_code == 0x0D): 
                break
            elif (op_code == 0x0C): #why call another function before the parameters were all pushed... if that happens, fuck
                break
            elif (op_code == 0x0E): 
                break
            elif (op_code == 0x0F): 
                break
            elif ((op_code >= 0x10) and(op_code <= 0x1E)):#Operations with two operands: the two are discarded and one (the result) is pushed => overall we popped one
                counter_exp = counter_exp - 1
                lowercase_name = instruction.name.lower()
                param_count = len(parameters_str)
    
                idx_top = len(copy_stack) - 1
                idx_top2 = len(copy_stack) - 2
    
                if len(parameters_str) == 0:
                    counter_exp = counter_exp + 1
                    variable_name_right = self.variables_names[idx_top]
                    
                    right = "TopVar(\"" + variable_name_right + "\")"
                else:
                    right = parameters_str[param_count - 1]
                    parameters_str.pop()
    
                if len(parameters_str) == 0: 
                    counter_exp = counter_exp + 1
                    variable_name_left = self.variables_names[idx_top2]
                    left = "TopVar(\"" + variable_name_left + "\")"
                else:
                    left = parameters_str[param_count - 2]
                    parameters_str.pop()
                full_instr_str = lowercase_name + "(" + left + ", " + right + ")"
                parameters_str.append(full_instr_str)
                
                
            elif ((op_code >= 0x1F) and (op_code <= 0x21)): #A single operand popped and the result is pushed => nothing changes in terms of stack occupation
                
                lowercase_name = instruction.name.lower()
                param_count = len(parameters_str)
                idx_top = len(copy_stack) - 1
                if len(parameters_str) == 0: 
                    counter_exp = counter_exp + 1
                    variable_name = self.variables_names[idx_top]
                    value = "TopVar(\"" + variable_name + "\")" 
                else:
                    value = parameters_str[param_count - 1]
                    parameters_str.pop()
                
                full_instr_str = lowercase_name + "(" + value + ")"
                parameters_str.append(full_instr_str)
    
                
    
            elif ((op_code == 0x22) or (op_code == 0x23) or (op_code == 0x24)): #For the same reason a regular call shouldn't happen here
                break
            elif (op_code == 0x25): #adds the return address and the current function address to the stack
                break
            elif (op_code == 0x27): 
                break
    
            self.update_stack(instruction, copy_stack, i)
            if counter_exp == 1:
                checkpoint = i
                checkpoint_str = len(parameters_str) - 1
                stack_checkpoint = copy_stack.copy()

            i = i + 1
    
        for j in range(checkpoint_str, len(parameters_str) - 1):
            parameters_str.pop()
    
        for parameter_str in parameters_str:
            result = result + parameter_str + ", "  
        if len(result) > 0:
            result = result[:-2]
        
        if len(stack_checkpoint)-1 not in self.variables_names.keys():
            self.variables_names[len(stack_checkpoint)-1] = "VAR_" + str(len(stack_checkpoint)-1)
            output = self.variables_names[len(stack_checkpoint)-1]
        else:
            output = self.variables_names[len(stack_checkpoint)-1]
        return ("AssignVar(" + "\"" + output + "\", " + result + ")", checkpoint - instr_id)
    
    def get_instruction_number_for_expression(self, instructions, start)->int:
        result = ""
        parameters_str = []
        i = start
        expected_operands = 1
        while expected_operands > 0:
            instruction = instructions[i]
            op_code = instruction.op_code 
            if (op_code == 0):
                expected_operands = expected_operands - 1
            elif (op_code == 2):  
                expected_operands = expected_operands - 1
            elif (op_code == 3):  
                expected_operands = expected_operands - 1
            elif (op_code == 4): 
                expected_operands = expected_operands - 1
            elif (op_code == 7): 
                expected_operands = expected_operands - 1
            elif (op_code == 9): 
                expected_operands = expected_operands - 1
            
            elif ((op_code >= 0x10) and(op_code <= 0x1E)):#Operations with two operands: the two are discarded and one (the result) is pushed => overall we popped one
                expected_operands = expected_operands - 1 + 2
                
            elif ((op_code >= 0x1F) and (op_code <= 0x21)): #A single operand popped and the result is pushed => nothing changes in terms of stack occupation
                pass
            
            elif (op_code == 0x26): 
                pass
            else: 
                break
            i = i - 1
        
        return start - i
    
    def get_param_str_from_instructions(self, instructions, start, end)->str:
        result = ""
        parameters_str = []
        for i in range(start, end + 1):
            instruction = instructions[i]
            op_code = instruction.op_code 
            
            if (op_code == 0):
                parameters_str.append(self.wrap_conversion(instruction.operands[0].value)) 
            elif (op_code == 2): 
                stack = self.instructions_stacks[i]
                idx = int(len(stack) + instruction.operands[0].value/4)
                variable_name = self.variables_names[idx]
                parameters_str.append("LoadVar(\""+ variable_name + "\")")
            elif (op_code == 3): 
                stack = self.instructions_stacks[i]
                idx = int(len(stack) + instruction.operands[0].value/4)
                variable_name = self.variables_names[idx]
                parameters_str.append("LoadVar2(\""+ variable_name + "\")")
            elif (op_code == 4): 
                parameters_str.append("LoadInt("+ str(instruction.operands[0].value) + ")")
            elif (op_code == 5): 
                raise ValueError('Should not happen.') 
            elif (op_code == 6): 
                raise ValueError('Should not happen.')
            elif (op_code == 7): 
                parameters_str.append("Load32("+ str(instruction.operands[0].value) + ")")
            elif (op_code == 8): 
                raise ValueError('Should not happen.')
            elif (op_code == 9): 
                parameters_str.append("LoadResult("+ str(instruction.operands[0].value) + ")")
            elif (op_code == 0x0A): 
                raise ValueError('Should not happen.')
            elif (op_code == 0x0D): 
                raise ValueError('Should not happen.')
            elif (op_code == 0x0C): #why call another function before the parameters were all pushed... if that happens, fuck
                raise ValueError('Should not happen.')
            elif (op_code == 0x0E): 
                raise ValueError('Should not happen.')
            elif (op_code == 0x0F): 
                raise ValueError('Should not happen.')
            elif ((op_code >= 0x10) and(op_code <= 0x1E)):#Operations with two operands: the two are discarded and one (the result) is pushed => overall we popped one
                lowercase_name = instruction.name.lower()
                param_count = len(parameters_str)
    
                stack = self.instructions_stacks[i]
                idx_top = len(stack) - 1
                idx_top2 = len(stack) - 2
    
                if len(parameters_str) == 0:
                    variable_name_right = self.variables_names[idx_top]
                    
                    right = "TopVar(\"" + variable_name_right + "\")" 
                else:
                    right = parameters_str[param_count - 1]
                    parameters_str.pop()
    
                if len(parameters_str) == 0: 
                    variable_name_left = self.variables_names[idx_top2]
                    left = "TopVar(\"" + variable_name_left + "\")" 
                   
                else:
                    left = parameters_str[param_count - 2]
                    parameters_str.pop()
                full_instr_str = lowercase_name + "(" + left + ", " + right + ")"
                parameters_str.append(full_instr_str)
                
                
            elif ((op_code >= 0x1F) and (op_code <= 0x21)): #A single operand popped and the result is pushed => nothing changes in terms of stack occupation
                lowercase_name = instruction.name.lower()
                param_count = len(parameters_str)
                stack = self.instructions_stacks[i]
                idx_top = len(stack) - 1
                if len(parameters_str) == 0: 
                    variable_name = self.variables_names[idx_top]
                    
                    variable_name = self.variables_names[idx_top]
                    value = "\"" + variable_name + "\""
                else:
                    value = parameters_str[param_count - 1]
                    parameters_str.pop()
                
                full_instr_str = lowercase_name + "(" + value + ")"
                parameters_str.append(full_instr_str)
                
            elif ((op_code == 0x22) or (op_code == 0x23) or (op_code == 0x24)): #For the same reason a regular call shouldn't happen here
                raise ValueError('Should not happen.')
            elif (op_code == 0x25): #adds the return address and the current function address to the stack
                raise ValueError('Should not happen.')
            elif (op_code == 0x27): 
                raise ValueError('Should not happen.')
        parameters_str.reverse()
        for parameter_str in parameters_str:
            result = result + parameter_str + ", "  
        if len(result) > 0:
            result = result[:-2]
        return result 
    
    
    
    def make_function_py_header(self, function)->str:
        result = "#-------------------------\n"
        result = result + "#original file addr: " + str(hex(function.start)) + "\n"
        result = result + "    set_current_function(\""+ function.name + "\")\n"
        for id_strct in range(len(function.structs)):
            result = result + "    add_struct(\n"
            result = result + "\tid = " + str((function.structs[id_strct]["id"]))+",\n"
            result = result + "\tnb_sth1 = " + str(hex(function.structs[id_strct]["nb_sth1"]))+",\n"

            result = result + "\tarray2 = ["
            for id_in in range(len(function.structs[id_strct]["array2"]) - 1):
                result = result + self.wrap_conversion(function.structs[id_strct]["array2"][id_in]) + ", "
            if (len(function.structs[id_strct]["array2"]) != 0):
                result = result + self.wrap_conversion(function.structs[id_strct]["array2"][len(function.structs[id_strct]["array2"])- 1]) 
            result = result + "],\n"

            result = result + "    )\n\n"
        return result

    def disassemble_instructions(self, function)->str:
        result = "#Instructions " + function.name + "\n\n"   
        for instruction in function.instructions:
            if instruction.addr in ED9InstructionsSet.locations_dict:
                result = result + "\n    Label(\""+ED9InstructionsSet.locations_dict[instruction.addr]+"\")\n\n"
            if instruction.op_code == 0x26 and self.markers == False: #Line Marker, we can separate with a new line
                result = result + "\n"
            else:
                result = result + "    " + instruction.to_string(self.stream) + "\n"
        return result

    def disassemble_function(self, function) -> str:

        fun_header = self.make_function_py_header(function)
        instructions = self.disassemble_instructions(function)
        
        return fun_header + instructions

    def decompile_function(self, function) -> str:

        fun_header = self.make_function_py_header(function)
        instructions = self.decompile_instructions(function)
        
        return fun_header + instructions
    
        # Внутри класса ED9Disassembler

    def decompile_instructions(self, function) -> str:
        print(f"          [DEBUG decompile_instructions] *** УПРОЩЕННЫЙ РЕЖИМ *** для {function.name}...") # Отладочный print
        functions = self.script.functions # Может понадобиться для to_string, если он использует имена функций
        result = "#Instructions " + function.name + "\n\n"
        string_list = [] # Список строк для финального вывода

        instruction_id = 0
        max_instructions = len(function.instructions)

        while instruction_id < max_instructions:
            # Проверяем, существует ли инструкция с таким ID (на всякий случай)
            if instruction_id >= len(function.instructions):
                print(f"ОШИБКА: Попытка доступа к инструкции за пределами списка (индекс {instruction_id}) в упрощенном цикле.")
                break

            instruction = function.instructions[instruction_id]
            lines_to_add = [] # Список строк для текущей инструкции (может быть метка + сама инструкция)

            # Добавляем метку, если она есть для этого адреса
            if instruction.addr in ED9InstructionsSet.locations_dict:
                # Добавляем пустую строку перед меткой для читаемости, если список не пуст и последняя строка не пустая
                if string_list and string_list[-1].strip():
                    lines_to_add.append("")
                lines_to_add.append(f"    Label(\"{ED9InstructionsSet.locations_dict[instruction.addr]}\")")
                # Добавляем пустую строку после метки
                lines_to_add.append("")

            # Обрабатываем саму инструкцию
            if instruction.op_code == 0x26 and not self.markers:
                # Пропускаем маркеры строк, если опция отключена
                # Не добавляем ничего в lines_to_add
                pass
            else:
                try:
                     # Добавляем инструкцию с отступом
                     lines_to_add.append("    " + instruction.to_string(self.stream))
                except Exception as to_str_e:
                     print(f"ОШИБКА в instruction.to_string для {hex(instruction.addr)} опкод {hex(instruction.op_code)}: {to_str_e}")
                     lines_to_add.append(f"    # ERROR generating string for op {hex(instruction.op_code)}")

            # Добавляем собранные строки в основной список
            string_list.extend(lines_to_add)

            instruction_id += 1 # Просто инкрементируем ID

        print(f"          [DEBUG decompile_instructions] *** УПРОЩЕННЫЙ РЕЖИМ *** Завершение для {function.name}.")

        # Очищаем лишние пустые строки в конце
        while string_list and not string_list[-1].strip():
             string_list.pop()

        return "\n".join(string_list) + "\n" # Добавляем перенос в конце

    def add_return_addresses(self, function): 
        functions = self.script.functions
        
        #print("NEW FUN: ", str(hex(self.start)))
        stack = [] 
        dict_stacks = {} 
        stack_list = []
        #first we add the input parameters of the function to the stack
        for in_id in range(len(function.input_args)):
            stack.append(-in_id -1)

        instruction_id = 0
        
        while instruction_id < len(function.instructions):
            stack_list.append(stack.copy())
            update_stack_needed = True
            instruction = function.instructions[instruction_id]
            if instruction.addr in ED9InstructionsSet.locations_dict:
                if ED9InstructionsSet.locations_dict[instruction.addr] in self.dict_stacks:
                    stack = self.dict_stacks[ED9InstructionsSet.locations_dict[instruction.addr]]
            if (instruction.op_code == 0x0B):
                if instruction.operands[0].value in self.dict_stacks:
                    pass
                else:
                    self.dict_stacks[instruction.operands[0].value] = stack.copy()
            elif (instruction.op_code == 0x0D):
                if instruction_id != len(function.instructions) - 1:
                    update_stack_needed = False
                    instruction_id = instruction_id + 1
                    instruction = function.instructions[instruction_id]
                    while instruction.addr not in ED9InstructionsSet.locations_dict:
                        instruction_id = instruction_id + 1
                        if instruction_id > len(function.instructions) - 1:
                            break
                        instruction = function.instructions[instruction_id]
                    
            elif (instruction.op_code == 0x0E): 
                if instruction.operands[0].value in self.dict_stacks:
                    pass
                else:
                    self.dict_stacks[instruction.operands[0].value] = stack.copy()
                    self.dict_stacks[instruction.operands[0].value].pop()
            elif (instruction.op_code == 0x0F):
                if instruction.operands[0].value in self.dict_stacks:
                    pass
                else:
                    self.dict_stacks[instruction.operands[0].value] = stack.copy()
                    self.dict_stacks[instruction.operands[0].value].pop()
            elif instruction.op_code == 0x0C: #Found a function call
                #We now attempt to find all the input parameters of the function and identify the return address (which should be pushed right before them)
                index_fun = instruction.operands[0].value
                called_fun = functions[index_fun]
                #instruction.operands[0] = ED9InstructionsSet.operand(functions[instruction.operands[0].value].name, False) 
                varin = len(called_fun.input_args)
                
                starting_instruction_id = stack[len(stack) -1 - varin]
                last_instruction = function.instructions[starting_instruction_id]
                
                
                function.instructions[starting_instruction_id].name = "PUSHRETURNADDRESS"
                addr = last_instruction.operands[0].value
                if addr in ED9InstructionsSet.locations_dict:
                    label = ED9InstructionsSet.locations_dict[addr]
                else:
                    label = "Loc_"+ str(ED9InstructionsSet.location_counter)
                    ED9InstructionsSet.locations_dict[addr] = label
                    ED9InstructionsSet.location_counter = ED9InstructionsSet.location_counter + 1
                function.instructions[starting_instruction_id].operands[0] = ED9InstructionsSet.operand(label, False)
                #The previous instruction is likely where the call really starts, it pushes a small unsigned integer (maybe some kind of stack size allocated for the called function?)
                function.instructions[starting_instruction_id - 1].text_before = "#Calling " + called_fun.name + "\n    "
                function.instructions[starting_instruction_id - 1].name = "PUSHCALLERFUNCTIONINDEX"
                function.instructions[starting_instruction_id - 1].operands.clear()# = ED9InstructionsSet.operand(functions[function.instructions[starting_instruction_id - 1].operands[0].value].name, False)
            elif instruction.op_code == 0x23:
                varin = instruction.operands[2].value
                
                if (function.instructions[instruction_id - 1 - varin].op_code == 1):
                    stack = stack_list[instruction_id - 1 - varin]

            elif instruction.op_code == 0x25: 
               addr = instruction.operands[0].value
               if addr in ED9InstructionsSet.locations_dict:
                   label = ED9InstructionsSet.locations_dict[addr]
               else:
                   label = "Loc_"+ str(ED9InstructionsSet.location_counter)
                   ED9InstructionsSet.locations_dict[addr] = label
                   ED9InstructionsSet.location_counter = ED9InstructionsSet.location_counter + 1
               instruction.operands[0] = ED9InstructionsSet.operand(label, False)
               #The previous instruction is likely where the call really starts, it pushes a small unsigned integer (maybe some kind of stack size allocated for the called function?)
            if (update_stack_needed):
                self.update_stack(instruction, stack, instruction_id)
                instruction_id = instruction_id + 1

            if instruction.op_code == 0x0C: #If there was a call, the operand becomes the name of the function rather than the index; should actually be in another function coming after this one
                index_fun = instruction.operands[0].value
                called_fun = functions[index_fun]
                instruction.operands[0] = ED9InstructionsSet.operand(functions[instruction.operands[0].value].name, False) 
                

    def wrap_conversion(self, value: int)->str:
        removeLSB = value & 0xC0000000
        actual_value = remove2MSB(value)
        MSB = removeLSB >> 0x1E
        if (MSB == 3):
            return "\"" + readtextoffset(self.stream, actual_value).replace("\n", "\\n") + "\"" 
        elif (MSB == 2):
            actual_value = actual_value << 2 
            bytes = struct.pack("<i",actual_value)
            return "FLOAT(" + str(struct.unpack("<f", bytes)[0]) + ")"
        elif (MSB == 1):
            return "INT(" + str((int(actual_value))) + ")"
        else:
            return "UNDEF(" + str(hex(int(actual_value))) + ")"

def find_start_function_call(instructions, instruction_id, varin)->int:
    counter_in = varin
    instruction_counter = -1
    while(counter_in > 0):
        current_instruction = instructions[instruction_id + instruction_counter]
        op_code = current_instruction.op_code
        if (op_code == 0):
            counter_in = counter_in - 1 
        elif (op_code == 1):
            popped_els = current_instruction.operands[0].value/4
            counter_in = counter_in + popped_els
        elif (op_code == 2): 
            counter_in = counter_in - 1
        elif (op_code == 3):  
            counter_in = counter_in - 1
        elif (op_code == 4):  
            counter_in = counter_in - 1
        elif (op_code == 5):  
            counter_in = counter_in + 1
        elif (op_code == 6): 
            counter_in = counter_in + 1
        elif (op_code == 7): 
            counter_in = counter_in - 1
        elif (op_code == 8): 
            counter_in = counter_in + 1
        elif (op_code == 9): 
            counter_in = counter_in - 1
        elif (op_code == 0x0A): 
            counter_in = counter_in + 1
        elif (op_code == 0x0D): 
            break
        elif (op_code == 0x0C): #why call another function before the parameters were all pushed... if that happens, fuck
            break
        elif (op_code == 0x0E): 
            counter_in = counter_in + 1
        elif (op_code == 0x0F): 
            counter_in = counter_in + 1
        elif ((op_code >= 0x10) and(op_code <= 0x1E)):#Operations with two operands: the two are discarded and one (the result) is pushed => overall we popped one
            counter_in = counter_in + 1
        elif ((op_code >= 0x1F) and (op_code <= 0x21)): #A single operand popped and the result is pushed => nothing changes in terms of stack occupation
            counter_in = counter_in + 1 - 1
        elif ((op_code == 0x22) or (op_code == 0x23) or (op_code == 0x24)): #For the same reason a regular call shouldn't happen here
           break
        elif (op_code == 0x25): 
            counter_in = counter_in - 1
            counter_in = counter_in - 1
            counter_in = counter_in - 1
            counter_in = counter_in - 1
            counter_in = counter_in - 1
        elif (op_code == 0x27): 
            count = current_instruction.operands[0].value
            for i in range(count):
                counter_in = counter_in + 1
        instruction_counter = instruction_counter - 1

    if (instruction_id + instruction_counter == -1):
        return (instruction_counter + 1, counter_in)
    current_instruction = instructions[instruction_id + instruction_counter]
    while(current_instruction.op_code == 0x26):
        instruction_counter = instruction_counter - 1
        current_instruction = instructions[instruction_id + instruction_counter]
    
    return (instruction_counter + 1, counter_in)