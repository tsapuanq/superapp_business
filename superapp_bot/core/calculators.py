def calculate_budget(income: float, expenses: list[float]) -> dict:
    total_expenses = sum(expenses)
    remaining = income - total_expenses
    save_10 = remaining * 0.10
    save_20 = remaining * 0.20
    save_30 = remaining * 0.30
    return {
        "income": income,
        "total_expenses": total_expenses,
        "remaining": remaining,
        "save_10_percent": save_10,
        "save_20_percent": save_20,
        "save_30_percent": save_30,
        "annual_save_20": save_20 * 12,
    }


def calculate_mortgage(price: float, down_payment: float, years: int, rate_percent: float) -> dict:
    loan = price - down_payment
    monthly_rate = rate_percent / 100 / 12
    n = years * 12
    if monthly_rate == 0:
        monthly = loan / n
    else:
        monthly = loan * monthly_rate * (1 + monthly_rate) ** n / ((1 + monthly_rate) ** n - 1)
    total_paid = monthly * n
    overpayment = total_paid - loan
    return {
        "loan_amount": round(loan),
        "monthly_payment": round(monthly),
        "total_paid": round(total_paid),
        "overpayment": round(overpayment),
        "years": years,
        "rate_percent": rate_percent,
    }


def calculate_savings_goal(goal: float, monthly_save: float, rate_percent: float = 0) -> dict:
    if monthly_save <= 0:
        return {"error": "monthly_save must be > 0"}
    if rate_percent > 0:
        monthly_rate = rate_percent / 100 / 12
        months = 0
        accumulated = 0.0
        while accumulated < goal and months < 1200:
            accumulated = accumulated * (1 + monthly_rate) + monthly_save
            months += 1
    else:
        months = int(goal / monthly_save) + (1 if goal % monthly_save else 0)
    years = months // 12
    rem_months = months % 12
    return {
        "goal": goal,
        "monthly_save": monthly_save,
        "months_needed": months,
        "years": years,
        "remaining_months": rem_months,
        "total_deposited": round(monthly_save * months),
    }


def calculate_ip_tax(income: float, regime: str = "упрощёнка") -> dict:
    """Упрощённый расчёт налогов ИП в Казахстане."""
    if regime == "упрощёнка":
        tax_rate = 0.03
        tax = income * tax_rate
        social = 3 * 14 * min(income, 1000000) / 100 / 12
        pension = income * 0.10
        return {
            "regime": "Упрощённая декларация (3%)",
            "income": income,
            "income_tax": round(tax),
            "social_contribution": round(social),
            "pension_contribution": round(pension),
            "total_to_pay": round(tax + social + pension),
            "net_income": round(income - tax - social - pension),
        }
    else:
        tax = income * 0.01
        return {
            "regime": "Патент (1%)",
            "income": income,
            "income_tax": round(tax),
            "net_income": round(income - tax),
        }


TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "calculate_budget",
            "description": "Считает остаток бюджета и сколько можно откладывать. Используй когда пользователь называет доход и расходы.",
            "parameters": {
                "type": "object",
                "properties": {
                    "income": {"type": "number", "description": "Ежемесячный доход в тенге"},
                    "expenses": {
                        "type": "array",
                        "items": {"type": "number"},
                        "description": "Список расходов в тенге (аренда, кредит, продукты и т.д.)"
                    },
                },
                "required": ["income", "expenses"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calculate_mortgage",
            "description": "Считает ежемесячный платёж по ипотеке/кредиту. Используй когда пользователь спрашивает про ипотеку или кредит с конкретными суммами.",
            "parameters": {
                "type": "object",
                "properties": {
                    "price":        {"type": "number", "description": "Стоимость недвижимости/товара в тенге"},
                    "down_payment": {"type": "number", "description": "Первоначальный взнос в тенге"},
                    "years":        {"type": "integer", "description": "Срок кредита в годах"},
                    "rate_percent": {"type": "number", "description": "Годовая процентная ставка, например 14.5"},
                },
                "required": ["price", "down_payment", "years", "rate_percent"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calculate_savings_goal",
            "description": "Считает за сколько месяцев накопить нужную сумму. Используй когда пользователь хочет накопить на что-то конкретное.",
            "parameters": {
                "type": "object",
                "properties": {
                    "goal":         {"type": "number", "description": "Целевая сумма в тенге"},
                    "monthly_save": {"type": "number", "description": "Сколько откладывать в месяц"},
                    "rate_percent": {"type": "number", "description": "Годовая ставка депозита (если есть), по умолчанию 0"},
                },
                "required": ["goal", "monthly_save"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calculate_ip_tax",
            "description": "Считает налоги ИП в Казахстане. Используй когда пользователь-предприниматель спрашивает сколько платить налогов.",
            "parameters": {
                "type": "object",
                "properties": {
                    "income":  {"type": "number", "description": "Ежемесячный доход ИП в тенге"},
                    "regime":  {"type": "string", "description": "Налоговый режим: 'упрощёнка' или 'патент'", "enum": ["упрощёнка", "патент"]},
                },
                "required": ["income"],
            },
        },
    },
]


def call_tool(name: str, args: dict) -> dict:
    if name == "calculate_budget":
        return calculate_budget(**args)
    elif name == "calculate_mortgage":
        return calculate_mortgage(**args)
    elif name == "calculate_savings_goal":
        return calculate_savings_goal(**args)
    elif name == "calculate_ip_tax":
        return calculate_ip_tax(**args)
    return {"error": f"unknown tool: {name}"}
