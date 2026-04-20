import json

from config import ADMIN_ID
from survey_data import SURVEY, VALID_ANSWERS
from state import user_state, user_histories
from database import (
    save_user, delete_user, load_users,
    record_feedback, category_boost, get_user_count,
)
from datalake import target_categories, get_lake
from telegram_api import tg_post, send_message, send_with_feedback, answer_callback
from ai import get_ai_reply, restore_session


# ─── Survey UI helpers ────────────────────────────────────────────────────────

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
    state = user_state[user_id]
    answers = state.get("answers", {})
    interests = sorted(state.get("selected_interests", set()))
    if interests:
        answers["interests"] = interests
    save_user(user_id, username, answers)
    state["step"] = "done"

    starters = get_starter_questions(answers)
    send_message(
        chat_id,
        f"Профиль сохранён ✅\n\nЯ готов помогать! Задай мне любой вопрос, например:\n\n"
        f"{starters}\n\nЖду твой вопрос 👇",
        reply_markup={"remove_keyboard": True},
    )


# ─── Survey flow ──────────────────────────────────────────────────────────────

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


# ─── Callback query handler ───────────────────────────────────────────────────

def handle_callback_query(cb: dict):
    user_id = cb["from"]["id"]
    chat_id = cb["message"]["chat"]["id"]
    data = cb.get("data", "")

    if data.startswith("toggle_"):
        cat_key = data[len("toggle_"):]
        state = user_state.setdefault(user_id, {})
        selected = state.setdefault("selected_interests", set())
        if cat_key in selected:
            selected.discard(cat_key)
        else:
            selected.add(cat_key)
        kb = build_interests_keyboard(selected)
        tg_post("editMessageReplyMarkup", {
            "chat_id": chat_id,
            "message_id": cb["message"]["message_id"],
            "reply_markup": json.dumps(kb),
        })
        answer_callback(cb["id"])
        return

    if data == "interests_done":
        state = user_state.get(user_id, {})
        step = state.get("step")
        ms_idx = next(i for i, q in enumerate(SURVEY) if q["type"] == "multiselect")
        if step == ms_idx:
            selected = state.get("selected_interests", set())
            if not selected:
                tg_post("answerCallbackQuery", {
                    "callback_query_id": cb["id"],
                    "text": "Выбери хотя бы один интерес! 👆",
                    "show_alert": True,
                })
                return
            tg_post("editMessageReplyMarkup", {
                "chat_id": chat_id,
                "message_id": cb["message"]["message_id"],
                "reply_markup": json.dumps({"inline_keyboard": []}),
            })
            next_step = ms_idx + 1
            username = state.get("username", "")
            if next_step < len(SURVEY):
                state["step"] = next_step
                send_survey_question(chat_id, next_step, user_id)
            else:
                finish_survey(chat_id, user_id, username)
        answer_callback(cb["id"])
        return

    if data == "fb_like":
        record_feedback(user_id, liked=True)
        user_histories.pop(user_id, None)
        tg_post("editMessageReplyMarkup", {
            "chat_id": chat_id,
            "message_id": cb["message"]["message_id"],
            "reply_markup": json.dumps({"inline_keyboard": [[{"text": "✅ Спасибо за оценку!", "callback_data": "noop"}]]}),
        })
    elif data == "fb_dislike":
        record_feedback(user_id, liked=False)
        user_histories.pop(user_id, None)
        tg_post("editMessageReplyMarkup", {
            "chat_id": chat_id,
            "message_id": cb["message"]["message_id"],
            "reply_markup": json.dumps({"inline_keyboard": [[{"text": "📝 Учту, покажу другое", "callback_data": "noop"}]]}),
        })

    answer_callback(cb["id"])


# ─── Message handler ──────────────────────────────────────────────────────────

def handle_message(msg: dict):
    chat_id = msg["chat"]["id"]
    user_id = msg["from"]["id"]
    username = msg["from"].get("username") or msg["from"].get("first_name", "")
    text = msg.get("text", "").strip()

    if not text:
        send_message(chat_id, "Извини, я умею читать только текстовые сообщения 📝 Пожалуйста, напиши свой вопрос текстом.")
        return

    if text == "/start":
        if restore_session(user_id):
            saved = load_users().get(str(user_id), {})
            starters = get_starter_questions(saved.get("profile", {}))
            send_message(
                chat_id,
                f"С возвращением! Твой профиль загружен ✅\n\n"
                f"Я — твой AI-ассистент. Могу помочь с финансами, бизнесом или покупками.\n\n"
                f"Спроси меня о чём угодно, например:\n\n{starters}\n\n"
                f"Задавай вопрос 👇"
            )
        else:
            user_state[user_id] = {"step": 0, "answers": {}, "username": username, "selected_interests": set()}
            send_message(chat_id, "Привет! Я AI-ассистент SuperApp 🇰🇿\n\nНесколько вопросов чтобы настроить под тебя 👇")
            send_survey_question(chat_id, 0, user_id)
        return

    if text == "/help":
        send_message(chat_id,
            "Что я умею:\n\n"
            "Отвечаю на вопросы по банкингу, финансам и сервисам SuperApp KZ\n\n"
            "Команды:\n"
            "/start — начать или вернуться\n"
            "/profile — посмотреть профиль\n"
            "/stats — статистика персонализации\n"
            "/reset — сбросить профиль\n"
            "/help — эта справка\n\n"
            "Просто напиши свой вопрос 👇"
        )
        return

    if text == "/profile":
        saved = load_users().get(str(user_id))
        if saved:
            p = saved["profile"]
            label_map = {
                "age_group": "Возраст", "employment": "Занятость",
                "main_goal": "Цель", "has_family": "Семья",
                "city": "Город", "interests": "Интересы",
            }
            lines = []
            for k, v in p.items():
                label = label_map.get(k, k)
                val = ", ".join(v) if isinstance(v, list) else v
                lines.append(f"  {label}: {val}")
            cats = target_categories(p)
            lines.append(f"\nАктивные категории: {', '.join(cats)}")
            send_message(chat_id, "Твой профиль:\n" + "\n".join(lines) + "\n\nЧтобы обновить — /reset затем /start")
        else:
            send_message(chat_id, "Профиль не найден. Напиши /start")
        return

    if text == "/stats":
        saved = load_users().get(str(user_id))
        if not saved:
            send_message(chat_id, "Профиль не найден. Напиши /start")
            return
        fb = saved.get("feedback", {})
        boosts = category_boost(user_id)
        cats = target_categories(saved.get("profile", {}))
        lines = [f"📊 Твоя статистика персонализации:\n"]
        lines.append(f"Активные категории: {', '.join(cats)}\n")
        if fb:
            lines.append("Фидбэк:")
            for cat, counts in fb.items():
                boost_val = boosts.get(cat, 1.0)
                arrow = "🔼" if boost_val > 1.0 else ("🔽" if boost_val < 1.0 else "➖")
                lines.append(
                    f"  {cat}: 👍{counts.get('likes',0)} 👎{counts.get('dislikes',0)} "
                    f"→ вес ×{boost_val:.2f} {arrow}"
                )
        else:
            lines.append("Пока нет оценок — нажимай 👍/👎 под ответами!")
        total_lake = sum(len(rows) for rows in get_lake().values())
        lines.append(f"\nData Lake: {total_lake} триггеров в {len(get_lake())} нодах")
        send_message(chat_id, "\n".join(lines))
        return

    if text == "/admin":
        if user_id == ADMIN_ID:
            count = get_user_count()
            send_message(chat_id, f"🔐 Админ-панель\n👥 Всего пользователей в базе: {count}")
        else:
            send_message(chat_id, "Команда не найдена.")
        return

    if text == "/reset":
        delete_user(user_id)
        user_state.pop(user_id, None)
        user_histories.pop(user_id, None)
        send_message(chat_id, "Профиль удалён. Напиши /start чтобы начать заново.")
        return

    state = user_state.get(user_id)
    if state and state.get("step") not in (None, "done"):
        handle_survey(chat_id, user_id, text)
        return

    if not state or user_id not in user_histories:
        if not restore_session(user_id):
            send_message(chat_id, "Напиши /start чтобы начать 👋")
            return

    from config import groq_clients
    if not groq_clients:
        send_message(chat_id, "⚠️ GROQ_API_KEY не настроен.")
        return

    reply = get_ai_reply(user_id, text)
    send_with_feedback(chat_id, reply)
