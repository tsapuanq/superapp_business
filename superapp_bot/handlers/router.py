from config import groq_clients
from db.state import user_state, user_histories
from db.database import log_event
from core.ai import get_ai_reply, restore_session
from integrations.telegram_api import send_message, send_with_feedback, send_typing
from .survey import handle_survey
from .commands import cmd_start, cmd_help, cmd_profile, cmd_stats, cmd_admin, cmd_reset, cmd_clear, cmd_calc, cmd_wishlist

_COMMANDS = {
    "/start":   lambda chat_id, user_id, username, args="": cmd_start(chat_id, user_id, username),
    "/help":    lambda chat_id, user_id, username, args="": cmd_help(chat_id),
    "/profile": lambda chat_id, user_id, username, args="": cmd_profile(chat_id, user_id),
    "/stats":   lambda chat_id, user_id, username, args="": cmd_stats(chat_id, user_id),
    "/admin":   lambda chat_id, user_id, username, args="": cmd_admin(chat_id, user_id),
    "/reset":   lambda chat_id, user_id, username, args="": cmd_reset(chat_id, user_id),
    "/clear":   lambda chat_id, user_id, username, args="": cmd_clear(chat_id, user_id),
    "/calc":    lambda chat_id, user_id, username, args="": cmd_calc(chat_id),
    "/wishlist": lambda chat_id, user_id, username, args="": cmd_wishlist(chat_id, user_id, args),
}


def handle_message(msg: dict):
    chat_id = msg["chat"]["id"]
    user_id = msg["from"]["id"]
    username = msg["from"].get("username") or msg["from"].get("first_name", "")
    text = msg.get("text", "").strip()

    if not text:
        send_message(chat_id, "Извини, я умею читать только текстовые сообщения 📝 Пожалуйста, напиши свой вопрос текстом.")
        return

    log_event(user_id, "user_message", text, username=username)

    cmd_parts = text.split(" ", 1)
    cmd_key = cmd_parts[0]
    cmd_args = cmd_parts[1] if len(cmd_parts) > 1 else ""
    if cmd_key in _COMMANDS:
        log_event(user_id, "command", text, username=username)
        _COMMANDS[cmd_key](chat_id, user_id, username, cmd_args)
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

    send_typing(chat_id)
    reply = get_ai_reply(user_id, text)
    send_with_feedback(chat_id, reply)

    # Offer to save savings goal to wishlist
    pending = user_state.get(user_id, {}).pop("pending_wishlist", None)
    if pending and pending.get("goal"):
        goal_amount = int(pending["goal"])
        kb = {"inline_keyboard": [[
            {"text": "💾 Сохранить цель в Wishlist", "callback_data": f"save_goal_{goal_amount}"},
        ]]}
        send_message(chat_id, "Хочешь сохранить эту цель в Wishlist?", reply_markup=kb)
