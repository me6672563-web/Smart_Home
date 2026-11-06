"""
Smart Home + AI Assistant - نسخة Flask لـ PythonAnywhere (نفس منطق app.py ونفس ملفاتك).
الملفات اللي لازم تكون جنب الملف ده: air_conditioner.py door.py fire_alarm.py TV.py
wash_machine.py lights.py Security.py ai_assistant.py
"""

import json
import os
import sys
from datetime import datetime, timedelta

from flask import Flask, jsonify, request, Response

try:
    import anthropic
except ImportError:
    anthropic = None

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
PORT = int(os.environ.get("PORT", 5050))
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


# ================= Flask =================
app = Flask(__name__)
client_holder = {"client": None}
histories = {}
pending = []                      # تنبيهات (حريق / كاميرا) بتتبعت للصفحة
hooks["alert"] = pending.append
load_events()


def set_key(k):
    if anthropic and k:
        client_holder["client"] = anthropic.Anthropic(api_key=k)


set_key(API_KEY.strip() or os.environ.get("ANTHROPIC_API_KEY", "").strip())


def apply_fire():
    set_state(FIRE, fire_file.is_on("yes" if env["smoke"] else "no", env["temp"]), source="حساس")


def apply_climate():
    """بترجع True لو التكييف اشتغل لوحده (الصفحة تسأل عن الدرجة)."""
    if ac_file.decide(env["person"], env["temp"]) == "ON":
        if not devices[AC]["on"]:
            set_state(AC, True, source="تلقائي")
            return True
    elif devices[AC]["on"]:
        set_state(AC, False, source="تلقائي")
    return False


def snapshot(**extra):
    alerts = pending[:]
    del pending[:]
    n = sum(1 for l in LIGHTS if devices[l]["on"])
    d = {"tiles": {"wash": state_text(WASHER), "lights": f"{n}/{len(LIGHTS)} شغال",
                   "security": "📷 " + state_text(CAMERA), "ac": state_text(AC),
                   "door": state_text(DOOR), "tv": state_text(TV), "fire": state_text(FIRE)},
         "on": {"wash": devices[WASHER]["on"], "ac": devices[AC]["on"],
                "door": devices[DOOR]["on"], "tv": devices[TV]["on"]},
         "cam": devices[CAMERA]["on"], "fire": devices[FIRE]["on"],
         "lights": {l: devices[l]["on"] for l in LIGHTS},
         "ac_value": devices[AC]["value"], "env": env, "alerts": alerts}
    d.update(extra)
    return jsonify(d)


def a_wash_off(d): set_state(WASHER, False, source="يدوي")


def a_wash_on(d):
    t = d.get("type", "normal")
    res = wash_file.start("yes", t)
    set_state(WASHER, True, t, source="يدوي")
    return {"msg": " - ".join(res["messages"])}


def a_light(d): set_state(d["name"], bool(d["on"]), source="يدوي")


def a_sec(d):
    res = security_file.check(d.get("pw", ""))
    ok, cam = res["ok"], devices[CAMERA]["on"]
    cam_txt = "الكاميرا شغالة ✅" if cam else "الكاميرا مطفية ⚠️"
    log_event("security", "فحص الأمان", f"الباسورد {'صح' if ok else 'غلط'} - {cam_txt}", "يدوي")
    return {"title": res["message"] + (" 🏠" if ok else " ❌"), "text": cam_txt, "cam_off": not cam}


def a_cam(d):
    set_state(CAMERA, True, source="يدوي")
    return {"msg": "الكاميرا اشتغلت ✅"}


def a_ac_tap(d):
    set_state(AC, True, source="يدوي")
    return {"ask_ac": True}


def a_ac_set(d):
    try:
        set_state(AC, True, int(d["value"]), source="يدوي")
        return {"msg": ac_file.changed_message(devices[AC]["value"])}
    except (ValueError, KeyError, TypeError):
        return {"msg": "اكتبي رقم صح للدرجة", "err": True}


def a_ac_off(d): set_state(AC, False, source="يدوي")


def a_ac_keep(d): return {"msg": ac_file.keep_message()}


def a_door_lock(d): set_state(DOOR, True, source="يدوي")


def a_door_enter(d):
    res = door_file.check(d.get("name", ""), "yes")
    who = res["name"]
    if res["known"]:
        set_state(DOOR, False, source=who)
        log_event("entry", DOOR, f"{who} دخل البيت", "الباب")
        return {"msg": " - ".join(res["messages"]) + " 👋"}
    log_event("security", DOOR, f"شخص غريب حاول يدخل (قال إنه: {who or 'مجهول'})", "الباب")
    return {"msg": res["messages"][0] + " ✋", "err": True}


def a_tv_off(d): set_state(TV, False, source="يدوي")


def a_tv_on(d):
    ch = (d.get("ch") or "").strip() or "1"
    res = tv_file.turn_on("yes", ch)
    set_state(TV, True, ch, source="يدوي")
    return {"msg": " ".join(res["messages"])}


def a_tv_no(d): return {"msg": tv_file.turn_on("no")["messages"][0]}


def a_lights_keep(d):
    if d.get("keep"):
        return {"msg": "الأنوار فضلت شغالة"} if lights_file.keep("yes") == "ON" else {}
    if lights_file.keep("no") == "OFF":
        for n in LIGHTS:
            set_state(n, False, source="تلقائي")


def a_env(d):
    out = {}
    if "person" in d:
        env["person"] = bool(d["person"])
        if lights_file.decide(env["person"]) == "ON":
            set_state(LIGHTS[0], True, source="تلقائي")
            out["ask_ac"] = apply_climate()
        else:
            out["ask_ac"] = apply_climate()
            out["ask_lights"] = any(devices[n]["on"] for n in LIGHTS)
    if "temp" in d:
        env["temp"] = int(d["temp"])
        apply_fire()
        out["ask_ac"] = apply_climate()
    if "smoke" in d:
        env["smoke"] = bool(d["smoke"])
        apply_fire()
    return out


def a_sim_entry(d):
    set_state(DOOR, False, source="حساس")
    log_event("entry", "حساس الحركة", "شخص دخل البيت", "حساس")


def a_sim_motion(d):
    log_event("motion", "حساس الحركة", "حركة في الصالة", "حساس")
    return {"msg": "اتسجلت حركة في الصالة"}


def a_key(d):
    if not anthropic:
        return {"msg": "مكتبة anthropic مش متثبتة", "err": True}
    set_key(d.get("key", "").strip())
    if d.get("quiet"):
        return {}
    return {"msg": "المفتاح اتحفظ ✅"}


def a_chat(d):
    text = d.get("text", "").strip()
    if client_holder["client"] is None:
        return {"reply": local_assistant(text)}
    try:
        return {"reply": ai_file.ask(client_holder["client"], histories.setdefault(d.get("sid", "x"), []), text)}
    except Exception as ex:
        return {"reply": f"حصل خطأ: {ex}"}


ACTIONS = {k[2:]: v for k, v in list(globals().items()) if k.startswith("a_") and callable(v)}


@app.post("/api/<name>")
def api(name):
    fn = ACTIONS.get(name)
    if not fn:
        return jsonify(error="unknown"), 404
    return snapshot(**(fn(request.get_json(silent=True) or {}) or {}))


@app.get("/api/state")
def api_state():
    return snapshot()


@app.get("/api/log")
def api_log():
    return jsonify(events=list(reversed(events[-60:])))


@app.get("/")
def index():
    return Response(PAGE, mimetype="text/html")


PAGE = r"""<!doctype html><html lang="ar"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Smart Home Intelligent Home Control</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/icon?family=Material+Icons+Outlined">
<style>
[hidden]{display:none!important}
body{margin:0;background:#030308;color:#fff;font-family:system-ui,Segoe UI,Tahoma,sans-serif;display:flex;justify-content:center}
#root{width:100%;max-width:560px;padding:16px;box-sizing:border-box}
.mi{font-family:'Material Icons Outlined';font-size:44px;font-weight:normal;font-style:normal;line-height:1;-webkit-font-feature-settings:'liga';font-feature-settings:'liga'}
.row{display:flex;gap:10px;margin-bottom:14px}
.tile{flex:1;height:120px;border-radius:26px;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:4px;cursor:pointer;text-align:center;user-select:none}
.tile b{font-size:13px}.tile small{font-size:11px;color:#FFFFFFCC;min-height:13px}
.wide{height:130px;flex-direction:row;gap:18px}.wide b{font-size:20px;display:block}
button{background:none;border:0;color:#22D3EE;font-size:15px;cursor:pointer;padding:8px 12px}
input[type=text],input[type=password],input[type=number]{width:100%;box-sizing:border-box;padding:10px;margin-top:8px;background:#111;color:#fff;border:1px solid #555;border-radius:8px;font-size:15px}
.ov{position:fixed;inset:0;background:#000A;display:flex;align-items:center;justify-content:center;z-index:9}
.dl{background:#1E1E1E;border-radius:20px;padding:20px;min-width:280px;max-width:90vw}.dl h3{margin:0 0 12px}
.ac{display:flex;justify-content:flex-end;flex-wrap:wrap;margin-top:12px}
.toast{position:fixed;bottom:20px;left:50%;transform:translateX(-50%);background:#333;padding:12px 18px;border-radius:10px;z-index:10;max-width:90vw}
.mr{display:flex;margin:4px 0}.bb{padding:10px;border-radius:14px;max-width:85%;white-space:pre-wrap;font-size:15px}
#chat{height:430px;overflow:auto}summary{color:#888;font-size:13px;cursor:pointer;margin:6px 0}
details label{display:block;margin:10px 0}
</style></head><body><div id="root">
<div id="main">
<div style="display:flex;justify-content:space-between;align-items:center">
 <i class="mi" style="font-size:46px;color:#E8EEF5">home</i>
 <div style="text-align:center"><div style="font-size:26px;font-weight:900">SMART HOME</div><div style="font-size:11px;font-weight:bold;color:#9CC3E6">INTELLIGENT HOME CONTROL</div></div>
 <button onclick="showLog()" title="السجل"><i class="mi" style="font-size:34px;color:#22D3EE">signal_cellular_alt</i></button></div>
<div style="height:2px;background:#22D3EE;margin:12px 0"></div>
<div class="row">
 <div class="tile" id="t-wash" style="background:#0099FF" onclick="wash()"><i class="mi">local_laundry_service</i><b>WASH MACHINE</b><small id="s-wash"></small></div>
 <div class="tile" id="t-lights" style="background:#E6B800" onclick="lights()"><i class="mi">lightbulb</i><b>LIGHTS</b><small id="s-lights"></small></div>
 <div class="tile" id="t-security" style="background:#00CC44" onclick="sec()"><i class="mi">shield</i><b>SECURITY</b><small id="s-security"></small></div></div>
<div class="row">
 <div class="tile" id="t-ac" style="background:#00B3B3" onclick="ac()"><i class="mi">ac_unit</i><b>AIR CONDITIONER</b><small id="s-ac"></small></div>
 <div class="tile" id="t-door" style="background:#E65C00" onclick="door()"><i class="mi">door_front_door</i><b>DOOR ACCESS</b><small id="s-door"></small></div>
 <div class="tile" id="t-tv" style="background:#9900CC" onclick="tv()"><i class="mi">tv</i><b>TELEVISION</b><small id="s-tv"></small></div></div>
<div class="row"><div class="tile wide" id="t-fire" style="background:#CC0029" onclick="fire()"><i class="mi">local_fire_department</i><div><b>FIRE ALARM</b><small id="s-fire"></small></div></div></div>
<div class="row" style="margin-top:6px"><div class="tile wide" style="background:#4B0082;height:80px;gap:14px" onclick="view(1)">
 <i class="mi" style="font-size:28px">smart_toy</i><span style="width:2px;height:24px;background:#fff"></span><b style="font-size:17px">AI SMART HOME ASSISTANT</b><i class="mi" style="font-size:24px">auto_awesome</i></div></div>
<details><summary>الحساسات (للتجربة)</summary>
 <label><input type="checkbox" id="person" onchange="api('env',{person:this.checked})"> 👤 فيه حد في البيت</label>
 <div id="tt" style="font-size:14px"></div>
 <input type="range" id="temp" min="15" max="50" style="width:100%" oninput="tt.textContent='درجة حرارة البيت: '+this.value+'°C'" onchange="api('env',{temp:+this.value})">
 <label><input type="checkbox" id="smoke" onchange="api('env',{smoke:this.checked})"> 💨 دخان</label>
 <div style="text-align:center"><button onclick="api('sim_entry',{})">🚪 دخول شخص</button><button onclick="api('sim_motion',{})">🏃 حركة</button></div></details>
</div>
<div id="chatv" hidden>
 <div style="display:flex;align-items:center"><button onclick="view(0)"><i class="mi" style="font-size:24px;color:#fff">arrow_back</i></button>
 <b style="flex:1">AI SMART HOME ASSISTANT</b><button onclick="settings()"><i class="mi" style="font-size:24px;color:#fff">settings</i></button></div>
 <div style="height:2px;background:#22D3EE;margin:10px 0"></div><div id="chat"></div>
 <div style="display:flex;gap:6px;margin-top:10px"><input type="text" id="msg" style="margin:0;border-radius:20px" placeholder="مثال: حد دخل البيت امتى؟ / الكاميرا شغالة؟" onkeydown="if(event.key=='Enter')send()">
 <button onclick="send()"><i class="mi" style="font-size:24px">send</i></button></div></div>
</div>
<script>
const $=s=>document.querySelector(s),sid=Math.random().toString(36).slice(2);let S=null,first=1;
const el=h=>{const d=document.createElement('div');d.innerHTML=h;return d};
function inp(type,ph){const i=document.createElement('input');i.type=type;i.placeholder=ph;return i}
async function api(n,b){const r=await fetch('/api/'+n,{method:b===undefined?'GET':'POST',headers:{'Content-Type':'application/json'},body:b===undefined?undefined:JSON.stringify(b)});const j=await r.json();render(j);return j}
function render(j){
 if(j.tiles){S=j;for(const k in j.tiles)$('#s-'+k).textContent=j.tiles[k];
  $('#t-security').style.background=j.cam?'#00CC44':'#E65100';$('#t-fire').style.outline=j.fire?'3px solid #fff':'none';
  if(first){first=0;$('#person').checked=j.env.person;$('#smoke').checked=j.env.smoke;$('#temp').value=j.env.temp;tt.textContent='درجة حرارة البيت: '+j.env.temp+'°C'}}
 (j.alerts||[]).forEach(m=>{addMsg(m,0,'#B71C1C');toast(m,'#B71C1C')});
 if(j.msg)toast(j.msg,j.err?'#B71C1C':null);
 if(j.ask_ac)askAC();if(j.ask_lights)askLights()}
function toast(m,c){const t=el('');t.className='toast';t.textContent=m;if(c)t.style.background=c;document.body.append(t);setTimeout(()=>t.remove(),3500)}
const Q=[];let busy=false;
function dlg(t,body,btns){Q.push([t,body,btns]);if(!busy)nxt()}
function nxt(){const x=Q.shift();if(!x){busy=false;return}busy=true;
 const o=el(''),d=el(''),h=document.createElement('h3'),a=el('');o.className='ov';d.className='dl';a.className='ac';h.textContent=x[0];d.append(h);
 d.append(typeof x[1]=='string'?document.createTextNode(x[1]):x[1]);
 x[2].forEach(([l,cb])=>{const b=document.createElement('button');b.textContent=l;b.onclick=()=>{o.remove();cb&&cb();nxt()};a.append(b)});
 d.append(a);o.append(d);document.body.append(o);const f=d.querySelector('input[type=text],input[type=password],input[type=number]');f&&f.focus()}
function wash(){if(S.on.wash)return api('wash_off',{});
 const b=el('<label><input type="radio" name="w" value="normal" checked> عادي (normal)</label><br><label><input type="radio" name="w" value="quick"> سريع (quick)</label>');
 dlg('تشغيل الغسالة 🧺',b,[['شغّل',()=>api('wash_on',{type:b.querySelector('input:checked').value})],['إلغاء']])}
function lights(){const b=el('');for(const n in S.lights){const l=document.createElement('label');l.style.display='block';l.style.margin='8px 0';l.innerHTML='<input type="checkbox"> '+n;const c=l.firstChild;c.checked=S.lights[n];c.onchange=()=>api('light',{name:n,on:c.checked});b.append(l)}dlg('الأنوار 💡',b,[['تمام']])}
function sec(){const i=inp('password','Please, enter security password');i.inputMode='numeric';
 dlg('فحص الأمان 🔐',i,[['تأكيد',async()=>{const r=await api('sec',{pw:i.value});const bt=[['تمام']];if(r.cam_off)bt.unshift(['شغّل الكاميرا',()=>api('cam',{})]);dlg(r.title,r.text,bt)}],['إلغاء']])}
function ac(){S.on.ac?askAC():api('ac_tap',{})}
function askAC(){const i=inp('number','الدرجة الجديدة');i.value=S.ac_value;const b=el('<p>الدرجة دلوقتي '+S.ac_value+'°C. تحب تغيّرها؟</p>');b.append(i);
 dlg('التكييف شغال ❄️',b,[['غيّر',()=>api('ac_set',{value:i.value})],['اطفيه',()=>api('ac_off',{})],['زي ما هي',()=>api('ac_keep',{})]])}
function door(){if(!S.on.door)return api('door_lock',{});const i=inp('text','who are you? / مين حضرتك؟');
 dlg('باب الشقة 🚪',i,[['دخول',()=>api('door_enter',{name:i.value})],['إلغاء']])}
function tv(){if(S.on.tv)return api('tv_off',{});const i=inp('text','أي قناة تحب تتفرج عليها؟');
 dlg('تشغيل التلفزيون 📺',i,[['شغّل',()=>api('tv_on',{ch:i.value})],['لأ',()=>api('tv_no',{})]])}
function fire(){const s=v=>()=>{$('#smoke').checked=v;api('env',{smoke:v})};
 dlg('فحص الحريق 🔥','فيه دخان؟ (الحرارة الحالية '+S.env.temp+'°C)',[['أيوه، فيه دخان',s(true)],['لأ',s(false)],['إلغاء']])}
function askLights(){dlg('الأنوار 💡','مفيش حد في البيت. تحب الأنوار تفضل شغالة؟',[['أيوه سيبها',()=>api('lights_keep',{keep:true})],['لأ، اطفيها',()=>api('lights_keep',{keep:false})]])}
async function showLog(){const r=await api('log');const ic={entry:'🚪',fire_alarm:'🔥',motion:'🏃',security:'🔐'},b=el('');b.style.cssText='max-height:380px;overflow:auto';
 r.events.forEach(e=>{const d=el('');d.style.cssText='font-size:13px;margin:6px 0;white-space:pre-line';d.textContent=(ic[e.kind]||'🔧')+' '+e.time+'\n'+e.device+': '+e.detail+'  ('+e.source+')';b.append(d)});
 if(!r.events.length)b.textContent='السجل فاضي لسه';dlg('سجل أحداث البيت',b,[['إغلاق']])}
function view(c){$('#main').hidden=!!c;$('#chatv').hidden=!c}
function addMsg(t,mine,c){const r=el(''),b=el('');r.className='mr';r.style.justifyContent=mine?'flex-end':'flex-start';b.className='bb';b.style.background=c||(mine?'#0078D4':'#2A2A2A');b.textContent=t;r.append(b);$('#chat').append(r);$('#chat').scrollTop=1e9;return b}
async function send(){const i=$('#msg'),t=i.value.trim();if(!t)return;i.value='';addMsg(t,1);const b=addMsg('⏳ بيفكر...',0);const r=await api('chat',{text:t,sid});b.textContent=r.reply}
function settings(){const i=inp('password','Anthropic API Key');dlg('إعدادات الـ AI',i,[['حفظ',()=>{const k=i.value.trim();if(k){try{localStorage.k=k}catch(e){}api('key',{key:k})}}]])}
addMsg('أهلاً! أنا بيتي 👋 بتحكم في البيت وبسجّل كل اللي بيحصل، اسألني عن أي حاجة.',0);
api('state');setInterval(()=>api('state'),5000);
try{if(localStorage.k)api('key',{key:localStorage.k,quiet:1})}catch(e){}
</script></body></html>"""


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT)