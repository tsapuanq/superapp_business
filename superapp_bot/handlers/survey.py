from core.survey_data import SURVEY, VALID_ANSWERS
from db.state import user_state, user_histories
from db.database import save_user
from integrations.telegram_api import send_message


def build_interests_keyboard(selected: set) -> dict:
    ms_step = next(q for q in SURVEY if q["type"] == "multiselect")
    opts = ms_step["options"]
    rows = []
    for i in range(0, len(opts), 2):
        row = []
        for cat_key, label in opts[i:i+2]:
            icon = "✅" if cat_key in selected else "◻️"
            row.append({"text": f"{icon} {label}", "callback_data": f"toggle_{cat_key}"})
        rows.append(row)
    rows.append([{"text": "✅ Готово — сохранить выбор", "callback_data": "interests_done"}])
    return {"inline_keyboard": rows}


def send_survey_question(chat_id: int, step: int, user_id: int = 0):
    q = SURVEY[step]
    if q["type"] == "multiselect":
        selected = user_state.get(user_id, {}).get("selected_interests", set())
        kb = build_interests_keyboard(selected)
        send_message(chat_id, q["question"], reply_markup={"remove_keyboard": True})
        send_message(chat_id, "👇 Нажми на интересы:", reply_markup=kb)
    elif q["type"] == "city":
        opts = q["options"]
        rows = [opts[i:i+3] for i in range(0, len(opts), 3)]
        kb = {"keyboard": [[{"text": c} for c in row] for row in rows],
              "resize_keyboard": True, "one_time_keyboard": True}
        send_message(chat_id, q["question"], reply_markup=kb)
    else:
        kb = {"keyboard": [[{"text": o}] for o in q["options"]],
              "resize_keyboard": True, "one_time_keyboard": True}
        send_message(chat_id, q["question"], reply_markup=kb)


def get_starter_questions(profile: dict) -> str:
    emp = profile.get("employment", "")
    if emp == "Свой бизнес / ИП":
        return "🔹 Какие налоги у ИП?\n🔹 Как увеличить оборот бизнеса?\n🔹 Как выбрать расчётный счёт?"
    elif emp == "Студент / школьник":
        return "🔹 Как начать копить со стипендии?\n🔹 Какую карту выбрать студенту?\n🔹 Как работает кэшбэк?"
    elif emp == "Фриланс / самозанятый":
        return "🔹 Как платить налоги самозанятому?\n🔹 Как копить при нестабильном доходе?\n🔹 Куда вложить первые накопления?"
    elif emp == "Пенсионер":
        return "🔹 Как защититься от мошенников в интернете?\n🔹 Есть ли льготы на переводы?\n🔹 Как сохранить сбережения от инфляции?"
    else:
        return "🔹 Как начать инвестировать?\n🔹 Как выгоднее копить на квартиру?\n🔹 На что влияет кредитная история?"


def finish_survey(chat_id: int, user_id: int, username: str):
    from core.ai import build_system_prompt
    state = user_state[user_id]
    answers = state.get("answers", {})
    interests = sorted(state.get("selected_interests", set()))
    if interests:
        answers["interests"] = interests
    save_user(user_id, username, answers)
    state["step"] = "done"
    if user_id in user_histories:
        user_histories[user_id][0] = {"role": "system", "content": build_system_prompt(answers, user_id)}

    starters = get_starter_questions(answers)
    send_message(
        chat_id,
        f"Профиль сохранён ✅\n\nЯ готов помогать! Задай мне любой вопрос, например:\n\n"
        f"{starters}\n\nЖду твой вопрос 👇",
        reply_markup={"remove_keyboard": True},
    )


def handle_survey(chat_id: int, user_id: int, text: str):
    state = user_state[user_id]
    step = state["step"]
    q = SURVEY[step]

    if q["type"] == "multiselect":
        selected = user_state.get(user_id, {}).get("selected_interests", set())
        kb = build_interests_keyboard(selected)
        send_message(chat_id, "👇 Нажми на интересы:", reply_markup=kb)
        return

    if text not in VALID_ANSWERS.get(q["key"], set()):
        send_message(chat_id, "Пожалуйста, выбери один из вариантов 👇")
        send_survey_question(chat_id, step, user_id)
        return

    state["answers"][q["key"]] = text
    next_step = step + 1
    if next_step < len(SURVEY):
        state["step"] = next_step
        send_survey_question(chat_id, next_step, user_id)
    else:
        finish_survey(chat_id, user_id, state.get("username", ""))
