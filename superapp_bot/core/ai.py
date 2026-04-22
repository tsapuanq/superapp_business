import json
import re
import time

from config import groq_clients
from db.state import user_state, user_histories
from db.database import (
    load_users, save_user,
    _context_lock, _dirty_context, flush_context_if_needed,
)
from .datalake import target_categories, match_prompts_to_query, pick_triggers
from .calculators import TOOLS_SCHEMA, call_tool

MAX_HISTORY_USERS = 200

_FUNC_TAG_RE = re.compile(r"<function=[^>]+>.*?</function>", re.DOTALL)


def _strip_function_tags(text: str) -> str:
    """Remove raw <function=...>...</function> blobs that 8b model leaks into text."""
    return _FUNC_TAG_RE.sub("", text).strip()


def _evict_histories_if_needed():
    if len(user_histories) > MAX_HISTORY_USERS:
        to_evict = list(user_histories.keys())[:50]
        for uid in to_evict:
            user_histories.pop(uid, None)


# ─── System prompt ────────────────────────────────────────────────────────────

def build_system_prompt(profile: dict, user_id: int = 0, users: dict | None = None) -> str:
    triggers = pick_triggers(profile, user_id=user_id, users=users)
    cats = target_categories(profile)

    by_cat: dict[str, list[str]] = {}
    for t in triggers:
        cat = t.get("Category_Tag", "OTHER")
        prompt_text = str(t.get("NLP_Prompt", "")).strip()
        if prompt_text:
            by_cat.setdefault(cat, []).append(prompt_text)

    rec_block = ""
    for cat in cats:
        lines = by_cat.get(cat, [])
        if lines:
            rec_block += f"\n[{cat}]\n" + "\n".join(f"- {l}" for l in lines[:4])

    profile_str = "\n".join(f"- {k}: {v}" for k, v in profile.items()) if profile else "не заполнен"

    employment = profile.get("employment", "")
    age_group = profile.get("age_group", "")
    if employment == "Свой бизнес / ИП":
        persona = (
            "Пользователь — действующий предприниматель или ИП. "
            "Приоритет: расчётный счёт, налоги ИП, кредиты на развитие, B2B-инструменты, OKR."
        )
    elif employment == "Фриланс / самозанятый":
        persona = (
            "Пользователь — фрилансер или самозанятый. "
            "Приоритет: управление нерегулярным доходом, налоги самозанятого, GIG-платформы, финансовая подушка."
        )
    elif employment == "Студент / школьник":
        persona = (
            "Пользователь — студент или школьник БЕЗ собственного бизнеса и стабильного дохода. "
            "Приоритет: первая карта, кэшбэк, подработки, стипендия, образовательные цели."
        )
    elif employment == "Пенсионер":
        persona = (
            "Пользователь — пенсионер. "
            "Приоритет: соцвыплаты, простые переводы, здоровье, семейные расходы, понятные инструменты. "
            "Избегай слишком сложных финансовых продуктов и жаргона, если не просят прямо."
        )
    elif employment == "Безработный":
        persona = (
            "Пользователь ищет работу или подработку, дохода нет или минимальный. "
            "Приоритет: GIG-сервисы, карьерные цели, микрокредиты, экономия."
        )
    elif employment == "Работаю (найм)":
        persona = (
            "Пользователь — наёмный работник со стабильным доходом. "
            "Приоритет: накопления, потребительские кредиты, карьерный рост, wishlist."
        )
    elif age_group == "16–25":
        persona = (
            "Молодой пользователь, скорее всего без опыта в финансах. "
            "Приоритет: кэшбэк, первые накопления, wishlist, карьерный старт."
        )
    else:
        persona = "Приоритет: переводы, кредиты, накопления, повседневные платежи."

    return f"""Ты — AI-ассистент SuperApp Казахстана. Работаешь в Telegram.

Профиль пользователя:
{profile_str}

{persona}

Приоритетные категории для этого пользователя: {', '.join(cats)}

Персонализированные рекомендации из Data Lake (отобраны по профилю, Priority_Score ≥ 3.5):
{rec_block if rec_block else 'Нет данных — отвечай на основе общих знаний о SuperApp KZ'}

Правила:
- Отвечай по теме: банкинг, финансы, сервисы SuperApp, ИП/бизнес, wishlist, OKR, карьера, недвижимость (ипотека, накопления на жильё, оценка бюджета)
- Если вопрос совсем не по теме (погода, политика, развлечения) — мягко переводи: "Это вне моей специализации, но если есть финансовый вопрос — с удовольствием помогу 😊"
- На приветствия ("привет", "спасибо", "окей") отвечай по-человечески и коротко, не вставляй шаблон про SuperApp
- Определяй язык по сообщению пользователя (русский / казахский / английский) и отвечай на нём
- ОБЯЗАТЕЛЬНО: если в сообщении есть блок [CONTEXT] — используй эти данные как ГЛАВНЫЙ источник. Адаптируй под вопрос, не цитируй дословно. Данные из блока [CONTEXT] приоритетнее раздела "Рекомендации" выше.
- Отвечай КОНКРЕТНО и КОРОТКО — максимум 3-5 предложений. Никаких вводных абзацев.
- Если пользователь просит конкретные варианты (квартир, машин, товаров), а их нет в данных — не отвечай сухо "Нет вариантов". Вежливо объясни, что ты не доска объявлений, но можешь помочь с финансовой стороной (как накопить, какую ипотеку взять и т.д.).
- Не выдумывай продукты которых нет в данных
- Ты информационный AI-ассистент — объясняешь, советуешь, отвечаешь на вопросы. Не оформляешь кредиты, переводы и любые операции. Если просят оформить — скажи: "Я информационный ассистент, оформление не в моих возможностях. Могу рассказать об условиях или помочь разобраться с вопросом."
- Никогда не упоминай "приложение в разработке", "когда SuperApp будет запущен" и подобные фразы — это демо-прототип, не превью реального продукта
- Никогда не запрашивай: доход, номер карты, ИИН, пароли
- ВАЖНО — понимай сокращения и суммы: млн = миллион, тыс = тысяча, млрд = миллиард. Анализируй масштаб суммы! 130 млн тенге = 130 000 000 тенге ≈ $260 000 — это БОЛЬШОЙ бюджет. НЕ говори "ограниченный бюджет" если сумма > 10 млн тенге. Ориентиры: средняя зарплата в КЗ ~350 000₸, квартира в Алматы ~30-80 млн₸.
- КАЛЬКУЛЯТОР: вызывай функции расчёта ТОЛЬКО если пользователь назвал конкретные числа. Если чисел нет — спроси их у пользователя простым вопросом, НЕ вызывай функцию с текстом вместо чисел.

РЕЖИМ ЭКСПЕРТА (ДЛЯ ПРЕЗЕНТАЦИИ/ЖЮРИ):
Если вопрос явно про продукт-менеджмент, юнит-экономику или оценку эффективности продукта (например: "как замерить retention", "что такое CAC", "объясни LTV", "как оценить product-market fit") — отвечай как Senior Product Manager.
Используй метрики: Retention, Churn Rate, CAC (у нас 120 тенге), LTV, DAU/MAU, CTR, Approval rate, NPS.
ЗАПРЕЩЕНО давать словарные определения. Всегда показывай причинно-следственную связь через цифры.
Если вопрос просто про "маркетинг своего ИП" или "как продвигать бизнес" — отвечай как обычный бизнес-советник, без метрик.
"""


# ─── AI reply ─────────────────────────────────────────────────────────────────

def get_ai_reply(user_id: int, user_msg: str) -> str:
    _evict_histories_if_needed()
    users = load_users()

    if user_id not in user_histories:
        saved = users.get(str(user_id))
        profile = saved.get("profile", {}) if saved else {}
        user_histories[user_id] = [{"role": "system", "content": build_system_prompt(profile, user_id, users=users)}]

    profile = user_state.get(user_id, {}).get("answers", {})
    cats = target_categories(profile)

    matched, dominant_cat = match_prompts_to_query(user_msg, profile, user_id=user_id)
    top_cat = dominant_cat if dominant_cat else (cats[0] if cats else "FINANCE")
    user_state.setdefault(user_id, {})["last_top_cat"] = top_cat

    with _context_lock:
        _dirty_context[str(user_id)] = {
            "category": top_cat,
            "ts": int(time.time()),
        }
    flush_context_if_needed()

    if matched:
        hint = "Тематические подсказки из Data Lake (направление ответа, не факты):\n"
        hint += "\n".join(f"- {p}" for p in matched)
        hint += (
            "\n\nВАЖНО: используй только общее направление этих подсказок. "
            "НЕ цитируй конкретные цифры, сроки или факты которых ты не знаешь "
            "о пользователе ('15 минут в графике', 'на 10% дешевле', 'ваш лимит' и т.п.). "
            "Если подсказка содержит такие данные — перефразируй в общий совет."
        )
        enriched_msg = f"{user_msg}\n\n[CONTEXT]{hint}[/CONTEXT]"
    else:
        enriched_msg = user_msg

    user_histories[user_id].append({"role": "user", "content": enriched_msg})
    convo = user_histories[user_id][1:][-6:]
    messages = [user_histories[user_id][0]] + convo

    FALLBACK_MODELS = ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"]

    reply = "Сервис под высокой нагрузкой. Попробуй задать вопрос ещё раз."
    found = False
    for model_name in FALLBACK_MODELS:
        for i, client in enumerate(groq_clients):
            try:
                print(f"[GROQ] {model_name} key#{i}")
                # Only 70b supports function calling reliably
                tools = TOOLS_SCHEMA if "70b" in model_name else None
                resp = client.chat.completions.create(
                    model=model_name,
                    messages=messages,
                    max_tokens=512,
                    temperature=0.7,
                    **({"tools": tools, "tool_choice": "auto"} if tools else {}),
                )
                msg = resp.choices[0].message

                # Handle function call
                if tools and msg.tool_calls:
                    tool_results = []
                    invalid = False
                    for tc in msg.tool_calls:
                        args = json.loads(tc.function.arguments)
                        has_invalid = any(
                            isinstance(v, str)
                            for v in args.values()
                            if not isinstance(v, list)
                        )
                        if has_invalid:
                            print(f"[TOOL] skipped {tc.function.name} — non-numeric args")
                            invalid = True
                            break
                        result = call_tool(tc.function.name, args)
                        print(f"[TOOL] {tc.function.name}({args}) → {result}")
                        tool_results.append({
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": json.dumps(result, ensure_ascii=False),
                        })

                    if invalid or not tool_results:
                        # Model tried to call tool without numbers — use text reply as-is
                        reply = msg.content or "Уточни пожалуйста — назови конкретные суммы, и я посчитаю."
                    else:
                        followup = client.chat.completions.create(
                            model=model_name,
                            messages=messages + [msg] + tool_results,
                            max_tokens=512,
                            temperature=0.7,
                        )
                        reply = followup.choices[0].message.content
                else:
                    reply = msg.content

                from db.database import log_event
                print(f"[GROQ] ✅ {model_name} key#{i}")
                uname = user_state.get(user_id, {}).get("username", "")
                log_event(user_id, "bot_reply", reply, {"model": model_name, "key_index": i}, username=uname)
                found = True
                break
            except Exception as e:
                err = str(e)
                if "429" in err or "rate limit" in err.lower() or "400" in err:
                    print(f"[GROQ] 429/400 {model_name} key#{i} → next key")
                    continue
                else:
                    print(f"[GROQ] Error {model_name} key#{i}: {e}")
                    break
        if found:
            break

    reply = _strip_function_tags(reply)
    user_histories[user_id].append({"role": "assistant", "content": reply})
    return reply


def restore_session(user_id: int) -> bool:
    users = load_users()
    saved = users.get(str(user_id))
    if not saved:
        return False
    profile = saved["profile"]
    user_state[user_id] = {"step": "done", "answers": profile}
    return True
