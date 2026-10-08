# -*- coding: utf-8 -*-
"""Проверка состояния кнопок лаунчера без ручного клика.

Запуск: python tools/test_launcher_state.py
Скрипт создаёт окно, прогоняет сценарий «нажали кнопку -> операция закончилась»
и проверяет, что все кнопки снова активны (кроме тех, у кого нет скрипта).
"""
import importlib.util
import os
import sys

TOOLS = os.path.dirname(os.path.abspath(__file__))   # KuroTools/tools
HERE = os.path.dirname(TOOLS)                        # KuroTools
spec = importlib.util.spec_from_file_location("launcher_mod", os.path.join(HERE, "launcher.pyw"))
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

app = mod.App()
app.update()

failures = []


def states():
    return {bid: btn.cget("state") for bid, btn in app.buttons.items()}


def check(cond, msg):
    print(("OK   " if cond else "FAIL ") + msg)
    if not cond:
        failures.append(msg)


wf_ids = [b for b in app.buttons if b.startswith("wf_")]
print("кнопок в панели:", len(app.buttons), "| из них wf_*:", len(wf_ids))

st = states()
check(all(st[b] == "normal" for b in wf_ids if b != "wf_edit_map"),
      "при старте все кнопки «Перевод»/«Сборка» активны")
check(st.get("terminate_button") == "disabled", "«Прервать» выключена, когда ничего не идёт")
check(st.get("wf_all") == "normal", "«Собрать всё» доступна при старте")
check(st.get("wf_build_tbl") == "normal", "«Собрать .tbl» доступна при старте")

# --- сценарий: пользователь нажал кнопку, операция пошла ---
app.is_running = True
app.current_process_pid = 4321
app.disable_all_buttons()
app.update()
st = states()
check(all(v == "disabled" for k, v in st.items() if k != "terminate_button"),
      "во время операции все кнопки, кроме «Прервать», выключены")
check(st.get("terminate_button") == "normal", "во время операции «Прервать» активна")

# --- эмуляция завершения: то же сообщение, что шлёт рабочий поток ---
app.message_queue.put({"type": "output", "data": "— Запуск translation_workflow.py build --what table —"})
app.message_queue.put({"type": "output", "data": "json2tbl: 844 таблиц — пересобрано 1, без изменений 843, ошибок 0"})
app.message_queue.put({"type": "status", "data": "translation_workflow.py завершён успешно."})
app.message_queue.put({"type": "done"})
for _ in range(6):
    app.update()
    app.after(60)
    import time
    time.sleep(0.06)
    app.update()

st = states()
for b in wf_ids:
    check(st[b] == "normal", f"после завершения «{b}» снова активна")
check(st.get("terminate_button") == "disabled", "после завершения «Прервать» снова выключена")
check(st.get("pac_pack") == "normal", "старые инструменты (pac_pack) тоже активны")

# --- повторный прогон: главный баг был «после ВТОРОГО раза уже не оживают» ---
for round_no in (2, 3):
    app.is_running = True
    app.disable_all_buttons()
    app.message_queue.put({"type": "done"})
    for _ in range(4):
        app.update()
        import time
        time.sleep(0.06)
        app.update()
    st = states()
    check(all(st[b] == "normal" for b in wf_ids), f"кнопки активны и после прогона №{round_no}")

# --- проверка выбора архива и разбора значений ---
app.build_what_combo.set("script — скрипты .dat")
check(app.wf_what() == "script", "выбор «script» читается правильно")
app.build_what_combo.set("scene — сцены (без сборки)")
check(app.wf_what() == "scene", "выбор «scene» читается правильно")
app.build_what_combo.set("table — таблицы .tbl")
check(app.wf_what() == "table", "выбор «table» читается правильно")

# --- отсутствие скрипта должно гасить только свою кнопку ---
app._set_button_enabled("pac_pack", False)
check(app.buttons["pac_pack"].cget("state") == "disabled", "кнопка без скрипта гаснет")
app.enable_all_buttons()
check(app.buttons["pac_pack"].cget("state") == "normal", "и включается обратно")

# --- какая кнопка какую команду запускает (через реальный invoke) ---
calls = []
app.run_script_thread = lambda sid, extra_args=None: calls.append((sid, extra_args))
# на всякий случай: операции не должны считаться запуском
app.run_workflow_orig = app.run_workflow

def expect(btn, want, what="table"):
    calls.clear()
    app.build_what_combo.set({"table": "table — таблицы .tbl",
                              "script": "script — скрипты .dat",
                              "scene": "scene — сцены (без сборки)"}[what])
    app.buttons[btn].invoke()
    got = calls[0] if calls else None
    check(got == want, f"кнопка {btn} -> {want} (получено {got})")

expect("wf_all", ("workflow", ["all", "--what", "table"]))
expect("wf_all", ("workflow", ["all", "--what", "script"]), what="script")
expect("wf_all_force",
       ("workflow", ["all", "--what", "table", "--force"]))
expect("wf_build_tbl", ("workflow", ["build", "--what", "table"]))
expect("wf_build_dat", ("workflow", ["build", "--what", "script"]))
expect("wf_apply", ("workflow", ["apply", "--kind", "tbl"]))
expect("wf_prepare", ("workflow", ["prepare"]))
expect("wf_status", ("workflow", ["status"]))
expect("selftest", ("selftest", ["--pac",
       os.path.join(HERE, "pac_packed", "table.pac"),
       "--game", "Kyoto",
       "--work", os.path.join(HERE, "selftest_work")]))

# --- разметка правой панели: одна прокрутка и подписи не обрезаны ---
check(type(app.button_frame).__name__ == "CTkFrame",
      "вся панель без прокрутки (полоса только внутри вкладки)")
scroll = [n for n, f in (("Перевод", app.wf_tf), ("Сборка", app.build_tf),
                         ("Ещё", app.more_tf)) if hasattr(f, "_parent_canvas")]
check(len(scroll) == 3, f"прокрутка только у вкладок: {scroll}")
# Самый плохой случай — окно минимального размера.
app.geometry("1080x720")
app.update()
app.update_idletasks()
for tab_name, frame in (("Перевод", app.wf_tf), ("Сборка", app.build_tf),
                        ("Ещё", app.more_tf)):
    app.tabview.set(tab_name)
    app.update()
    app.update_idletasks()
    clipped = [b for b, btn in app.buttons.items()
               if btn.master is frame and btn.winfo_width() < btn.winfo_reqwidth()]
    check(not clipped, f"вкладка «{tab_name}»: подписи кнопок не обрезаны ({clipped[:3]})")
    full = [btn.winfo_width() for b, btn in app.buttons.items()
            if btn.master is frame and btn.grid_info().get("columnspan") == 2]
    check(full and min(full) >= max(full) - 4,
          f"вкладка «{tab_name}»: кнопки одинаковой полной ширины "
          f"{min(full) if full else '-'}..{max(full) if full else '-'}")
win_bottom = app.winfo_rooty() + app.winfo_height()
for w, wname in ((app.tabview, "вкладки"), (app.terminate_button, "«Прервать»"),
                 (app.author_label, "подпись")):
    check(w.winfo_rooty() + w.winfo_height() <= win_bottom,
          f"{wname} видны целиком (окно минимального размера)")

app.is_running = False
app.destroy()

print()
if failures:
    print(f"ПРОВАЛЕНО: {len(failures)}")
    for f in failures:
        print(" -", f)
    sys.exit(1)
print("ВСЕ ПРОВЕРКИ ПРОШЛИ")
