"""
Streakly onboarding: questionnaire, personal plan builder, and daily lessons.

Flow: welcome -> questions (stored in session) -> plan preview -> register/login -> Today.
After registration apply_onboarding() creates the user's starter habits, daily routine
and first challenge from the answers.
"""
from datetime import date, datetime, time as dtime, timedelta

from django.db import transaction

from .models import Challenge, Habit, OnboardingAnswer, RoutineItem

# ---------------------------------------------------------------------------
# Questions (Russian UI). Every option id must stay stable: answers are stored by id.
# ---------------------------------------------------------------------------

QUESTIONS = [
    {
        "id": "focus",
        "title": "Что для тебя сейчас важнее всего?",
        "sub": "Выбери одно. Остальное подтянется.",
        "options": [
            {"id": "money", "label": "Деньги и карьера", "hint": "Доход, навык, свой проект", "icon": "fa-coins"},
            {"id": "discipline", "label": "Дисциплина и воля", "hint": "Делать, даже когда не хочется", "icon": "fa-fire"},
            {"id": "body", "label": "Тело и здоровье", "hint": "Сила, энергия, режим", "icon": "fa-dumbbell"},
            {"id": "circle", "label": "Круг общения", "hint": "Друзья, связи, влияние", "icon": "fa-user-group"},
            {"id": "mind", "label": "Характер и спокойствие", "hint": "Холодная голова и внутренний стержень", "icon": "fa-brain"},
        ],
    },
    {
        "id": "finance",
        "title": "Как у тебя сейчас с деньгами?",
        "sub": "Без стеснения. Это нужно, чтобы план был честным.",
        "options": [
            {"id": "none", "label": "Пока нет дохода", "hint": "Учусь или ищу своё", "icon": "fa-seedling"},
            {"id": "spend", "label": "Доход есть, но всё уходит", "hint": "Нет накоплений и контроля трат", "icon": "fa-wallet"},
            {"id": "stable", "label": "Стабильный доход", "hint": "Хочу расти и копить", "icon": "fa-arrow-trend-up"},
            {"id": "biz", "label": "Свой бизнес или проект", "hint": "Хочу масштабироваться", "icon": "fa-briefcase"},
        ],
    },
    {
        "id": "time",
        "title": "Сколько времени в день готов вкладывать в себя?",
        "sub": "Честно. Лучше меньше, но каждый день.",
        "options": [
            {"id": "t30", "label": "30 минут", "hint": "Минимум, зато каждый день", "icon": "fa-hourglass-start"},
            {"id": "t60", "label": "1 час", "hint": "Хороший рабочий ритм", "icon": "fa-hourglass-half"},
            {"id": "t120", "label": "2 часа", "hint": "Серьёзный подход", "icon": "fa-hourglass-end"},
            {"id": "t180", "label": "3 часа и больше", "hint": "Полная концентрация", "icon": "fa-bolt"},
        ],
    },
    {
        "id": "obstacle",
        "title": "Что тебя тормозит чаще всего?",
        "sub": "Назови главного врага.",
        "options": [
            {"id": "lazy", "label": "Лень и прокрастинация", "hint": "Откладываю на потом", "icon": "fa-couch"},
            {"id": "phone", "label": "Телефон, соцсети, игры", "hint": "Время утекает незаметно", "icon": "fa-mobile-screen"},
            {"id": "noplan", "label": "Нет чёткого плана", "hint": "Хватаюсь за всё сразу", "icon": "fa-map"},
            {"id": "fear", "label": "Страх ошибиться", "hint": "Боюсь начать и не справиться", "icon": "fa-shield-halved"},
            {"id": "tired", "label": "Усталость, нет энергии", "hint": "К вечеру нет сил", "icon": "fa-battery-quarter"},
        ],
    },
    {
        "id": "wake",
        "title": "Во сколько ты обычно встаёшь?",
        "sub": "Из этого соберём реалистичный распорядок дня.",
        "options": [
            {"id": "late", "label": "Позже 10:00", "hint": "Начнём с 8:30", "icon": "fa-moon"},
            {"id": "mid", "label": "С 8:00 до 10:00", "hint": "Начнём с 7:30", "icon": "fa-cloud-sun"},
            {"id": "early", "label": "С 6:00 до 8:00", "hint": "Начнём с 6:30", "icon": "fa-sun"},
            {"id": "vearly", "label": "Раньше 6:00", "hint": "Начнём с 5:30", "icon": "fa-mountain-sun"},
        ],
    },
    {
        "id": "friends",
        "title": "Как у тебя с друзьями?",
        "sub": "Окружение определяет твой уровень.",
        "options": [
            {"id": "none", "label": "Друзей почти нет", "hint": "Хочу найти своих людей", "icon": "fa-user"},
            {"id": "few", "label": "Есть один-два близких", "hint": "Хочу сильное окружение", "icon": "fa-user-group"},
            {"id": "shallow", "label": "Много знакомых, мало настоящих", "hint": "Нужно качество, не количество", "icon": "fa-users"},
            {"id": "ok", "label": "Всё хорошо", "hint": "Хочу держать планку", "icon": "fa-handshake"},
        ],
    },
    {
        "id": "alone",
        "title": "Как ты переносишь одиночество?",
        "sub": "Умение быть одному делает тебя свободным.",
        "options": [
            {"id": "hard", "label": "Тяжело, быстро тянет к людям", "hint": "Скучно и тревожно одному", "icon": "fa-face-frown"},
            {"id": "ok", "label": "Нормально", "hint": "Могу, но не всегда хочу", "icon": "fa-face-meh"},
            {"id": "comfy", "label": "Комфортно, люблю быть один", "hint": "Заряжаюсь в тишине", "icon": "fa-face-smile"},
        ],
    },
    {
        "id": "decide",
        "title": "Как ты принимаешь решения?",
        "sub": "Мужской характер начинается с решений.",
        "options": [
            {"id": "doubt", "label": "Долго сомневаюсь", "hint": "Откладываю и тяну", "icon": "fa-hourglass"},
            {"id": "emotion", "label": "Решаю по эмоциям", "hint": "Потом жалею", "icon": "fa-heart-pulse"},
            {"id": "advice", "label": "Спрашиваю у других", "hint": "Сам не уверен", "icon": "fa-comments"},
            {"id": "fast", "label": "Быстро и беру ответственность", "hint": "Хочу делать это ещё лучше", "icon": "fa-gavel"},
        ],
    },
]

TIME_MINUTES = {"t30": 30, "t60": 60, "t120": 120, "t180": 180}
WAKE_TIME = {"late": dtime(8, 30), "mid": dtime(7, 30), "early": dtime(6, 30), "vearly": dtime(5, 30)}


def validate_answers(raw):
    """Returns a clean {question_id: option_id} dict, or None if anything is missing or invalid."""
    if not isinstance(raw, dict):
        return None
    clean = {}
    for q in QUESTIONS:
        val = raw.get(q["id"])
        if val not in {o["id"] for o in q["options"]}:
            return None
        clean[q["id"]] = val
    return clean


# ---------------------------------------------------------------------------
# Plan builder
# ---------------------------------------------------------------------------

HABITS = {
    "train":   ("Тренировка", "Сила тела это основа воли и энергии. Двигайся каждый день."),
    "plan":    ("План на день", "Кто управляет днём, тот управляет жизнью. Запиши 3 главные задачи."),
    "focus":   ("Глубокая работа без телефона", "Один час полного фокуса стоит больше, чем пять часов рассеянности."),
    "income":  ("Работа над доходом", "Деньги идут за ценностью. Каждый день делай шаг к своему делу или навыку."),
    "skill":   ("Учёба и навык", "Навык, за который платят, это самый надёжный капитал."),
    "read":    ("Чтение", "Читай книги, которые меняют мышление. Двадцать минут в день дают десятки книг в год."),
    "social":  ("Живое общение", "Пиши друзьям, встречайся, знакомься. Круг общения строят действиями."),
    "journal": ("Дневник решений", "Записывай решения и выводы. Так ты учишься на ошибках, а не повторяешь их."),
    "alone":   ("Время наедине", "Тишина без телефона. Умение быть одному делает тебя свободным."),
}
HABIT_ORDER = list(HABITS.keys())
MORNING = ["train", "plan", "focus", "income", "skill", "read"]
EVENING = ["social", "journal", "alone"]

RULES = {
    "focus": {"money": {"income": 5, "skill": 3}, "discipline": {"focus": 4, "plan": 2, "train": 2},
              "body": {"train": 6, "plan": 1}, "circle": {"social": 5, "alone": 1},
              "mind": {"alone": 4, "journal": 4, "read": 2}},
    "finance": {"none": {"skill": 3, "income": 2}, "spend": {"plan": 3, "skill": 2},
                "stable": {"income": 3}, "biz": {"income": 4, "social": 2}},
    "obstacle": {"lazy": {"train": 2, "plan": 1}, "phone": {"focus": 4}, "noplan": {"plan": 4},
                 "fear": {"journal": 2, "social": 1}, "tired": {"train": 3}},
    "friends": {"none": {"social": 4}, "few": {"social": 2}, "shallow": {"social": 2, "alone": 1}, "ok": {"social": 1}},
    "alone": {"hard": {"alone": 4}, "ok": {"alone": 2}, "comfy": {"alone": 1}},
    "decide": {"doubt": {"journal": 4}, "emotion": {"journal": 3, "alone": 1}, "advice": {"journal": 3}, "fast": {"plan": 1}},
}

ARCHETYPES = {
    "money": ("Строитель капитала",
              "Деньги приходят к тому, кто растёт в навыке и годами не сдаётся. Сначала навык и доход, потом накопления и вложения.",
              "Построить стабильный доход и привычку откладывать"),
    "discipline": ("Железная дисциплина",
                   "Сильный человек делает то, что решил, даже когда не хочется. Дисциплина это уважение к самому себе.",
                   "Стать человеком, который выполняет свои обещания"),
    "body": ("Сильное тело",
             "Энергия и здоровье это фундамент всего остального. Сильное тело делает сильнее и характер.",
             "Выйти на стабильный режим и физическую форму"),
    "circle": ("Лидер окружения",
               "Ты становишься средним из тех, с кем проводишь время. Выбирай людей и строй круг осознанно.",
               "Собрать крепкое окружение и научиться общаться уверенно"),
    "mind": ("Холодная голова",
             "Спокойствие, ответственность за свои решения и умение быть одному. Сильный тот, кто управляет собой.",
             "Научиться держать себя в руках и принимать решения"),
}


def _round5(x):
    return int(5 * round(x / 5.0))


def _add_minutes(t, minutes):
    return (datetime.combine(date.today(), t) + timedelta(minutes=minutes)).time()


def _principles(a):
    items = []
    if a["obstacle"] == "phone":
        items.append("Телефон главный враг фокуса. Убирай его из комнаты на время работы.")
    elif a["obstacle"] == "noplan":
        items.append("Три главные задачи на день. Больше не нужно, меньше нельзя.")
    elif a["obstacle"] == "lazy":
        items.append("Не жди настроения. Сделай первые 10 минут, и дальше пойдёт.")
    elif a["obstacle"] == "fear":
        items.append("Ошибки это цена роста. Действуй небольшими шагами и учись на результатах.")
    else:
        items.append("Сон и движение дают энергию. Режим важнее мотивации.")

    if a["alone"] == "hard":
        items.append("Одиночество это навык. Начни с 20 минут в день без телефона.")
    elif a["friends"] in ("none", "few"):
        items.append("Друзей строят, а не находят. Раз в неделю пиши первым и предлагай встречу.")
    elif a["friends"] == "shallow":
        items.append("Выбирай качество: оставь 3-5 людей, которые растут вместе с тобой.")
    else:
        items.append("Держи окружение сильным: общайся с теми, у кого можно учиться.")

    if a["finance"] in ("none", "spend"):
        items.append("Сначала навык и контроль трат, потом вложения. «Быстрые деньги» это обычно ловушка.")
    else:
        items.append("Откладывай 10-20% с каждого дохода сразу, как только получил.")
    return items[:3]


def build_plan(a):
    """a is a validated answers dict. Returns a plan dict used by the preview page and apply_onboarding()."""
    weights = {k: 0 for k in HABITS}
    weights["train"] += 1
    weights["read"] += 1
    for qid, table in RULES.items():
        for habit, n in table.get(a.get(qid), {}).items():
            weights[habit] += n

    budget = TIME_MINUTES[a["time"]]
    count = 3 if budget <= 30 else 4 if budget <= 60 else 5
    chosen = sorted(HABIT_ORDER, key=lambda k: (-weights[k], HABIT_ORDER.index(k)))[:count]
    total_w = sum(weights[k] for k in chosen) or 1

    habits = []
    for k in chosen:
        minutes = max(10, _round5(budget * weights[k] / total_w))
        habits.append({"key": k, "title": HABITS[k][0], "minutes": minutes, "why": HABITS[k][1]})
    by_key = {h["key"]: h for h in habits}

    wake = WAKE_TIME[a["wake"]]
    routine = [{"title": "Подъём, вода, без телефона", "start": wake, "end": _add_minutes(wake, 30), "habit_key": None}]

    cursor = _add_minutes(wake, 30)
    for k in [k for k in MORNING if k in by_key]:
        end = _add_minutes(cursor, by_key[k]["minutes"])
        routine.append({"title": by_key[k]["title"], "start": cursor, "end": end, "habit_key": k})
        cursor = _add_minutes(end, 10)

    cursor = dtime(20, 30)
    for k in [k for k in EVENING if k in by_key]:
        end = _add_minutes(cursor, by_key[k]["minutes"])
        if end <= cursor:  # crossed midnight, skip
            break
        routine.append({"title": by_key[k]["title"], "start": cursor, "end": end, "habit_key": k})
        cursor = _add_minutes(end, 10)
        if cursor < dtime(20, 30):
            break

    focus = a["focus"]
    name, text, goal = ARCHETYPES[focus]
    return {
        "focus": focus,
        "archetype": name,
        "archetype_text": text,
        "habits": habits,
        "total_minutes": sum(h["minutes"] for h in habits),
        "wake": wake,
        "routine": routine,
        "challenge": {"title": "30 дней без оправданий", "goal": goal, "days": 30, "habit_key": habits[0]["key"]},
        "principles": _principles(a),
    }


@transaction.atomic
def apply_onboarding(user, answers):
    """Saves the answers and creates the starter habits, routine and challenge for a new user."""
    plan = build_plan(answers)
    OnboardingAnswer.objects.update_or_create(user=user, defaults={"answers": answers, "focus": plan["focus"]})

    habit_objs = {}
    for h in plan["habits"]:
        habit_objs[h["key"]] = Habit.objects.create(user=user, title=h["title"], daily_goal_minutes=h["minutes"])

    for r in plan["routine"]:
        RoutineItem.objects.create(
            user=user, title=r["title"], start_time=r["start"], end_time=r["end"],
            habit=habit_objs.get(r["habit_key"]),
        )

    ch = plan["challenge"]
    Challenge.objects.create(user=user, title=ch["title"], goal=ch["goal"], days=ch["days"],
                             habit=habit_objs[ch["habit_key"]])
    return plan


# ---------------------------------------------------------------------------
# Daily lessons (short, practical, one action per lesson)
# ---------------------------------------------------------------------------

TRACK_LABELS = {
    "discipline": "Дисциплина",
    "money": "Деньги",
    "mind": "Характер",
    "circle": "Круг общения",
    "alone": "Одиночество",
}
TRACK_ORDER = ["discipline", "money", "mind", "circle", "alone"]
FOCUS_TRACK = {"money": "money", "discipline": "discipline", "body": "discipline", "circle": "circle", "mind": "mind"}

LESSONS = {
    "discipline": [
        {"title": "Мотивация приходит после действия",
         "text": "Не жди настроения. Мотивация это результат старта, а не его условие. Сделай первые две минуты, и мозг включится.",
         "action": "Запусти таймер на 10 минут, даже если не хочется."},
        {"title": "Правило одного обещания",
         "text": "Каждое невыполненное обещание себе снижает самоуважение. Давай меньше обещаний и выполняй все.",
         "action": "Выбери одну задачу на сегодня и закрой её до обеда."},
        {"title": "Среда сильнее воли",
         "text": "Сила воли ограничена. Убери телефон из комнаты, где работаешь, и ты выиграешь без борьбы.",
         "action": "Положи телефон в другую комнату на 30 минут."},
    ],
    "money": [
        {"title": "Сначала навык, потом капитал",
         "text": "Быстро разбогатеть почти всегда миф. Реальный путь: навык, за который платят, затем доход, затем накопления и вложения.",
         "action": "Выпиши навык, который принесёт тебе деньги, и займись им 30 минут."},
        {"title": "Плати сначала себе",
         "text": "Откладывай 10-20% с каждого дохода сразу, а не то, что осталось в конце месяца. Привычка важнее суммы.",
         "action": "Определи свой процент и переведи первую сумму сегодня."},
        {"title": "Долги и азарт: главные враги",
         "text": "Потребкредиты, ставки и «верные схемы» забирают больше, чем дают. Если обещают быстрые деньги, проверь дважды.",
         "action": "Запиши все свои долги и ежемесячные траты."},
    ],
    "mind": [
        {"title": "Пауза между эмоцией и действием",
         "text": "Сильный человек не лишён эмоций, он выбирает реакцию. Перед ответом на злость или обиду сделай три глубоких вдоха.",
         "action": "В первой раздражающей ситуации сегодня выдержи паузу 10 секунд."},
        {"title": "Бери ответственность",
         "text": "Ты не контролируешь всё, но отвечаешь за свою реакцию и следующий шаг. «Что я могу сделать?» сильнее вопроса «кто виноват?».",
         "action": "Выбери одну проблему и запиши шаг, который сделаешь сам."},
        {"title": "Решение лучше сомнения",
         "text": "Большинство решений обратимы. Мелочи решай за минуту, важное до завтра. Потом действуй и делай выводы.",
         "action": "Прими сегодня одно отложенное решение."},
    ],
    "circle": [
        {"title": "Друзей строят, а не находят",
         "text": "Крепкая дружба это регулярные встречи и взаимная польза. Написать первым не слабость, а инициатива.",
         "action": "Напиши одному человеку и предложи встретиться на этой неделе."},
        {"title": "Ты среднее из своего окружения",
         "text": "Люди рядом задают твою планку. Держись тех, кто растёт, и сам будь полезным.",
         "action": "Запиши трёх людей, у кого можно учиться, и свяжись с одним."},
        {"title": "Слушай больше, чем говоришь",
         "text": "Влияние рождается из внимания. Задавай вопросы и запоминай детали о человеке.",
         "action": "В разговоре сегодня задай три вопроса, не перебивая."},
    ],
    "alone": [
        {"title": "Одиночество это навык",
         "text": "Кто комфортно проводит время наедине, не цепляется за людей из страха. Тогда дружба становится выбором, а не нуждой.",
         "action": "20 минут без телефона и музыки: просто посиди или прогуляйся."},
        {"title": "Тишина против суеты",
         "text": "Постоянный шум скрывает мысли. Минуты тишины возвращают ясность и подсказывают решения.",
         "action": "Пройдись сегодня 15 минут без наушников."},
        {"title": "Дневник: разговор с собой",
         "text": "Записывай по вечерам, что сделал, что понял и что улучшишь. Через месяц увидишь себя со стороны.",
         "action": "Запиши три строки: победа, ошибка, план на завтра."},
    ],
}


def lesson_of_the_day(focus, today):
    """Alternates days between the user's focus track and the other tracks."""
    track = FOCUS_TRACK.get(focus, "discipline")
    mine = LESSONS[track]
    others = [(t, l) for t in TRACK_ORDER if t != track for l in LESSONS[t]]
    n = today.toordinal()
    if n % 2 == 0:
        t, lesson = track, mine[(n // 2) % len(mine)]
    else:
        t, lesson = others[(n // 2) % len(others)]
    return {"track": t, "track_label": TRACK_LABELS[t], **lesson}