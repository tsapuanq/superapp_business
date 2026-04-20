# SuperApp KZ — Telegram Bot

AI-ассистент SuperApp Казахстана. Персонализирует ответы на основе профиля пользователя и Data Lake.

---

## Структура проекта

```
superapp_bot/
│
├── bot.py            ← Точка входа. Flask app + все маршруты
├── config.py         ← Env vars, пути, Groq клиенты
├── state.py          ← Общая память процесса (user_state, user_histories)
│
├── database.py       ← PostgreSQL CRUD (Supabase). Пул соединений
├── datalake.py       ← Загрузка JSON, NLP-матчинг, pick_triggers
├── survey_data.py    ← Вопросы опроса, категории, маппинги
│
├── ai.py             ← Groq API, system prompt, get_ai_reply
├── handlers.py       ← Обработка сообщений и inline-кнопок
├── telegram_api.py   ← Обёртки над Telegram Bot API
│
├── datalake_json/    ← JSON файлы с триггерами (Finance, Career и т.д.)
│
├── requirements.txt  ← Зависимости Python
├── Procfile          ← Команда запуска для Render
└── render.yaml       ← Конфиг деплоя Render
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
  ├─ Новый пользователь → опрос (survey_data.py + handlers.py)
  ├─ Команда /start /help /profile → handlers.py
  └─ Вопрос → ai.py → Groq API → ответ пользователю
```

---

## Переменные окружения

| Переменная | Описание |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Токен бота от @BotFather |
| `GROQ_API_KEYS` | Ключи Groq через запятую: `key1,key2,key3` |
| `DATABASE_URL` | PostgreSQL URI из Supabase |
| `WEBHOOK_URL` | `https://твой-бот.onrender.com/BOT_TOKEN` |
| `PUSH_SECRET` | Секрет для защиты `/send_pushes` |

---

## Локальный запуск

```bash
# 1. Установить зависимости
pip install -r requirements.txt

# 2. Создать .env файл
TELEGRAM_BOT_TOKEN=...
GROQ_API_KEYS=...
DATABASE_URL=...
WEBHOOK_URL=...
PUSH_SECRET=...

# 3. Запустить
python bot.py
```

---

## Деплой на Render

1. Залить проект на GitHub
2. Render → New Web Service → подключить репо
3. Добавить все env vars из таблицы выше
4. Render автоматически использует `Procfile`:
   ```
   gunicorn -w 1 --threads 4 -b 0.0.0.0:$PORT bot:app
   ```
5. После деплоя зайти на `/set_webhook` — Telegram зарегистрирует URL

---

## Supabase (база данных)

1. Создать проект на [supabase.com](https://supabase.com)
2. Settings → Database → Connection string → URI
3. Скопировать в `DATABASE_URL`
4. Таблица создаётся автоматически при первом запуске (`init_db()`)

---

## cron-job.org (чтобы Render не засыпал)

Создать два задания на [cron-job.org](https://cron-job.org) бесплатно:

| Задание | URL | Расписание |
|---|---|---|
| Keep-alive | `https://твой-бот.onrender.com/` | каждые 14 минут |
| Пуш-рассылка | `https://твой-бот.onrender.com/send_pushes?key=SECRET` | раз в день (например `0 10 * * *`) |

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

Данные лежат в `datalake_json/*.json`. Чтобы обновить:

1. Изменить JSON файлы
2. Сделать git push (Render передеплоит автоматически)
3. Или вызвать `/reload` без редеплоя (перечитает файлы с диска)
