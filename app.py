
import json
import os
import socket
import subprocess
import sys
import threading
from datetime import datetime, timedelta


def _ensure(import_name, pip_name):
    try:
        __import__(import_name)
    except ImportError:
        print(f"بيتثبت {pip_name} ... استني لحظات")
        subprocess.check_call([sys.executable, "-m", "pip", "install", pip_name])


def _fix_fastapi():
    try:
        from importlib.metadata import version
        major_minor = tuple(int(x) for x in version("fastapi").split(".")[:2])
        if major_minor >= (0, 145):
            print("بيتظبط نسخة FastAPI ... استني لحظات")
            subprocess.check_call([sys.executable, "-m", "pip", "install", "fastapi<0.145"])
    except Exception:
        pass


_ensure("flet", "flet==0.28.3")
_ensure("anthropic", "anthropic")
_fix_fastapi()

import flet as ft
import anthropic

# ---------------- ملفاتك أنتِ (التطبيق بيستدعيها، مش كاتب منطقها من جديد) ----------------
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import air_conditioner as ac_file
import door as door_file
import fire_alarm as fire_file
import TV as tv_file
import wash_machine as wash_file
import lights as lights_file
import Security as security_file
import ai_assistant as ai_file          # المساعد الذكي بتاعك

# >>> سيبيها فاضية لو مش عايزة AI (المساعد المحلي هيشتغل). أو حطي المفتاح هنا <<<
API_KEY = ""

# لو التطبيق شغال على سيرفر (Render / Railway / ...) السيرفر بيحدد البورت لوحده،
# وساعتها مش محتاجين نفق Cloudflare ولا اللاب يكون شغال.
IS_CLOUD = bool(os.environ.get("PORT")) or os.environ.get("RUN_ON_SERVER") == "1"
PORT = int(os.environ.get("PORT", 8550))
KNOWN_PEOPLE = door_file.person          # من door.py
AC_ON_TEMP = ac_file.ON_TEMP             # من air_conditioner.py
FIRE_TEMP = fire_file.TEMP_LIMIT         # من fire_alarm.py
WASH_TYPES = {"normal": "عادي", "quick": "سريع"}

TS_FMT = "%Y-%m-%d %H:%M:%S"
MAX_EVENTS = 500
EVENTS_FILE = os.path.join(os.environ.get("DATA_DIR", os.path.dirname(os.path.abspath(__file__))),
                           "home_events.json")

# ---------------- الأجهزة ----------------
FIRE = "إنذار الحريق"
DOOR = "باب الشقة"
CAMERA = "الكاميرا"
AC = "التكييف"
TV = "التلفزيون"
WASHER = "الغسالة"

devices = {
    "نور الصالة": dict(group="LIGHTS", on=True, on_text="شغال", off_text="مطفي"),
    "نور الأوضة": dict(group="LIGHTS", on=False, on_text="شغال", off_text="مطفي"),
    "نور المطبخ": dict(group="LIGHTS", on=False, on_text="شغال", off_text="مطفي"),
    DOOR: dict(group="SECURITY", on=True, on_text="مقفول", off_text="مفتوح"),
    CAMERA: dict(group="SECURITY", on=True, on_text="شغالة", off_text="مطفية"),
    FIRE: dict(group="SECURITY", on=False, on_text="🔥 شغال", off_text="سليم"),
    AC: dict(group="CLIMATE", on=False, on_text="شغال", off_text="مطفي", value=24,
             fmt=lambda v: f" ({v} درجة)"),
    TV: dict(group="ENTERTAINMENT", on=False, on_text="شغال", off_text="مطفي", value=None,
             fmt=lambda v: f" (قناة {v})"),
    WASHER: dict(group="APPLIANCES", on=False, on_text="شغالة", off_text="مطفية", value=None,
                 fmt=lambda v: f" ({WASH_TYPES.get(v, v)})"),
    "السخان": dict(group="APPLIANCES", on=False, on_text="شغال", off_text="مطفي"),
}
LIGHTS = [n for n, d in devices.items() if d["group"] == "LIGHTS"]

env = {"person": True, "temp": 24, "smoke": False}

# ---------------- سجل الأحداث ----------------
events = []
hooks = {"persist": None, "alert": None}


def now_str():
    return datetime.now().strftime(TS_FMT)


def load_events():
    try:
        with open(EVENTS_FILE, "r", encoding="utf-8") as f:
            events.extend(json.load(f)[-MAX_EVENTS:])
    except Exception:
        pass


def save_events():
    try:
        with open(EVENTS_FILE, "w", encoding="utf-8") as f:
            json.dump(events, f, ensure_ascii=False)
    except Exception:
        pass


def log_event(kind, device, detail, source="يدوي"):
    events.append({"time": now_str(), "kind": kind, "device": device,
                   "detail": detail, "source": source})
    del events[:-MAX_EVENTS]
    save_events()


def state_text(name):
    d = devices[name]
    txt = d["on_text"] if d["on"] else d["off_text"]
    if d["on"] and "fmt" in d and d.get("value") not in (None, ""):
        txt += d["fmt"](d["value"])
    return txt


def set_state(name, on, value=None, source="يدوي"):
    d = devices[name]
    before = (d["on"], d.get("value"))
    d["on"] = on
    if value is not None and "value" in d:
        d["value"] = int(value) if isinstance(d["value"], int) else str(value)
    if before != (d["on"], d.get("value")):
        if name == FIRE:
            detail = "إنذار الحريق اشتغل" if on else "إنذار الحريق اتلغى / رجع سليم"
            log_event("fire_alarm", name, detail, source)
            if on and hooks["alert"]:
                hooks["alert"]("🔥 تنبيه: إنذار الحريق اشتغل!")
        else:
            log_event("device_change", name, state_text(name), source)
            if name == CAMERA and not on and hooks["alert"]:
                hooks["alert"]("⚠️ تنبيه: الكاميرا مطفية!")


def query_events(device=None, kind=None, hours=None, limit=20):
    cutoff = datetime.now() - timedelta(hours=hours) if hours else None
    out = []
    for e in reversed(events):
        if device and device not in e["device"]:
            continue
        if kind and e["kind"] != kind:
            continue
        if cutoff and datetime.strptime(e["time"], TS_FMT) < cutoff:
            continue
        out.append(e)
    return {
        "total_matching": len(out),
        "events_newest_first": out[: int(limit or 20)],
        "note": "" if out else "مفيش أحداث مسجلة بالمواصفات دي",
    }


# ---------------- المساعد الذكي: بيجي من ai_assistant.py ----------------
ai_file.bind(devices, set_state, state_text, query_events, env)


# ---------------- مساعد محلي (من غير AI ومن غير API Key) ----------------
import re as _re


def _norm(t):
    t = t.lower()
    t = _re.sub(r"[\u064B-\u0652\u0640]", "", t)
    for a, b in (("أ", "ا"), ("إ", "ا"), ("آ", "ا"), ("ة", "ه"), ("ى", "ي"), ("ؤ", "و"), ("ئ", "ي")):
        t = t.replace(a, b)
    return t


ALIASES = {
    "نور الصالة": ["صاله"],
    "نور الأوضة": ["اوضه", "غرفه", "نوم"],
    "نور المطبخ": ["مطبخ"],
    DOOR: ["باب"],
    CAMERA: ["كاميرا", "كاميره"],
    FIRE: ["حريق", "انذار"],
    AC: ["تكييف", "تكيف"],
    TV: ["تلفزيون", "تلفاز", "تيفي", "tv"],
    WASHER: ["غساله"],
    "السخان": ["سخان"],
}
ON_WORDS = {"شغل", "شغلي", "ولع", "ولعي", "افتح", "افتحي", "فتح", "فعل"}
OFF_WORDS = {"اطفي", "طفي", "اطفيه", "طفيه", "اطفيها", "طفيها", "اقفل", "اقفلي",
             "اقفله", "قفل", "وقف", "وقفي"}
OPEN_WORDS = {"افتح", "افتحي", "فتح"}


def _fmt_events(res):
    ev = res["events_newest_first"]
    if not ev:
        return "مفيش حاجة مسجلة بالمواصفات دي لسه."
    lines = [f"• {e['time']} - {e['device']}: {e['detail']} ({e['source']})" for e in ev[:6]]
    return f"لقيت {res['total_matching']} حدث، آخرهم:\n" + "\n".join(lines)


def local_assistant(text):
    t = _norm(text)
    words = set(_re.findall(r"\w+", t))
    found = [d for d, ks in ALIASES.items() if any(k in t for k in ks)]
    if not any(d in LIGHTS for d in found) and any(k in t for k in ("انوار", "نور", "لمب")):
        found += LIGHTS
    is_on = bool(words & ON_WORDS)
    is_off = bool(words & OFF_WORDS)

    # 1) أوامر تحكم
    if (is_on or is_off) and found:
        out = []
        nums = _re.findall(r"\d+", t)
        for dev in found:
            if dev == FIRE:
                out.append("🔥 إنذار الحريق بيتحكم فيه الحساس بس.")
            elif dev == DOOR:
                if words & OPEN_WORDS:
                    out.append("🚪 فتح الباب بيتم من كارت الباب بعد ما تكتبي اسمك، مش من الشات.")
                else:
                    set_state(DOOR, True, source="المساعد")
                    out.append("🔒 الباب اتقفل.")
            else:
                on = is_on and not is_off
                value = None
                if on and dev == AC and nums:
                    value = int(nums[0])
                elif on and dev == TV and nums:
                    value = nums[0]
                elif on and dev == WASHER:
                    value = "quick" if "سريع" in t else "normal"
                set_state(dev, on, value, source="المساعد")
                out.append(f"✅ {dev}: {state_text(dev)}")
        return "\n".join(out)

    # 2) أسئلة عن اللي حصل
    if any(k in t for k in ("امتي", "مين", "سجل", "اخر", "حصل", "دخل", "دخول", "تاريخ")):
        kind = None
        if "دخل" in t or "دخول" in t:
            kind = "entry"
        elif "حريق" in t:
            kind = "fire_alarm"
        elif "حركه" in t:
            kind = "motion"
        return _fmt_events(query_events(kind=kind, limit=6))

    # 3) حالة جهاز معين
    if found:
        return "\n".join(f"• {d}: {state_text(d)}" for d in found)

    # 4) حالة البيت كلها
    if any(k in t for k in ("حاله", "البيت", "كله", "شغال", "الوضع")):
        lines = [f"• {n}: {state_text(n)}" for n in devices]
        lines.append(f"• فيه حد في البيت: {'أيوه' if env['person'] else 'لأ'} | الحرارة: {env['temp']}°C")
        if devices[FIRE]["on"]:
            lines.insert(0, "🔥 تنبيه: إنذار الحريق شغال!")
        if not devices[CAMERA]["on"]:
            lines.insert(0, "⚠️ تنبيه: الكاميرا مطفية!")
        return "\n".join(lines)

    if words & {"ازيك", "اهلا", "مرحبا", "هاي", "سلام"}:
        return "أهلاً! 👋 قوليلي تشغلي أو تطفي إيه، أو اسأليني عن حالة البيت."

    return ("مش فاهم قصدك 🤔 جربي مثلاً:\n"
            "• شغل نور الصالة / اطفي التكييف\n"
            "• شغل التكييف 22 / شغل التلفزيون 5\n"
            "• الكاميرا شغاله؟ / حالة البيت\n"
            "• حد دخل البيت امتى؟")


# ---------------- ألوان الواجهة ----------------
BG = "#030308"
CYAN = "#22D3EE"
C_WASH = "#0099FF"
C_LIGHTS = "#E6B800"
C_SECURITY = "#00CC44"
C_AC = "#00B3B3"
C_DOOR = "#E65C00"
C_TV = "#9900CC"
C_FIRE = "#CC0029"
C_AI = "#4B0082"


def build_app(page: ft.Page):
    page.title = "Smart Home Intelligent Home Control"
    page.rtl = False
    page.bgcolor = BG
    page.theme_mode = ft.ThemeMode.DARK
    page.padding = 16
    page.scroll = ft.ScrollMode.AUTO
    page.horizontal_alignment = ft.CrossAxisAlignment.CENTER

    client_holder = {"client": None}
    history = []

    if not events:
        load_events()

    # ---------- أدوات مساعدة ----------
    def snack(msg, color=None):
        page.open(ft.SnackBar(ft.Text(msg), bgcolor=color))

    def show_dialog(title, content, buttons):
        dlg = ft.AlertDialog(modal=True, title=ft.Text(title), content=content)

        def wrap(cb):
            def handler(e):
                page.close(dlg)
                if cb:
                    cb()
            return handler

        dlg.actions = [ft.TextButton(label, on_click=wrap(cb)) for label, cb in buttons]
        page.open(dlg)

    # ---------- مفتاح الـ API ----------
    key_field = ft.TextField(label="Anthropic API Key", password=True, can_reveal_password=True)

    def set_key(key):
        client_holder["client"] = anthropic.Anthropic(api_key=key)

    def save_key():
        key = key_field.value.strip()
        if key:
            try:
                page.client_storage.set("api_key", key)
            except Exception:
                pass
            set_key(key)

    def open_settings(e=None):
        show_dialog("إعدادات الـ AI", key_field, [("حفظ", save_key)])

    # ---------- السجل ----------
    def show_log(e=None):
        lv = ft.ListView(spacing=6, height=380, width=300)
        if not events:
            lv.controls.append(ft.Text("السجل فاضي لسه"))
        for ev in reversed(events[-60:]):
            icon = {"entry": "🚪", "fire_alarm": "🔥", "motion": "🏃", "security": "🔐"}.get(ev["kind"], "🔧")
            lv.controls.append(ft.Text(
                f"{icon} {ev['time']}\n{ev['device']}: {ev['detail']}  ({ev['source']})", size=13))
        show_dialog("سجل أحداث البيت", lv, [("إغلاق", None)])

    # ---------- الكروت ----------
    tiles = {}  # key -> (container, subtitle_text)

    def status_for(key):
        if key == "wash":
            return state_text(WASHER)
        if key == "lights":
            n = sum(1 for l in LIGHTS if devices[l]["on"])
            return f"{n}/{len(LIGHTS)} شغال"
        if key == "security":
            return "📷 " + state_text(CAMERA)
        if key == "ac":
            return state_text(AC)
        if key == "door":
            return state_text(DOOR)
        if key == "tv":
            return state_text(TV)
        if key == "fire":
            return state_text(FIRE)
        return ""

    def refresh_ui():
        for key, (box, sub) in tiles.items():
            if key == "ai":
                continue
            sub.value = status_for(key)
        # تحذيرات بصرية
        sec_box = tiles["security"][0]
        sec_box.bgcolor = C_SECURITY if devices[CAMERA]["on"] else "#E65100"
        fire_box = tiles["fire"][0]
        fire_box.border = ft.border.all(3, "white") if devices[FIRE]["on"] else None
        page.update()

    def make_tile(key, label, icon, color, on_click, height=120, wide=False):
        sub = ft.Text("", size=11, color="#FFFFFFCC", text_align=ft.TextAlign.CENTER)
        if wide:
            content = ft.Row(
                [ft.Icon(icon, size=44, color="white"),
                 ft.Column([ft.Text(label, size=20, weight=ft.FontWeight.BOLD, color="white"), sub],
                           spacing=0, tight=True)],
                alignment=ft.MainAxisAlignment.CENTER, spacing=18)
        else:
            content = ft.Column(
                [ft.Icon(icon, size=44, color="white"),
                 ft.Text(label, size=13, weight=ft.FontWeight.BOLD, color="white",
                         text_align=ft.TextAlign.CENTER),
                 sub],
                alignment=ft.MainAxisAlignment.CENTER,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=4)
        box = ft.Container(content=content, height=height, bgcolor=color, border_radius=26,
                           alignment=ft.alignment.center, ink=True,
                           on_click=lambda e: on_click(), expand=True)
        tiles[key] = (box, sub)
        return box

    # ---------- التكييف ----------
    def ask_ac_temp():
        f = ft.TextField(label="الدرجة الجديدة", keyboard_type=ft.KeyboardType.NUMBER,
                         value=str(devices[AC]["value"]))

        def change():
            try:
                set_state(AC, True, int(f.value), source="يدوي")
                snack(ac_file.changed_message(devices[AC]["value"]))
            except ValueError:
                snack("اكتبي رقم صح للدرجة", "#B71C1C")
            refresh_ui()

        def keep():
            snack(ac_file.keep_message())

        def turn_off():
            set_state(AC, False, source="يدوي")
            refresh_ui()

        show_dialog("التكييف شغال ❄️",
                    ft.Column([ft.Text(f"الدرجة دلوقتي {devices[AC]['value']}°C. تحب تغيّرها؟"), f],
                              tight=True),
                    [("غيّر", change), ("اطفيه", turn_off), ("زي ما هي", keep)])

    def apply_climate():
        if ac_file.decide(env["person"], env["temp"]) == "ON":
            if not devices[AC]["on"]:
                set_state(AC, True, source="تلقائي")
                refresh_ui()
                ask_ac_temp()
        elif devices[AC]["on"]:
            set_state(AC, False, source="تلقائي")
        refresh_ui()

    def ac_tap():
        if devices[AC]["on"]:
            ask_ac_temp()
        else:
            set_state(AC, True, source="يدوي")
            refresh_ui()
            ask_ac_temp()

    # ---------- الحريق ----------
    def apply_fire():
        set_state(FIRE, fire_file.is_on("yes" if env["smoke"] else "no", env["temp"]),
                  source="حساس")
        refresh_ui()

    def fire_tap():
        def set_smoke(v):
            def cb():
                env["smoke"] = v
                smoke_sw.value = v
                apply_fire()
            return cb
        show_dialog("فحص الحريق 🔥",
                    ft.Text(f"فيه دخان؟ (الحرارة الحالية {env['temp']}°C)"),
                    [("أيوه، فيه دخان", set_smoke(True)), ("لأ", set_smoke(False)), ("إلغاء", None)])

    # ---------- الباب ----------
    def door_tap():
        if not devices[DOOR]["on"]:
            set_state(DOOR, True, source="يدوي")
            refresh_ui()
            return
        f = ft.TextField(label="who are you? / مين حضرتك؟", autofocus=True)

        def submit():
            res = door_file.check(f.value, "yes")
            if res["known"]:
                who = res["name"]
                set_state(DOOR, False, source=who)
                log_event("entry", DOOR, f"{who} دخل البيت", "الباب")
                snack(" - ".join(res["messages"]) + " 👋")
            else:
                who = res["name"]
                log_event("security", DOOR, f"شخص غريب حاول يدخل (قال إنه: {who or 'مجهول'})", "الباب")
                snack(res["messages"][0] + " ✋", "#B71C1C")
            refresh_ui()

        show_dialog("باب الشقة 🚪", f, [("دخول", submit), ("إلغاء", None)])

    # ---------- التلفزيون ----------
    def tv_tap():
        if devices[TV]["on"]:
            set_state(TV, False, source="يدوي")
            refresh_ui()
            return
        f = ft.TextField(label="أي قناة تحب تتفرج عليها؟", autofocus=True)

        def go():
            ch = f.value.strip() or "1"
            res = tv_file.turn_on("yes", ch)
            set_state(TV, True, ch, source="يدوي")
            snack(" ".join(res["messages"]))
            refresh_ui()

        show_dialog("تشغيل التلفزيون 📺", f, [("شغّل", go), ("لأ", lambda: snack(tv_file.turn_on("no")["messages"][0]))])

    # ---------- الغسالة ----------
    def wash_tap():
        if devices[WASHER]["on"]:
            set_state(WASHER, False, source="يدوي")
            refresh_ui()
            return
        rg = ft.RadioGroup(
            value="normal",
            content=ft.Column([ft.Radio(value="normal", label="عادي (normal)"),
                               ft.Radio(value="quick", label="سريع (quick)")], tight=True))

        def go():
            res = wash_file.start("yes", rg.value)
            set_state(WASHER, True, rg.value, source="يدوي")
            snack(" - ".join(res["messages"]))
            refresh_ui()

        show_dialog("تشغيل الغسالة 🧺", rg, [("شغّل", go), ("إلغاء", None)])

    # ---------- الأنوار ----------
    def lights_tap():
        col = ft.Column(tight=True)

        def make_sw(n):
            def ch(e):
                set_state(n, e.control.value, source="يدوي")
                refresh_ui()
            return ft.Switch(label=n, value=devices[n]["on"], on_change=ch)

        for n in LIGHTS:
            col.controls.append(make_sw(n))
        show_dialog("الأنوار 💡", col, [("تمام", None)])

    # ---------- الأمان ----------
    def security_tap():
        pw = ft.TextField(label="Please, enter security password", password=True,
                          can_reveal_password=True, keyboard_type=ft.KeyboardType.NUMBER,
                          autofocus=True)

        def submit():
            res = security_file.check(pw.value)
            ok = res["ok"]
            cam_on = devices[CAMERA]["on"]
            cam_txt = "الكاميرا شغالة ✅" if cam_on else "الكاميرا مطفية ⚠️"
            log_event("security", "فحص الأمان",
                      f"الباسورد {'صح' if ok else 'غلط'} - {cam_txt}", "يدوي")
            buttons = [("تمام", None)]
            if not cam_on:
                def cam_start():
                    set_state(CAMERA, True, source="يدوي")
                    snack("الكاميرا اشتغلت ✅")
                    refresh_ui()
                buttons.insert(0, ("شغّل الكاميرا", cam_start))
            show_dialog(res["message"] + (" 🏠" if ok else " ❌"),
                        ft.Text(cam_txt, size=16), buttons)

        show_dialog("فحص الأمان 🔐", pw, [("تأكيد", submit), ("إلغاء", None)])

    # ---------- بناء الشاشة الرئيسية ----------
    header = ft.Row(
        [
            ft.Icon(ft.Icons.HOME_OUTLINED, size=46, color="#E8EEF5"),
            ft.Column(
                [ft.Text("SMART HOME", size=26, weight=ft.FontWeight.W_900, color="white"),
                 ft.Text("INTELLIGENT HOME CONTROL", size=11, weight=ft.FontWeight.BOLD,
                         color="#9CC3E6")],
                spacing=0, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
            ft.IconButton(ft.Icons.SIGNAL_CELLULAR_ALT_ROUNDED, icon_color=CYAN, icon_size=34,
                          tooltip="السجل", on_click=show_log),
        ],
        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )
    divider = ft.Container(height=2, bgcolor=CYAN, margin=ft.margin.only(top=6, bottom=6))

    row1 = ft.Row([
        make_tile("wash", "WASH MACHINE", ft.Icons.LOCAL_LAUNDRY_SERVICE_OUTLINED, C_WASH, wash_tap),
        make_tile("lights", "LIGHTS", ft.Icons.LIGHTBULB_OUTLINE, C_LIGHTS, lights_tap),
        make_tile("security", "SECURITY", ft.Icons.SHIELD_OUTLINED, C_SECURITY, security_tap),
    ], spacing=10)
    row2 = ft.Row([
        make_tile("ac", "AIR CONDITIONER", ft.Icons.AC_UNIT, C_AC, ac_tap),
        make_tile("door", "DOOR ACCESS", ft.Icons.DOOR_FRONT_DOOR_OUTLINED, C_DOOR, door_tap),
        make_tile("tv", "TELEVISION", ft.Icons.TV, C_TV, tv_tap),
    ], spacing=10)
    fire_row = ft.Row([make_tile("fire", "FIRE ALARM", ft.Icons.LOCAL_FIRE_DEPARTMENT_OUTLINED,
                                 C_FIRE, fire_tap, height=130, wide=True)])

    # ---------- الحساسات (للتجربة) ----------
    def lights_question():
        if not any(devices[n]["on"] for n in LIGHTS):
            return

        def keep():
            if lights_file.keep("yes") == "ON":
                snack("الأنوار فضلت شغالة")

        def off():
            if lights_file.keep("no") == "OFF":
                for n in LIGHTS:
                    set_state(n, False, source="تلقائي")
            refresh_ui()

        show_dialog("الأنوار 💡", ft.Text("مفيش حد في البيت. تحب الأنوار تفضل شغالة؟"),
                    [("أيوه سيبها", keep), ("لأ، اطفيها", off)])

    def on_person(e):
        env["person"] = e.control.value
        if lights_file.decide(env["person"]) == "ON":
            set_state(LIGHTS[0], True, source="تلقائي")
            refresh_ui()
            apply_climate()
        else:
            apply_climate()
            lights_question()

    temp_text = ft.Text(f"درجة حرارة البيت: {env['temp']}°C", size=14)

    def on_temp_drag(e):
        temp_text.value = f"درجة حرارة البيت: {int(e.control.value)}°C"
        page.update()

    def on_temp_set(e):
        env["temp"] = int(e.control.value)
        temp_text.value = f"درجة حرارة البيت: {env['temp']}°C"
        apply_fire()
        apply_climate()

    def on_smoke(e):
        env["smoke"] = e.control.value
        apply_fire()

    person_sw = ft.Switch(label="👤 فيه حد في البيت", value=env["person"], on_change=on_person)
    smoke_sw = ft.Switch(label="💨 دخان", value=env["smoke"], on_change=on_smoke)
    temp_slider = ft.Slider(min=15, max=50, divisions=35, value=env["temp"],
                            label="{value}°", on_change=on_temp_drag, on_change_end=on_temp_set)

    def sim_entry(e):
        set_state(DOOR, False, source="حساس")
        log_event("entry", "حساس الحركة", "شخص دخل البيت", "حساس")
        refresh_ui()

    def sim_motion(e):
        log_event("motion", "حساس الحركة", "حركة في الصالة", "حساس")
        snack("اتسجلت حركة في الصالة")

    sensors = ft.ExpansionTile(
        title=ft.Text("الحساسات (للتجربة)", size=13, color="#888888"),
        controls=[
            person_sw, temp_text, temp_slider, smoke_sw,
            ft.Row([ft.OutlinedButton("🚪 دخول شخص", on_click=sim_entry),
                    ft.OutlinedButton("🏃 حركة", on_click=sim_motion)],
                   wrap=True, alignment=ft.MainAxisAlignment.CENTER),
        ],
    )

    # ---------- الشات ----------
    chat = ft.ListView(height=430, spacing=8, auto_scroll=True)

    def add_msg(text, mine, color=None):
        t = ft.Text(text, selectable=True, size=15)
        bubble = ft.Container(content=t, padding=10, border_radius=14,
                              bgcolor=color or ("#0078D4" if mine else "#2A2A2A"))
        chat.controls.append(
            ft.Row([bubble], alignment=ft.MainAxisAlignment.END if mine else ft.MainAxisAlignment.START))
        page.update()
        return t

    def alert(msg):
        add_msg(msg, False, color="#B71C1C")
        snack(msg, "#B71C1C")
        refresh_ui()

    hooks["alert"] = alert

    def ask_worker(text, bubble_text):
        bubble_text.value = ai_file.ask(client_holder["client"], history, text)
        refresh_ui()

    def send(e):
        text = inp.value.strip()
        if not text:
            return
        inp.value = ""
        add_msg(text, True)
        if client_holder["client"] is None:
            # من غير API Key: المساعد المحلي يرد على طول
            add_msg(local_assistant(text), False)
            refresh_ui()
            return
        thinking = add_msg("⏳ بيفكر...", False)
        threading.Thread(target=ask_worker, args=(text, thinking), daemon=True).start()

    inp = ft.TextField(hint_text="مثال: حد دخل البيت امتى؟ / الكاميرا شغالة؟",
                       expand=True, on_submit=send, border_radius=20)
    send_btn = ft.IconButton(ft.Icons.SEND, on_click=send)

    # ---------- التنقل بين الرئيسية والمساعد ----------
    def show_chat():
        main_view.visible = False
        chat_view.visible = True
        page.update()

    def show_main(e=None):
        chat_view.visible = False
        main_view.visible = True
        refresh_ui()

    ai_bar = make_tile("ai", "AI SMART HOME ASSISTANT", ft.Icons.SMART_TOY_OUTLINED, C_AI,
                       show_chat, height=80, wide=True)
    ai_bar.content = ft.Row(
        [ft.Icon(ft.Icons.SMART_TOY_OUTLINED, size=28, color="white"),
         ft.Container(width=2, height=24, bgcolor="white"),
         ft.Text("AI SMART HOME ASSISTANT", size=17, weight=ft.FontWeight.BOLD, color="white"),
         ft.Icon(ft.Icons.AUTO_AWESOME, size=24, color="white")],
        alignment=ft.MainAxisAlignment.CENTER, spacing=14)

    main_view = ft.Column(
        [header, divider, row1, row2, fire_row, ft.Container(height=6), ai_bar, sensors],
        spacing=14)

    chat_view = ft.Column(
        [ft.Row([ft.IconButton(ft.Icons.ARROW_BACK, on_click=show_main),
                 ft.Text("AI SMART HOME ASSISTANT", size=16, weight=ft.FontWeight.BOLD, expand=True),
                 ft.IconButton(ft.Icons.SETTINGS, on_click=open_settings)]),
         ft.Container(height=2, bgcolor=CYAN),
         chat,
         ft.Row([inp, send_btn])],
        visible=False, spacing=10)

    root = ft.Container(content=ft.Column([main_view, chat_view]), width=560)

    def fit(e=None):
        try:
            root.width = min(page.width or 560, 560)
            page.update()
        except Exception:
            pass

    page.on_resize = fit
    page.add(root)
    refresh_ui()
    fit()
    add_msg("أهلاً! أنا بيتي 👋 بتحكم في البيت وبسجّل كل اللي بيحصل، اسألني عن أي حاجة.", False)

    key = API_KEY.strip() or os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not key:
        try:
            key = page.client_storage.get("api_key") or ""
        except Exception:
            key = ""
    if key:
        set_key(key)


# ================= يفتح على طول من غير كلمة سر =================
def main(page: ft.Page):
    build_app(page)


# ================= اللينك العام (Cloudflare Tunnel) - للتشغيل على اللاب بس =================
def _lan_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def _cloudflared_path():
    """بينزّل cloudflared لوحده أول مرة (من غير حساب ولا توكن)."""
    import platform
    import stat
    import tarfile
    import urllib.request

    base = os.path.dirname(os.path.abspath(__file__))
    system = platform.system().lower()
    machine = platform.machine().lower()
    arch = "arm64" if ("arm" in machine or "aarch64" in machine) else "amd64"
    root = "https://github.com/cloudflare/cloudflared/releases/latest/download/"

    if system == "windows":
        path = os.path.join(base, "cloudflared.exe")
        if not os.path.exists(path):
            print("بيتنزّل ملف النفق (مرة واحدة بس) ... استني لحظات")
            urllib.request.urlretrieve(root + f"cloudflared-windows-{arch}.exe", path)
        return path

    path = os.path.join(base, "cloudflared")
    if not os.path.exists(path):
        print("بيتنزّل ملف النفق (مرة واحدة بس) ... استني لحظات")
        if system == "darwin":
            tgz = os.path.join(base, "cloudflared.tgz")
            urllib.request.urlretrieve(root + f"cloudflared-darwin-{arch}.tgz", tgz)
            with tarfile.open(tgz) as t:
                t.extract("cloudflared", base)
            os.remove(tgz)
        else:
            urllib.request.urlretrieve(root + f"cloudflared-linux-{arch}", path)
        os.chmod(path, os.stat(path).st_mode | stat.S_IEXEC)
    return path


def _start_public_tunnel():
    import re
    exe = _cloudflared_path()
    proc = subprocess.Popen(
        [exe, "tunnel", "--url", f"http://localhost:{PORT}", "--no-autoupdate"],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        encoding="utf-8", errors="ignore")

    def reader():
        shown = False
        for line in proc.stdout:
            m = re.search(r"https://[a-z0-9-]+\.trycloudflare\.com", line)
            if m and not shown:
                shown = True
                print("=" * 50)
                print(f"🌍 اللينك من أي نت أو داتا:  {m.group(0)}")
                print("=" * 50)

    threading.Thread(target=reader, daemon=True).start()


if IS_CLOUD:
    # على السيرفر: من غير نفق ومن غير ما يفتح متصفح، واللاب مش لازم يكون شغال
    print(f"التطبيق شغال على السيرفر - بورت {PORT}")
    ft.app(target=main, view=None, host="0.0.0.0", port=PORT)
else:
    print("=" * 50)
    print(f"على نفس الواي فاي:  http://{_lan_ip()}:{PORT}")
    try:
        _start_public_tunnel()
    except Exception as ex:
        print(f"النفق ما اشتغلش: {ex}")
    print("استني ثواني لحد ما يظهر اللينك العام (🌍) تحت...")
    print("=" * 50)
    ft.app(target=main, view=ft.AppView.WEB_BROWSER, host="0.0.0.0", port=PORT)