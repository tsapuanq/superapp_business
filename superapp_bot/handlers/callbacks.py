import json

from db.state import user_state, user_histories
from db.database import record_feedback, log_event, get_wishlist, update_wishlist
from integrations.telegram_api import tg_post, answer_callback, send_typing, send_with_feedback, send_message
from core.survey_data import SURVEY
from .survey import build_interests_keyboard, finish_survey, send_survey_question


def handle_callback_query(cb: dict):
    user_id = cb["from"]["id"]
    chat_id = cb["message"]["chat"]["id"]
    data = cb.get("data", "")

    if data.startswith("toggle_"):
        _handle_toggle(cb, user_id, chat_id, data)
        return

    if data == "interests_done":
        _handle_interests_done(cb, user_id, chat_id)
        return

    if data.startswith("quick_q_"):
        _handle_quick_question(cb, user_id, chat_id, data)
        return

    if data.startswith("save_goal_"):
        _handle_save_goal(cb, user_id, chat_id, data)
        return

    username = user_state.get(user_id, {}).get("username", "")
    if data == "fb_like":
        record_feedback(user_id, liked=True)
        user_histories.pop(user_id, None)
        log_event(user_id, "feedback", "like", username=username)
        _replace_feedback_button(cb, "✅ Спасибо за оценку!")
    elif data == "fb_dislike":
        record_feedback(user_id, liked=False)
        user_histories.pop(user_id, None)
        log_event(user_id, "feedback", "dislike", username=username)
        _replace_feedback_button(cb, "📝 Учту, покажу другое")

    answer_callback(cb["id"])


def _handle_toggle(cb: dict, user_id: int, chat_id: int, data: str):
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


def _handle_interests_done(cb: dict, user_id: int, chat_id: int):
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


def _handle_quick_question(cb: dict, user_id: int, chat_id: int, data: str):
    from core.ai import get_ai_reply, restore_session
    from .survey import get_starter_buttons
    from db.database import load_users, get_wishlist
    answer_callback(cb["id"])
    # Remove buttons so user can't tap twice
    tg_post("editMessageReplyMarkup", {
        "chat_id": chat_id,
        "message_id": cb["message"]["message_id"],
        "reply_markup": json.dumps({"inline_keyboard": []}),
    })
    question = user_state.get(user_id, {}).get("quick_questions", {}).get(data)
    # Fallback: reconstruct from profile if state was lost (e.g. server restart)
    if not question:
        try:
            idx = int(data[len("quick_q_"):])
            profile = load_users().get(str(user_id), {}).get("profile", {})
            # Only reconstruct if profile is real (not empty after /reset)
            if profile.get("employment"):
                buttons = get_starter_buttons(profile)
                if 0 <= idx < len(buttons):
                    question = buttons[idx][1]
                    restore_session(user_id)  # repopulate user_state so AI sees real profile
        except ValueError:
            pass
    if not question:
        send_message(chat_id, "Напиши свой вопрос 👇")
        return
    send_typing(chat_id)
    reply = get_ai_reply(user_id, question)
    send_with_feedback(chat_id, reply)
    # Offer to save savings goal to wishlist (check against real wishlist, survives restarts)
    pending = user_state.get(user_id, {}).pop("pending_wishlist", None)
    if pending and pending.get("goal"):
        goal_amount = int(pending["goal"])
        goals = get_wishlist(user_id)
        if not any(int(g.get("target", 0)) == goal_amount for g in goals):
            kb = {"inline_keyboard": [[
                {"text": "💾 Сохранить цель в Wishlist", "callback_data": f"save_goal_{goal_amount}"},
            ]]}
            send_message(chat_id, "Хочешь сохранить эту цель в Wishlist?", reply_markup=kb)


def _handle_save_goal(cb: dict, user_id: int, chat_id: int, data: str):
    answer_callback(cb["id"])
    try:
        amount = float(data[len("save_goal_"):])
    except ValueError:
        return
    goals = get_wishlist(user_id)
    name = f"Накопление {int(amount):,}₸".replace(",", " ")
    goals.append({"name": name, "target": amount, "saved": 0})
    update_wishlist(user_id, goals)
    tg_post("editMessageReplyMarkup", {
        "chat_id": chat_id,
        "message_id": cb["message"]["message_id"],
        "reply_markup": json.dumps({"inline_keyboard": [[{"text": f"✅ Сохранено в Wishlist", "callback_data": "noop"}]]}),
    })
    send_message(chat_id,
        f"Цель «{name}» добавлена в Wishlist 🎯\n"
        f"Посмотреть: /wishlist\n"
        f"Обновить прогресс: /wishlist saved 1 <сумма>"
    )


def _replace_feedback_button(cb: dict, label: str):
    tg_post("editMessageReplyMarkup", {
        "chat_id": cb["message"]["chat"]["id"],
        "message_id": cb["message"]["message_id"],
        "reply_markup": json.dumps({"inline_keyboard": [[{"text": label, "callback_data": "noop"}]]}),
    })
