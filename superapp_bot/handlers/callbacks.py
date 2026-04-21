import json

from db.state import user_state, user_histories
from db.database import record_feedback, log_event
from integrations.telegram_api import tg_post, answer_callback
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


def _replace_feedback_button(cb: dict, label: str):
    tg_post("editMessageReplyMarkup", {
        "chat_id": cb["message"]["chat"]["id"],
        "message_id": cb["message"]["message_id"],
        "reply_markup": json.dumps({"inline_keyboard": [[{"text": label, "callback_data": "noop"}]]}),
    })
