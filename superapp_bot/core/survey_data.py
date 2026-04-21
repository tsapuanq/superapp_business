CITIES = [
    "Алматы", "Астана", "Шымкент",
    "Караганда", "Актобе", "Атырау",
    "Тараз", "Павлодар", "Семей",
    "Кызылорда", "Костанай", "Кокшетау",
    "Актау", "Уральск", "Туркестан",
    "Петропавловск", "Экибастуз", "Усть-Каменогорск",
    "Другой",
]

SURVEY = [
    {
        "key": "age_group",
        "type": "single",
        "question": "1️⃣ Ваш возраст?",
        "options": ["16–25", "26–35", "36–45", "46+"],
    },
    {
        "key": "employment",
        "type": "single",
        "question": "2️⃣ Ваша занятость?",
        "options": [
            "Работаю (найм)",
            "Свой бизнес / ИП",
            "Студент / школьник",
            "Фриланс / самозанятый",
            "Пенсионер",
            "Безработный",
        ],
    },
    {
        "key": "main_goal",
        "type": "single",
        "question": "3️⃣ Главная цель прямо сейчас?",
        "options": [
            "💰 Финансы и накопления",
            "📈 Развить бизнес / ИП",
            "💼 Карьера и доход",
            "🛒 Покупки и желания",
            "👨‍👩‍👧 Семья и стабильность",
        ],
    },
    {
        "key": "has_family",
        "type": "single",
        "question": "4️⃣ Есть ли у тебя семья или дети?",
        "options": ["Да", "Нет / пока нет"],
    },
    {
        "key": "city",
        "type": "city",
        "question": "5️⃣ Ваш город?",
        "options": CITIES,
    },
    {
        "key": "interests",
        "type": "multiselect",
        "question": "6️⃣ Что тебя интересует? Выбери всё подходящее и нажми ✅ Готово",
        "options": [
            ("BUSINESS_GROWTH", "📈 Бизнес и рост"),
            ("FINANCE",         "💰 Финансы"),
            ("WISHLIST",        "🛒 Покупки и вишлист"),
            ("CAREER",          "💼 Карьера"),
            ("EDUCATION",       "📚 Обучение"),
            ("FAMILY",          "👨‍👩‍👧 Семья"),
            ("HEALTH",          "🏥 Здоровье"),
            ("FITNESS",         "🏃 Спорт / активность"),
            ("GIG_ECONOMY",     "💻 Фриланс"),
        ],
    },
]

VALID_ANSWERS = {
    q["key"]: set(q["options"])
    for q in SURVEY if q["type"] in ("single", "city")
}

PROFILE_CATEGORIES = {
    "Свой бизнес / ИП":        ["BUSINESS_GROWTH", "FINANCE", "GIG_ECONOMY"],
    "Фриланс / самозанятый":   ["GIG_ECONOMY", "CAREER", "FINANCE"],
    "Студент / школьник":      ["EDUCATION", "CAREER", "WISHLIST"],
    "Пенсионер":               ["HEALTH", "FAMILY", "FINANCE"],
    "Безработный":             ["GIG_ECONOMY", "CAREER", "FINANCE"],
    "Работаю (найм)":          ["CAREER", "FINANCE", "WISHLIST"],
}

AGE_CATEGORIES = {
    "16–25": ["EDUCATION", "CAREER", "WISHLIST"],
    "26–35": ["FINANCE", "CAREER", "BUSINESS_GROWTH"],
    "36–45": ["BUSINESS_GROWTH", "FINANCE", "FAMILY"],
    "46+":   ["FINANCE", "HEALTH", "FAMILY"],
}

GOAL_CATEGORIES = {
    "💰 Финансы и накопления":   ["FINANCE"],
    "📈 Развить бизнес / ИП":    ["BUSINESS_GROWTH", "FINANCE"],
    "💼 Карьера и доход":        ["CAREER", "GIG_ECONOMY"],
    "🛒 Покупки и желания":      ["WISHLIST"],
    "👨‍👩‍👧 Семья и стабильность": ["FAMILY", "FINANCE"],
}
