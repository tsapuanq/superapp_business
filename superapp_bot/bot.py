"""
bot.py — entry point.

Run locally:   python bot.py
Render:        gunicorn -w 1 --threads 8 -b 0.0.0.0:$PORT bot:app
"""

import os
import threading

import requests
from flask import Flask, request

from config import BOT_TOKEN, TG_API, WEBHOOK_URL
from db.database import init_db, migrate_json, load_users, flush_context_if_needed, update_push_history, get_user_count
from handlers import handle_callback_query, handle_message

# ─── App ──────────────────────────────────────────────────────────────────────

app = Flask(__name__)

init_db()
migrate_json()


# ─── Background processing ────────────────────────────────────────────────────

def _process_update(update: dict):
    try:
        if "callback_query" in update:
            handle_callback_query(update["callback_query"])
        elif "message" in update:
            handle_message(update["message"])
    except Exception as e:
        print(f"[ERROR] _process_update: {e}")


# ─── Webhook ──────────────────────────────────────────────────────────────────

@app.route(f"/{BOT_TOKEN}", methods=["POST"])
def webhook():
    update = request.get_json(force=True, silent=True)
    if not update:
        return "ok"
    threading.Thread(target=_process_update, args=(update,), daemon=True).start()
    return "ok"


# ─── Utility routes ───────────────────────────────────────────────────────────

@app.route("/set_webhook")
def set_webhook():
    r = requests.get(f"{TG_API}/setWebhook?url={WEBHOOK_URL}")
    return r.json()


@app.route("/reload")
def reload_lake():
    import core.datalake as datalake
    import time
    datalake._lake_cache = datalake.load_lake()
    datalake._lake_loaded_at = time.time()
    total = sum(len(rows) for rows in datalake._lake_cache.values())
    return {"status": "ok", "nodes": len(datalake._lake_cache), "total_rows": total}


@app.route("/send_pushes")
def send_pushes():
    flush_context_if_needed(force=True)
    secret = request.args.get("key", "")
    expected = os.environ.get("PUSH_SECRET", "change_me_123")
    if secret != expected:
        return {"error": "unauthorized"}, 403

    from push_sender import pick_push, send_push
    users = load_users()
    if not users:
        return {"status": "no users"}

    sent, failed = 0, 0
    for uid, entry in users.items():
        profile = entry.get("profile", {})
        feedback = entry.get("feedback", {})
        last_context = entry.get("last_context")
        sent_history = entry.get("push_history", [])
        push_text = pick_push(profile, feedback, last_context, sent_history)
        if send_push(int(uid), push_text):
            sent += 1
            update_push_history(int(uid), (sent_history + [push_text])[-10:])
        else:
            failed += 1

    return {"status": "ok", "sent": sent, "failed": failed}


@app.route("/")
def index():
    return "SuperApp KZ Bot is running"


# ─── Local dev ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app.run(debug=True)
