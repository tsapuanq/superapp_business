# SuperApp KZ — Telegram Bot

AI-ассистент SuperApp Казахстана. Персонализирует ответы на основе профиля пользователя и Data Lake.

---

## Структура проекта

```
superapp_bot/
│
├── bot.py                  ← Точка входа. Flask app + все маршруты
├── config.py               ← Env vars, пути, Groq клиенты
│
├── core/                   ← Бизнес-логика
│   ├── ai.py               ← Groq API, system prompt, get_ai_reply
│   ├── datalake.py         ← Загрузка JSON, NLP-матчинг, pick_triggers
│   └── survey_data.py      ← Вопросы опроса, категории, маппинги
│
├── db/                     ← Работа с данными
│   ├── database.py         ← PostgreSQL CRUD (Supabase). Пул соединений
│   └── state.py            ← Общая память процесса (user_state, user_histories)
│
├── handlers/               ← Обработка входящих сообщений
│   ├── __init__.py         ← Экспорт handle_message, handle_callback_query
│   ├── survey.py           ← UI и flow опроса, quick-темы после анкеты
│   ├── commands.py         ← /start /help /profile /stats /admin /reset /calc /wishlist /clear
│   ├── callbacks.py        ← Inline-кнопки (лайки, интересы, quick-темы, wishlist, calc-goal)
│   └── router.py           ← Роутер входящих сообщений, pending_calc flow
│
├── integrations/           ← Внешние API
│   └── telegram_api.py     ← Обёртки над Telegram Bot API
│
├── data/
│   └── datalake_json/      ← JSON файлы с триггерами (Finance, Career и т.д.)
│
├── requirements.txt        ← Зависимости Python
├── Procfile                ← Команда запуска для Render
└── render.yaml             ← Конфиг деплоя Render
```

---

## Как работает бот

```
Пользователь пишет сообщение
        ↓
Telegram → POST /BOT_TOKEN → Flask (bot.py)
        ↓
Flask мгновенно возвращает 200 OK
        ↓
Фоновый поток обрабатывает сообщение:
  ├─ Новый пользователь → опрос → quick-темы (handlers/survey.py)
  ├─ Команда /start /help /profile /calc /wishlist /clear → handlers/commands.py
  ├─ Inline-кнопка → handlers/callbacks.py
  └─ Вопрос → pending_calc? → core/ai.py → Groq API → ответ + кнопки
```

### Как JSON из Data Lake попадают в LLM

```
data/datalake_json/*.json
        ↓ (загрузка при старте, TTL-кэш 5 мин)
core/datalake.py: match_prompts_to_query()
        ↓ (NLP word-boundary матчинг по словам пользователя)
pick_triggers()
        ↓ (фильтр по профилю: возраст, город, цели + boost по фидбэку)
core/ai.py: build_system_prompt() + get_ai_reply()
        ↓ (триггеры в system prompt + [CONTEXT] блок в сообщении)
Groq API
```

---

## Переменные окружения

| Переменная | Описание |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Токен бота от @BotFather |
| `GROQ_API_KEYS` | Ключи Groq через запятую: `key1,key2,key3` |
| `DATABASE_URL` | PostgreSQL URI из Supabase (Transaction Pooler) |
| `WEBHOOK_URL` | `https://твой-бот.onrender.com/BOT_TOKEN` |
| `PUSH_SECRET` | Секрет для защиты `/send_pushes` |

> **Важно:** `DATABASE_URL` должен быть из **Transaction Pooler** в Supabase (порт 6543, IPv4-совместимый). Render Free не поддерживает IPv6.

---

## Локальный запуск

```bash
# 1. Установить зависимости
pip install -r requirements.txt

# 2. Создать .env файл
TELEGRAM_BOT_TOKEN=...
GROQ_API_KEYS=key1,key2,key3
DATABASE_URL=postgresql://postgres.xxx:[password]@aws-0-eu-central-1.pooler.supabase.com:6543/postgres
WEBHOOK_URL=...
PUSH_SECRET=...

# 3. Запустить
python bot.py
```

---

## Деплой на Render

1. Залить проект на GitHub
2. Render → New Web Service → подключить репо (Configure account → дать доступ к репо)
3. Settings → **Root Directory**: `superapp_bot`
4. Добавить все env vars из таблицы выше
5. Render использует `Procfile` автоматически:
   ```
   gunicorn -w 1 --threads 8 -b 0.0.0.0:$PORT bot:app
   ```
6. После деплоя зайти на `/set_webhook` — Telegram зарегистрирует URL

> **Auto-deploy:** После подключения репо Render автоматически деплоит при каждом `git push` в ветку `main`.

---

## Supabase (база данных)

1. Создать проект на [supabase.com](https://supabase.com)
2. Connect → Transaction Pooler → скопировать URI (порт 6543)
3. Вставить в `DATABASE_URL`
4. Таблица `users` создаётся автоматически при первом запуске (`init_db()`)

Схема таблицы:
```sql
CREATE TABLE users (
    user_id      BIGINT PRIMARY KEY,
    username     TEXT    DEFAULT '',
    profile      TEXT    DEFAULT '{}',
    feedback     TEXT    DEFAULT '{}',
    last_context TEXT,
    push_history TEXT    DEFAULT '[]',
    wishlist     TEXT    DEFAULT '[]'
);
```

---

## Функциональность бота

### Персонализация
- При первом запуске бот проводит анкету (6 вопросов): возраст, занятость, цель, семья, город, интересы
- После анкеты показывает inline-кнопки с релевантными темами (по профилю)
- Ответы AI фильтруются через Data Lake с учётом профиля и фидбэка (👍/👎)

### Калькуляторы (`/calc`)
Распознаёт запросы с цифрами и считает:
- **Бюджет** — `«Зарплата 350к, аренда 120к, еда 60к»`
- **Ипотека** — `«Квартира 25 млн, взнос 5 млн, 15 лет, ставка 14%»`
- **Накопления** — `«Хочу накопить 3 млн, откладываю 80к в месяц»`
- **Налоги ИП** — `«Доход 500к в месяц, упрощёнка»`

### Wishlist (`/wishlist`)
Финансовые цели с отслеживанием прогресса:

| Команда | Действие |
|---|---|
| `/wishlist` | Показать все цели с прогресс-баром |
| `/wishlist Машина 5000000` | Добавить цель (поддерживает `5млн`, `500тыс`) |
| `/wishlist saved 1 50000` | Обновить накопленную сумму |
| `/wishlist del 1` | Удалить цель |

После добавления цели бот предлагает кнопку **"📊 Рассчитать план накоплений"** — юзер вводит ежемесячную сумму, AI считает срок. После расчёта появляются кнопки **"🔄 Пересчитать"** и **"📋 Мои цели"**.

---

## Отказоустойчивость Groq

Бот автоматически переключается между ключами и моделями при ошибке 429 (rate limit):

```
GROQ_API_KEYS=key1,key2,key3
```

Порядок fallback: `llama-3.3-70b-versatile` → `llama-3.1-8b-instant`, по каждому ключу.

---

## cron-job.org (чтобы Render не засыпал)

Render Free засыпает после 15 минут без запросов. Создать два задания на [cron-job.org](https://cron-job.org):

| Задание | URL | Расписание |
|---|---|---|
| Keep-alive | `https://твой-бот.onrender.com/` | каждые 14 минут |
| Пуш-рассылка | `https://твой-бот.onrender.com/send_pushes?key=SECRET` | раз в день (`0 10 * * *`) |

---

## API маршруты

| Маршрут | Метод | Описание |
|---|---|---|
| `/{BOT_TOKEN}` | POST | Webhook от Telegram |
| `/set_webhook` | GET | Зарегистрировать webhook в Telegram |
| `/reload` | GET | Перезагрузить datalake_json из файлов |
| `/send_pushes?key=` | GET | Запустить пуш-рассылку |
| `/` | GET | Health check (keep-alive) |

---

## Обновление Data Lake

Данные лежат в `data/datalake_json/*.json`. Чтобы обновить:

1. Изменить JSON файлы
2. Сделать `git push` (Render передеплоит автоматически)
3. Или вызвать `/reload` без редеплоя (перечитает файлы с диска)
