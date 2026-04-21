from config import groq_clients
from db.state import user_state, user_histories
from db.database import log_event
from core.ai import get_ai_reply, restore_session
from integrations.telegram_api import send_message, send_with_feedback
from .survey import handle_survey
from .commands import cmd_start, cmd_help, cmd_profile, cmd_stats, cmd_admin, cmd_reset

_COMMANDS = {
    "/start":   lambda chat_id, user_id, username: cmd_start(chat_id, user_id, username),
    "/help":    lambda chat_id, user_id, username: cmd_help(chat_id),
    "/profile": lambda chat_id, user_id, username: cmd_profile(chat_id, user_id),
    "/stats":   lambda chat_id, user_id, username: cmd_stats(chat_id, user_id),
    "/admin":   lambda chat_id, user_id, username: cmd_admin(chat_id, user_id),
    "/reset":   lambda chat_id, user_id, username: cmd_reset(chat_id, user_id),
}


def handle_message(msg: dict):
    chat_id = msg["chat"]["id"]
    user_id = msg["from"]["id"]
    username = msg["from"].get("username") or msg["from"].get("first_name", "")
    text = msg.get("text", "").strip()

    if not text:
        send_message(chat_id, "Извини, я умею читать только текстовые сообщения 📝 Пожалуйста, напиши свой вопрос текстом.")
        return

    log_event(user_id, "user_message", text, {"username": username})

    if text in _COMMANDS:
        log_event(user_id, "command", text)
        _COMMANDS[text](chat_id, user_id, username)
        return

    state = user_state.get(user_id)
    if state and state.get("step") not in (None, "done"):
        handle_survey(chat_id, user_id, text)
        return

    if not state or user_id not in user_histories:
        if not restore_session(user_id):
            send_message(chat_id, "Напиши /start чтобы начать 👋")
            return

    if not groq_clients:
        send_message(chat_id, "⚠️ GROQ_API_KEY не настроен.")
        return

    reply = get_ai_reply(user_id, text)
    send_with_feedback(chat_id, reply)
