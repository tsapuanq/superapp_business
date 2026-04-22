import re

from config import ADMIN_ID
from db.state import user_state, user_histories
from db.database import delete_user, load_users, category_boost, get_user_count, get_wishlist, update_wishlist
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
        "/calc — калькуляторы (бюджет, ипотека, накопления, налоги ИП)\n"
        "/wishlist — финансовые цели и накопления\n"
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


def cmd_calc(chat_id: int):
    send_message(chat_id,
        "🧮 Калькуляторы SuperApp\n\n"
        "Просто напиши запрос с цифрами — я посчитаю сам:\n\n"
        "💰 Бюджет:\n«Зарплата 350к, аренда 120к, еда 60к, транспорт 20к»\n\n"
        "🏠 Ипотека:\n«Квартира 25 млн, взнос 5 млн, 15 лет, ставка 14%»\n\n"
        "🎯 Накопления:\n«Хочу накопить 3 млн, откладываю 80к в месяц»\n\n"
        "📋 Налоги ИП:\n«Доход 500к в месяц, упрощёнка»\n\n"
        "Задавай вопрос 👇"
    )


def cmd_wishlist(chat_id: int, user_id: int, args: str = ""):
    """
    /wishlist             — показать цели
    /wishlist Машина 5000000  — добавить цель
    /wishlist del 1       — удалить цель по номеру
    """
    goals = get_wishlist(user_id)

    if args.startswith("del "):
        try:
            idx = int(args[4:].strip()) - 1
            removed = goals.pop(idx)
            update_wishlist(user_id, goals)
            send_message(chat_id, f"Цель «{removed['name']}» удалена ✅")
        except (ValueError, IndexError):
            send_message(chat_id, "Укажи номер цели, например: /wishlist del 1")
        return

    if args:
        # Normalize shorthand amounts (handles "5млн", "5 млн", "5.5 млн")
        normalized = re.sub(r'(\d+(?:\.\d+)?)\s*млрд', lambda m: str(int(float(m.group(1)) * 1_000_000_000)), args)
        normalized = re.sub(r'(\d+(?:\.\d+)?)\s*млн',  lambda m: str(int(float(m.group(1)) * 1_000_000)), normalized)
        normalized = re.sub(r'(\d+(?:\.\d+)?)\s*тыс',  lambda m: str(int(float(m.group(1)) * 1_000)), normalized)
        # Split: everything before last number = name, last number = target
        m = re.search(r'^(.*?)\s*(\d+(?:\.\d+)?)\s*$', normalized.strip())
        if m and m.group(1).strip():
            name = m.group(1).strip()
            try:
                target = float(m.group(2))
                goals.append({"name": name, "target": target, "saved": 0})
                update_wishlist(user_id, goals)
                send_message(chat_id,
                    f"Цель «{name}» добавлена 🎯\n"
                    f"Нужно накопить: {int(target):,}₸\n\n"
                    f"Чтобы посчитать план накоплений — напиши:\n"
                    f"«Хочу накопить {int(target):,}₸, могу откладывать X тенге в месяц»"
                )
                return
            except ValueError:
                pass
        send_message(chat_id, "Формат: /wishlist <Название> <Сумма>\nПримеры:\n/wishlist Машина 5000000\n/wishlist Квартира 30млн")
        return

    if not goals:
        send_message(chat_id,
            "📋 Wishlist пустой\n\n"
            "Добавь финансовую цель:\n"
            "/wishlist Машина 5000000\n"
            "/wishlist Квартира 30000000\n"
            "/wishlist Отпуск 500000"
        )
        return

    lines = ["📋 Твои финансовые цели:\n"]
    for i, g in enumerate(goals, 1):
        target = int(g["target"])
        saved = int(g.get("saved", 0))
        pct = int(saved / target * 100) if target else 0
        bar = "█" * (pct // 10) + "░" * (10 - pct // 10)
        lines.append(f"{i}. {g['name']} — {target:,}₸")
        lines.append(f"   [{bar}] {pct}% накоплено\n")
    lines.append("Удалить: /wishlist del <номер>")
    lines.append("Добавить: /wishlist <Название> <Сумма>")
    send_message(chat_id, "\n".join(lines))


def cmd_reset(chat_id: int, user_id: int):
    delete_user(user_id)
    user_state.pop(user_id, None)
    user_histories.pop(user_id, None)
    send_message(chat_id, "Профиль удалён. Напиши /start чтобы начать заново.")


def cmd_clear(chat_id: int, user_id: int):
    user_histories.pop(user_id, None)
    send_message(chat_id, "История диалога очищена ✅ Профиль сохранён. Задавай новый вопрос 👇")
