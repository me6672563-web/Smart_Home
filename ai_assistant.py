import json
from datetime import datetime

MODEL = "claude-sonnet-5-5"
FIRE = "إنذار الحريق"
TS_FMT = "%Y-%m-%d %H:%M:%S"

# بيتملّوا من app.py في bind()
devices = None
set_state = None
state_text = None
query_events = None
home_env = None


def bind(app_devices, app_set_state, app_state_text, app_query_events, app_env=None):
    """بتربط المساعد بأجهزة وسجل التطبيق."""
    global devices, set_state, state_text, query_events, home_env
    devices = app_devices
    set_state = app_set_state
    state_text = app_state_text
    query_events = app_query_events
    home_env = app_env


def now_str():
    return datetime.now().strftime(TS_FMT)


def snapshot():
    out = {n: {"القسم": d["group"], "الحالة": state_text(n)} for n, d in devices.items()}
    if home_env is not None:   # إضافة: حالة البيت (حد في البيت؟ حرارة، دخان)
        out["حالة البيت"] = {
            "فيه حد في البيت": home_env["person"],
            "درجة الحرارة": home_env["temp"],
            "دخان": home_env["smoke"],
        }
    return out


def make_system():
    return f"""أنت مساعد بيت ذكي اسمه "بيتي"، بتتكلم بالعامية المصرية ومختصر ومنطقي.
الوقت دلوقتي: {now_str()}

عندك أدوات:
- get_home_status: الحالة الحالية الحقيقية للأجهزة.
- get_events: سجل كل اللي حصل في البيت ومتى (دخول أشخاص، حركة، إنذار حريق، تشغيل/إطفاء أي جهاز، ومين عملها).
- set_device: للتحكم في الأجهزة.

قواعد مهمة:
1. أي سؤال عن حاجة حصلت قبل كده ("حد دخل البيت امتى؟"، "حصل حريق امتى؟"، "التلفزيون اتشغل امتى؟"،
   "مين فتح الباب؟") لازم تستدعي get_events الأول وتجاوب منه بالتاريخ والوقت بالظبط،
   وقول من إيه الحاجة حصلت (إنت/المساعد/حساس) لو مهم. ولو الحدث كان من بدري قول "من كام ساعة/يوم" بالنسبة للوقت الحالي.
   "دخول البيت" = أحداث entry، وممكن كمان فتح باب الشقة (device_change على باب الشقة).
2. لو get_events مرجعش حاجة قول بصراحة إنه مفيش تسجيل لحدث زي ده. ممنوع تألف أحداث أو أوقات من عندك،
   والسجل بيبدأ من أول ما التطبيق اشتغل.
3. لأسئلة الحالة الحالية استخدم get_home_status وجاوب مباشرة. ممنوع تقول "شوف من القائمة" أو "راجع الإعدادات" أو "راجع الـ Rules".
4. بعد أي تحكم بـ set_device أكد للمستخدم اللي حصل.
5. لو الجهاز مش موجود قول بصراحة واذكر الأجهزة المتاحة. لو الطلب غامض اسأل سؤال واحد قصير.
6. اتكلم في موضوعات البيت بس. لو السؤال خارج البيت اعتذر بلطف.
7. لو فيه خطر (إنذار حريق شغال، السخان شغال وإنت مش في البيت، باب مفتوح بالليل) نبّه المستخدم.
8. في أسئلة الأمان لو في إنذار حريق شغال دلوقتي قوله الأول قبل أي حاجة تانية."""


TOOLS = [
    {
        "name": "get_home_status",
        "description": "بترجع الحالة الحقيقية الحالية لكل أجهزة البيت.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_events",
        "description": "بترجع سجل الأحداث اللي حصلت في البيت مع الوقت (الأحدث أولاً). "
                       "استخدمها لأي سؤال عن حاجة حصلت قبل كده.",
        "input_schema": {
            "type": "object",
            "properties": {
                "device": {"type": "string", "description": "جزء من اسم الجهاز/الحساس، مثلاً: التلفزيون، باب الشقة، حساس"},
                "kind": {"type": "string",
                         "enum": ["entry", "fire_alarm", "motion", "device_change"],
                         "description": "نوع الحدث: entry=دخول شخص، fire_alarm=إنذار حريق، motion=حركة، device_change=تغيير حالة جهاز"},
                "hours": {"type": "number", "description": "ارجع بس الأحداث في آخر كذا ساعة (اختياري)"},
                "limit": {"type": "integer", "description": "أقصى عدد أحداث (الافتراضي 20)"},
            },
        },
    },
    {
        "name": "set_device",
        "description": "تشغيل/إطفاء جهاز، أو قفل/فتح الباب، أو ضبط درجة التكييف.",
        "input_schema": {
            "type": "object",
            "properties": {
                "device": {"type": "string", "description": "اسم الجهاز بالظبط"},
                "on": {"type": "boolean", "description": "true = شغال/مقفول، false = مطفي/مفتوح"},
                "value": {"type": "number", "description": "درجة حرارة التكييف (اختياري)"},
            },
            "required": ["device", "on"],
        },
    },
]


def run_tool(name, args):
    if name == "get_home_status":
        return snapshot()
    if name == "get_events":
        return query_events(args.get("device"), args.get("kind"),
                            args.get("hours"), args.get("limit", 20))
    if name == "set_device":
        dev = args["device"]
        if dev not in devices:
            return {"error": f"الجهاز '{dev}' مش موجود", "available": list(devices)}
        if dev == FIRE:
            return {"error": "إنذار الحريق بيتحكم فيه الحساس بس، مش من المساعد"}
        set_state(dev, args["on"], args.get("value"), source="المساعد")
        return {"ok": True, "device": dev, "الحالة": state_text(dev)}
    return {"error": "أداة غير معروفة"}


def ask(client, history, text):
    """نفس حلقة ask_worker بتاعتك: بتكلم Claude وتنفّذ الأدوات لحد ما يرد برد نهائي."""
    history.append({"role": "user", "content": text})
    start = len(history) - 1
    try:
        while True:
            resp = client.messages.create(
                model=MODEL, max_tokens=800, system=make_system(),
                tools=TOOLS, messages=history,
            )
            history.append({"role": "assistant", "content": resp.content})
            if resp.stop_reason == "tool_use":
                results = []
                for b in resp.content:
                    if b.type == "tool_use":
                        out = run_tool(b.name, b.input)
                        results.append({
                            "type": "tool_result", "tool_use_id": b.id,
                            "content": json.dumps(out, ensure_ascii=False),
                        })
                history.append({"role": "user", "content": results})
            else:
                return "".join(b.text for b in resp.content if b.type == "text")
    except Exception as ex:
        del history[start:]   # يشيل الرسالة وأي أدوات ناقصة عشان المحادثة ما تبوظش
        return f"حصل خطأ في الاتصال:\n{ex}"