import json
import requests

from config import TG_API


def tg_post(method: str, payload: dict, timeout: int = 5):
    try:
        requests.post(f"{TG_API}/{method}", json=payload, timeout=timeout)
    except Exception:
        pass


def send_message(chat_id: int, text: str, reply_markup=None):
    payload = {"chat_id": chat_id, "text": text}
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)
    tg_post("sendMessage", payload)


def send_with_feedback(chat_id: int, text: str):
    kb = {"inline_keyboard": [[
        {"text": "👍 Полезно", "callback_data": "fb_like"},
        {"text": "👎 Не то",  "callback_data": "fb_dislike"},
    ]]}
    send_message(chat_id, text, reply_markup=kb)


def answer_callback(callback_id: str):
    tg_post("answerCallbackQuery", {"callback_query_id": callback_id})
