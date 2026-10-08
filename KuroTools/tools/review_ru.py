# -*- coding: utf-8 -*-
"""Ревью карт перевода: охват, целостность, длина, термины, дубли.

Только чтение — ничего не пишет в `translation_map/`. Отчёт печатается в
stdout и (если задан `--report`) в файл.

    python tools/review_ru.py                        # обе карты, кратко
    python tools/review_ru.py --kind script --top 40
    python tools/review_ru.py --report tools/_review.txt

Разделы:

  ОХВАТ      — сколько строк ещё без перевода и почему; строки без причины
               (значит, видимые игроку) перечисляются отдельно. Это сторож,
               который ловит ловушки классификатора: раньше из-за среза по
               полноширинным «！»/«？» и правила «встречается в 5+ файлах»
               из волн выпадали настоящие реплики и кнопки меню.
  ЦЕЛОСТНОСТЬ — то, что ломает игру: порядок/парность тегов, спецификаторы
               формата (%s, %d), руби, escape-последовательности, настоящие
               переносы строк и TAB, полноширинные символы в переводе.
  ДЛИНА      — переводы, которые втрое и более длиннее японского текста;
               отдельно — короткие строки (в UI они сжимаются сильнее всего).
  ТЕРМИНЫ    — одни и те же японские термины и имена, переведённые по-разному.
  ДУБЛИ      — один и тот же русский текст у разных японских строк (следы
               копипасты и следствия склейки половин реплик).
"""
import argparse
import collections
import io
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

MAP_FILES = {"table": "tables.jsonl", "script": "scripts.jsonl"}

TAG = re.compile(r"<[^<>]{1,120}>")
RUBY = re.compile(r"<R>(.*?)</R([^<>]*)>")
# `<KW KEYWORD_ID_X 0 日本語>` — обращение к словарю ключевых слов. Текст
# подстановки внутри тега копируется и переводится свободно: сборка с
# переведённым полем уже проверена в игре и работает (см. `t_npc_c0010.tbl`
# в собранном `json_to_tbl/`), поэтому при сравнении тегов это поле
# отбрасывается — иначе каждая такая строка выглядит «сломанной».
KW = re.compile(r"^<KW\s+(\S+)\s+\S+[^<>]*>$")
JP = re.compile(r"[\u3040-\u309f\u30a0-\u30ff\u4e00-\u9fff]")
# японская буква (в отличие от пунктуации: ・ 、 。 ー ！ ？ и т.п.)
JP_LETTER = re.compile(r"[\u3041-\u3096\u309d-\u309f\u30a1-\u30fa"
                       r"\u30fc-\u30ff\u4e00-\u9fff]")
# руби-чтение — исключение из сравнения тегов: оно обязано быть
# транслитерировано, поэтому «</Rなきり>» и «</Rнакири>» — это ОДИН тег
RUBY_CLOSE = re.compile(r"</R[^<>]*>")


def norm_tag(t):
    """Канонический вид тега для сравнения японской и русской строк.

    Руби-чтение обязано быть транслитерировано, а подпись внутри `<KW>` —
    свободный текст: обе части в сравнении не участвуют.
    """
    if RUBY_CLOSE.fullmatch(t):
        return "</R>"
    m = KW.match(t)
    if m:
        return "<KW %s>" % m.group(1)
    return t
# полиоширинная пунктуация, которую в русском тексте видеть нормально:
# «～» — знак протяжности, «。”«» — кавычки и точки
FULLW_OK = "～・…。、“”「」『』〈〉《》"
KANA = re.compile(r"^[\u3040-\u309f\u30a0-\u30ff\u30fc\u3000\s]+$")
FULLW = re.compile(r"[\uff01-\uff5e]")
FMT = re.compile(r"%[0-9.\-+]*[sdiufxX%]")
LATIN = re.compile(r"[A-Za-z]{4,}")

# Служебные строки скриптов: игрок их не видит, переводить не надо.
SVC_FILE = re.compile(r"^(ai_|mon\d|chr\d|chrx\d|common\.|etc\d|btlshoot|sound\."
                      r"|obj_break|system\.|ev_mes|sys_battle|sys_campmenu|"
                      r"mon_empty|chr_templete)")
SVC_TEXT = re.compile(
    r"(Ｍ_|M_[A-Z_]|ＡＤＶ|CUTIN|不正|失敗|未作成|未入力|確認して|してください"
    r"|設置|カット|デバッグ|エフェクト|モーション|ボーン|座標|ポリゴン|テクスチャ"
    r"|アニメーション|初期化|非表示|効果音|ボイス|特殊身長|ウィンドウ|ダイアログ"
    r"|コマンド|判定|起動|エラー|警告|実装中|解禁|上書き|デフォ|挙動未確認"
    r"|スロット|キャンセル|ノックダウン|ダメージ|スタン|ジャンプ|ワープ|待機"
    r"|追跡|観察|後退|歩き|走り|死亡|旋回|回転|打ち上げ|射撃|回避|ヒット"
    r"|実習|階層|章間|チュートリアル|演出|告知|リージョン|ボス|ギミック|フラグ"
    r"|スキップ|です$|ます$|選んだ$|存在しません|指定して下さい|描画レイヤー"
    r"|距離|落下|着地|出現|上昇|接近|移動|高さ|近く|から$|[+＋*＊]{3,}|：[^ ]*$)")
SVC_TABLE = re.compile(
    r"(^テスト|^◆|^DEBUG|^カット[0-9０-９]|名前演出|地名演出|タイトル演出"
    r"|エフェクト文字|エフェクトメッセージ|話者名非表示|//選択肢メニュー"
    r"|^カメラ|キャラ部屋|エネミー部屋|浅沼部屋)")


def load(path):
    rows = []
    with io.open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def ru(row):
    return (row.get("ru_text") or "").strip()


# ---------------------------------------------------------------- разделы
def sec_scope(rows, kind, out):
    out("== ОХВАТ (%s)" % kind)
    no_ru = [r for r in rows if not ru(r)]
    out("  строк без перевода: %d из %d" % (len(no_ru), len(rows)))
    svc = SVC_TABLE if kind == "table" else SVC_TEXT
    # сколько РАЗНЫХ файлов содержит строку: это самый надёжный признак
    # библиотечного сообщения движка (компилятор вставляет его во все .dat)
    spread = collections.defaultdict(set)
    for r in rows:
        spread[r["jp_text"]].add(r["file"])
    rest, svc_n = [], collections.Counter()
    for r in no_ru:
        t = r["jp_text"]
        if not JP.search(t) or KANA.match(t):
            svc_n["не текст (формат/число/только кана)"] += 1
            continue
        if r.get("key_prefix"):
            svc_n["команда движка (key_prefix)"] += 1
            continue
        if kind == "script" and SVC_FILE.match(os.path.basename(r["file"])):
            svc_n["служебный файл (метки анимаций/ИИ)"] += 1
            continue
        if svc.search(t):
            svc_n["служебное по шаблону"] += 1
            continue
        if kind == "script" and len(spread[t]) >= 5:
            svc_n["библиотечное сообщение (5+ файлов)"] += 1
            continue
        rest.append(r)
    for k, v in svc_n.most_common():
        out("    служебное · %-34s %d" % (k, v))
    out("    БЕЗ ПРИЧИНЫ (проверить вручную): %d" % len(rest))
    by_file = collections.Counter(os.path.basename(r["file"]) for r in rest)
    for f, n in by_file.most_common(12):
        out("      %-24s %d" % (f, n))
    for r in rest[:15]:
        out("      %-24s %r" % (os.path.basename(r["file"]), r["jp_text"][:60]))
    return rest


def sec_integrity(rows, kind, out):
    out("== ЦЕЛОСТНОСТЬ (%s)" % kind)
    bad = collections.Counter()
    ex = collections.defaultdict(list)

    def note(name, r, detail=""):
        bad[name] += 1
        if len(ex[name]) < 6:
            ex[name].append("%s | %s | jp=%r"
                            % (r["file"].split("/")[-1], detail,
                               r["jp_text"][:40]))

    for r in rows:
        if not ru(r):
            continue
        jp, rru = r["jp_text"], ru(r)
        tags_jp = [norm_tag(t) for t in TAG.findall(jp)]
        tags_ru = [norm_tag(t) for t in TAG.findall(rru)]
        if tags_jp != tags_ru:
            if sorted(tags_jp) != sorted(tags_ru):
                note("теги: СОСТАВ (потеряны/лишние)", r,
                     "%r -> %r" % (tags_jp[:4], tags_ru[:4]))
            else:
                note("теги: ПОРЯДОК изменён — риск, проверить", r,
                     "%r -> %r" % (tags_jp[:4], tags_ru[:4]))
        if FMT.findall(jp) or FMT.findall(rru):
            if FMT.findall(jp) and not FMT.findall(rru):
                note("потерян %s", r, "%r" % FMT.findall(jp))
        if jp.count("<R>") != rru.count("<R>") or jp.count("</R") != rru.count("</R"):
            note("руби: структура", r)
        for _b, reading in RUBY.findall(rru):
            if JP.search(reading):
                note("руби: чтение не транслитерировано", r, repr(reading))
        if "\n" in rru and "\n" not in jp:
            note("добавлен перенос строки (обычно намеренно)", r)
        if "\t" in rru and "\t" not in jp:
            note("настоящий TAB в переводе", r)
        if "\\n" in rru and "\\n" not in jp:
            note("литеральный \\\\n", r)
        bad_full = [c for c in FULLW.findall(rru) if c not in FULLW_OK]
        if bad_full:
            note("полноширинные буквы/цифры в переводе", r,
                 "%r %r" % ("".join(bad_full[:6]), rru[:34]))
        # Японские буквы ищем вне тегов: внутри `<KW … 0 日本語>` подпись
        # остаётся японской по правилу §2.2 брифа и это не ошибка перевода.
        if JP_LETTER.search(TAG.sub("", rru)):
            note("японские БУКВЫ остались в переводе", r, repr(rru[:40]))
        # Кавычки: эталон — японская строка. Реплики нарочно разрезаны так,
        # что открывающая кавычка в одной строке, а закрывающая в другой
        # (`レイは『<C3>` / `</C>』を読んだ`), поэтому «непарность» перевода
        # сравниваем с «непарностью» японского, а не с нулём.
        if (rru.count("«") != rru.count("»")
                and (jp.count("「") + jp.count("『")
                     == jp.count("」") + jp.count("』"))):
            note("непарные « »", r, repr(rru[:40]))
        # Домашний стиль — «„…“»: открывает U+201E, закрывает U+201C.
        # Японский стиль — «“…”»: закрывает U+201D. Поэтому признак
        # невыправленного японского стиля — именно U+201D: символ U+201C
        # есть и в правильной паре, ругаться на него нельзя.
        if "”" in rru:
            note("стиль кавычек: «“…”» вместо «„…“»", r, repr(rru[:40]))
        elif (rru.count("„") != rru.count("“")
                and jp.count("“") == jp.count("”")):
            note("непарные „ “", r, repr(rru[:40]))
        if "\\u3000" in jp and rru.count("\\u3000") != jp.count("\\u3000"):
            note("потерян литеральный \\\\u3000", r)
    if not bad:
        out("  чисто")
    for n, c in bad.most_common():
        out("  %s: %d" % (n, c))
        for d in ex[n]:
            out("      " + d)
    return bad


# Числа и латиница: в японских строках они часто полноширинные
# («５００», «１２年», «Ｅｘｔｒｅｍｅ»), поэтому перед сравнением они
# приводятся к ASCII — иначе полноширинное «Ｅｘｔｒｅｍｅ» не считается
# признаком того, что латиница в переводе уместна.
_HALF = ("0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
         "-,.%()<>[]!?:;/")
_FULL = ("０１２３４５６７８９ＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺ"
         "ａｂｃｄｅｆｇｈｉｊｋｌｍｎｏｐｑｒｓｔｕｖｗｘｙｚ"
         "－，．％（）＜＞［］！？：；／")
FW_ASCII = str.maketrans(_FULL, _HALF)
NUM = re.compile(r"[0-9]+(?:\.[0-9]+)?")
# Латинские слова, которые в этом переводе оставлены намеренно (бренды).
LATIN_OK = {"Xiphone", "LinoN", "Hello", "OK", "HP", "MP", "EXP", "TIPS",
            "SP", "ATK", "DEF", "RPG", "Zodiac", "Nemesis", "Aegis", "BGM",
            "CG", "DLC", "NPC", "HP/MP"}


# Кандзи-числительные: «十段» = 10-й дан, «伍万» = 50 000. Если число
# перевода получается из такого кандзи, это не выдуманное число.
KANJI_NUM = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6,
             "七": 7, "八": 8, "九": 9, "十": 10, "百": 100, "千": 1000,
             "万": 10000, "伍": 5, "零": 0, "壱": 1, "弐": 2, "参": 3}


def merge_thousands(s):
    """Склеивает разделители разрядов: «5,000», «10 000» → «5000», «10000»."""
    prev = None
    while prev != s:
        prev = s
        s = re.sub(r"(?<=\d)[,\u00a0 ](?=\d{3}(?!\d))", "", s)
    return s


def nums_of(text):
    """Все числа строки в ASCII-виде (с склеенными разрядами)."""
    return NUM.findall(merge_thousands(text.translate(FW_ASCII)))


def digits_of(text):
    """Только цифры строки — без разделителей разрядов («10 000» → «10000»)."""
    return re.sub(r"\D", "", text.translate(FW_ASCII))


def _scaled(a, b):
    """«50» — это «5» с другим разрядом (японское 万 = ×10 000).

    Применяется только к лишним числам перевода, чтобы не ругаться на
    «5 万円» → «50 тысяч иен»: цифры без хвостовых нулей совпадают.
    """
    a2, b2 = a.rstrip("0"), b.rstrip("0")
    return a2 != "" and a2 == b2


def sec_suspect(rows, kind, out, top=25):
    """Механические признаки возможной неверности перевода или потери.

    Это только подозрения для ручной вычитки, но сигналы очень урожайные:
    потерянное число, оборванный перевод, забытая латиница, пропавшая
    единица измерения/счётчик.
    """
    out("== ПОДОЗРЕНИЯ (%s)" % kind)
    num_lost, num_extra, short, latin = [], [], [], []
    for r in rows:
        if not ru(r):
            continue
        jp, rru = r["jp_text"], ru(r)
        jp_plain, ru_plain = TAG.sub("", jp), TAG.sub("", rru)
        if not JP.search(jp_plain):
            continue
        jp_ascii = jp_plain.translate(FW_ASCII)
        # Даты переформатируются («９/２１» → «21.09») — числа в них не сверяем.
        is_date = bool(re.search(r"\d\s*/\s*\d", jp_ascii))
        jn, rn = nums_of(jp_plain), nums_of(ru_plain)
        rd = digits_of(ru_plain)
        # В живой речи числа свободно пишутся словами («больше ста видов»,
        # «после тридцати»), поэтому проверяем только те, что почти никогда
        # не разворачивают в слова: годы, цены, крупные счётчики (≥ 3 цифр).
        multi_j = [n for n in jn if len(digits_of(n)) >= 3]
        multi_r = [n for n in rn if len(digits_of(n)) >= 3]
        lost = [n for n in multi_j if digits_of(n) not in rd]
        if not is_date and (lost or len(multi_r) < len(multi_j)):
            num_lost.append((lost or "%d→%d" % (len(multi_j), len(multi_r)), r))
        extra = [n for n in multi_r
                 if digits_of(n) not in digits_of(jp_plain)  # noqa: E501
                 and not any(_scaled(digits_of(n), digits_of(j)) for j in jn)
                 and not any(int(digits_of(n)) == v
                             for c, v in KANJI_NUM.items() if c in jp_plain)]
        if not is_date and extra:
            num_extra.append((extra, r))
        if len(jp_plain) >= 10 and len(ru_plain) < len(jp_plain) * 0.45:
            short.append((len(ru_plain) / len(jp_plain), r))
        for w in LATIN.findall(ru_plain):
            if w not in LATIN_OK and not LATIN.search(jp_ascii):
                latin.append((w, r))
                break

    groups = [("потеряно число из японского", num_lost),
              ("число в переводе, которого нет в японском", num_extra),
              ("перевод подозрительно короткий (обрыв?)", short),
              ("латиница в переводе без основы в японском", latin)]
    for name, items in groups:
        out("  %s: %d" % (name, len(items)))
        for tag, r in items[:top]:
            out("     %-24s %-12r jp=%r"
                % (os.path.basename(r["file"]), str(tag),
                   r["jp_text"][:44]))
            out("     %-24s %-12s ru=%r" % ("", "", ru(r)[:64]))


def sec_length(rows, kind, out, top):
    out("== ДЛИНА (%s)" % kind)
    items = []
    for r in rows:
        if not ru(r):
            continue
        jp, rru = r["jp_text"], ru(r)
        if len(jp) < 4:
            continue
        items.append((len(rru) / max(1, len(jp)), len(jp), len(rru), r))
    big = [it for it in items if it[2] > max(40, it[1] * 3)]
    out("  перевод втрое длиннее: %d из %d" % (len(big), len(items)))
    short = sorted((it for it in items if it[1] <= 18), key=lambda it: -it[2])
    out("  --- самые длинные переводы коротких строк (риск сжатия в UI) ---")
    for ratio, lj, lr, r in short[:top]:
        out("    %3d→%3d (%4.1fx) %-22s %r"
            % (lj, lr, ratio, os.path.basename(r["file"]), ru(r)[:58]))
    out("  --- худшие по отношению ---")
    # key= обязателен: у одинаковых отношений кортежи доходят до словаря,
    # а словари между собой не сравниваются (TypeError).
    for ratio, lj, lr, r in sorted(items, key=lambda it: it[0], reverse=True)[:top]:
        out("    %3d→%3d (%4.1fx) %-22s %r"
            % (lj, lr, ratio, os.path.basename(r["file"]), ru(r)[:50]))


def sec_terms(rows, out, min_hits=4):
    out("== ТЕРМИНЫ: один японский текст — разные переводы")
    variants = collections.defaultdict(collections.Counter)
    for r in rows:
        if ru(r):
            variants[r["jp_text"]][ru(r)] += 1
    multi = [(jp, c) for jp, c in variants.items()
             if len(c) > 1 and sum(c.values()) >= min_hits]
    multi.sort(key=lambda kv: -sum(kv[1].values()))
    out("  строк с расхождениями: %d" % len(multi))
    for jp, c in multi[:30]:
        out("    %r" % jp[:48])
        for v, n in c.most_common(4):
            out("        %2dx %r" % (n, v[:64]))


# Ранее согласованные термины (§5.3 брифа) и их запретные варианты. Проверка
# ловит «дрейф»: один и тот же термин, переведённый по-разному в разных местах.
VARIANTS = [
    ("Рю-сэн → Тацу-сэн", r"Рю[-:：]?[сc]эн(?!сэ)", "Тацу-сэн"),
    ("Рюгу → Тацумия", r"Рюгу", "Тацумия"),
    ("Рю-сэнсэй → учитель Тацумия", r"Рю[-:：]?[сc]энсэ", "учитель Тацумия"),
    ("Фукуми → Фусими", r"Фукуми", "Фусими"),
    ("Фукан → Фусими", r"Фукан", "Фусими"),
    ("Миччин → Миттин", r"Миччин", "Миттин"),
    ("Хэйан-Кё → Хэйан-кё", r"Хэйан-К[ёе]", "Хэйан-кё"),
    ("Найнфайв → Найн-Файв", r"Найнфайв|Найн[ -]фа[йи]в", "Найн-Файв"),
    ("дух-талисман/оружие → духовное снаряжение",
     r"дух[- ]?талисман|дух[- ]?оружие", "духовное снаряжение"),
    ("Тосэки → Акаси", r"Тосэки(?!-)", "Акаси"),
    ("Икай → Иной мир", r"\bИкай", "Иной мир"),
    ("Грид (ед.ч.) в значении мн.ч.", r"\bГрида\b", "проверить падеж"),
    # --- добавлено после волны ревью 08.10.2026 (находки воркеров) ---
    ("「Ускорение души」 → Соул-Аксель", r"Ускорение души", "Соул-Аксель"),
    ("«очки души» → Соул-очки", r"очки души", "Соул-очки"),
    ("кириллическое «АР» → латинское «AP»", r"\bАР\b", "AP"),
    ("гэнсо → фантомные элементы", r"[Гг]энсо", "фантомные элементы"),
    ("дух-талисман → Страж-Гардиан", r"Дух\.?[- ]талисман", "Страж-Гардиан"),
    ("Клеймёный рыцарь → Рыцарь Печати", r"Клеймён\w+ рыцар\w+", "Рыцарь Печати"),
    ("Управление Оммё → Управа Инь-Ян", r"Управлени\w+ Омм[ёе]", "Управа Инь-Ян"),
    ("Кагэюкодзи → Кадэнокодзи", r"Кагэюкодзи", "Кадэнокодзи"),
    ("праздник Амато → Аматодо", r"праздник\w* Амато\b", "праздник Аматодо"),
    ("хозяин местности → Владыка", r"хозяин\w* местности", "Владыка"),
    ("Котоноха → слово/Словарь", r"[Кк]отоноха", "слово / Словарь"),
    ("Хякки Сэнки → Кадзуки Накири", r"Хякки Сэнки", "Кадзуки Накири"),
    ("нестабильная зона → Зона неопределённости",
     r"нестабильн\w+ зон\w+", "Зона неопределённости"),
    ("душевное оружие → Соул-Девайс", r"душевн\w+ оружи\w+", "Соул-Девайс"),
    ("соул-девайс (строчная) → Соул-Девайс",
     r"(?<![А-Яа-яA-Za-z-])[сc]оул-девайс", "Соул-Девайс"),
    ("Катастрофа Оодзина ↔ Бедствие Одзина", r"(Катастрофа Оодзина|Бедствие Одзина)",
     "один вариант"),
    ("Доблесть/Гуманность ↔ Отвага/Милосердие",
     r"(Доблест\w+|Гуманност\w+|Отваг\w+|Милосерди\w+)",
     "один набор трёх добродетелей"),
]


def sec_glossary(rows, out):
    out("== ГЛОССАРИЙ: запрещённые варианты терминов")
    total = 0
    for label, rx, want in VARIANTS:
        hits = [r for r in rows
                if ru(r) and re.search(rx, ru(r))]
        if not hits:
            continue
        total += len(hits)
        out("  %-44s %3d  (нужно: %s)" % (label, len(hits), want))
        seen = set()
        for r in hits:
            if ru(r) in seen:
                continue
            seen.add(ru(r))
            out("        %-20s %r" % (os.path.basename(r["file"]), ru(r)[:62]))
            if len(seen) >= 6:
                break
    if not total:
        out("  чисто")
    return total


def sec_dups(rows, out, limit=400):
    out("== ДУБЛИ: один и тот же русский текст у разных японских строк")
    back = collections.defaultdict(set)
    for r in rows:
        if ru(r) and len(ru(r)) >= 14:
            back[ru(r)].add(r["jp_text"])
    multi = [(v, jps) for v, jps in back.items() if len(jps) > 1]
    multi.sort(key=lambda kv: -len(kv[1]))
    out("  русских строк, повторённых у разных японских: %d" % len(multi))
    for v, jps in multi[:limit][:12]:
        out("    %r" % v[:60])
        for jp in list(jps)[:3]:
            out("        <- %r" % jp[:52])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kind", default="both", choices=["table", "script", "both"])
    ap.add_argument("--top", type=int, default=20)
    ap.add_argument("--report", default=None)
    ap.add_argument("--only", default="",
                    help="охват|целостность|длина|подозрения|термины|дубли")
    args = ap.parse_args()

    buf = []

    def out(s=""):
        print(s)
        buf.append(s)

    kinds = ["table", "script"] if args.kind == "both" else [args.kind]
    for kind in kinds:
        path = os.path.join(ROOT, "translation_map", MAP_FILES[kind])
        rows = load(path)
        out("#" * 64)
        out("# %s — %s, строк %d, переведено %d"
            % (kind, MAP_FILES[kind], len(rows), sum(1 for r in rows if ru(r))))
        out("#" * 64)
        want = args.only
        if not want or want == "охват":
            sec_scope(rows, kind, out)
            out()
        if not want or want == "целостность":
            sec_integrity(rows, kind, out)
            out()
        if not want or want == "длина":
            sec_length(rows, kind, out, args.top)
            out()
        if not want or want == "подозрения":
            sec_suspect(rows, kind, out, args.top)
            out()
        if not want or want == "термины":
            sec_glossary(rows, out)
            out()
            sec_terms(rows, out)
            out()
        if not want or want == "дубли":
            sec_dups(rows, out)
            out()

    if args.report:
        with io.open(args.report, "w", encoding="utf-8", newline="\n") as fh:
            fh.write("\n".join(buf) + "\n")
        print("отчёт: %s" % os.path.relpath(args.report, ROOT))


if __name__ == "__main__":
    main()
