from config import ADMIN_ID
from db.state import user_state, user_histories
from db.database import delete_user, load_users, category_boost, get_user_count
from core.datalake import target_categories, get_lake
from integrations.telegram_api import send_message
from core.ai import restore_session
from .survey import send_survey_question, get_starter_questions


def cmd_start(chat_id: int, user_id: int, username: str):
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
        send_message(chat_id,
            f"Привет, {username}! 👋\n\n"
            "Я — AI-ассистент SuperApp Казахстана 🇰🇿\n\n"
            "Помогаю с реальными финансовыми вопросами:\n"
            "🧮 Считаю бюджет, ипотеку, накопления, налоги ИП\n"
            "💬 Объясняю банковские продукты простым языком\n"
            "🎯 Даю советы под твою ситуацию — не шаблонные\n\n"
            "Например, можешь спросить:\n"
            "— «Зарплата 350к, аренда 100к — сколько могу откладывать?»\n"
            "— «Как открыть ИП и сколько платить налогов?»\n"
            "— «За сколько накоплю 5 млн если откладывать 50к в месяц?»\n\n"
            "Чтобы советы были точными — отвечу на 6 быстрых вопросов 👇\n"
            "Займёт меньше минуты."
        )
        send_survey_question(chat_id, 0, user_id)


def cmd_help(chat_id: int):
    send_message(chat_id,
        "Что я умею:\n\n"
        "Отвечаю на вопросы по банкингу, финансам и сервисам SuperApp KZ\n\n"
        "Команды:\n"
        "/start — начать или вернуться\n"
        "/profile — посмотреть профиль\n"
        "/stats — статистика персонализации\n"
        "/clear — очистить историю диалога (профиль остаётся)\n"
        "/reset — сбросить профиль полностью\n"
        "/help — эта справка\n\n"
        "Просто напиши свой вопрос 👇"
    )


def cmd_profile(chat_id: int, user_id: int):
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


def cmd_stats(chat_id: int, user_id: int):
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


def cmd_admin(chat_id: int, user_id: int):
    if user_id == ADMIN_ID:
        count = get_user_count()
        send_message(chat_id, f"🔐 Админ-панель\n👥 Всего пользователей в базе: {count}")
    else:
        send_message(chat_id, "Команда не найдена.")


def cmd_reset(chat_id: int, user_id: int):
    delete_user(user_id)
    user_state.pop(user_id, None)
    user_histories.pop(user_id, None)
    send_message(chat_id, "Профиль удалён. Напиши /start чтобы начать заново.")


def cmd_clear(chat_id: int, user_id: int):
    user_histories.pop(user_id, None)
    send_message(chat_id, "История диалога очищена ✅ Профиль сохранён. Задавай новый вопрос 👇")
