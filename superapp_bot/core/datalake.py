import json
import re
import time

from config import LAKE_DIR
from .survey_data import PROFILE_CATEGORIES, AGE_CATEGORIES, GOAL_CATEGORIES

# ─── Lake cache ───────────────────────────────────────────────────────────────

_lake_cache: dict | None = None
_lake_loaded_at: float = 0
LAKE_TTL = 300


def load_lake() -> dict[str, list[dict]]:
    lake = {}
    for f in LAKE_DIR.glob("*.json"):
        raw = json.loads(f.read_text(encoding="utf-8"))
        node_key = f.stem
        if isinstance(raw, list):
            rows = raw
        elif isinstance(raw, dict):
            rows = []
            for v in raw.values():
                if isinstance(v, list):
                    rows.extend(v)
        else:
            rows = []
        lake[node_key] = [r for r in rows if isinstance(r, dict)]
    return lake


def get_lake() -> dict[str, list[dict]]:
    global _lake_cache, _lake_loaded_at
    if _lake_cache is None or (time.time() - _lake_loaded_at) > LAKE_TTL:
        _lake_cache = load_lake()
        _lake_loaded_at = time.time()
    return _lake_cache


# ─── Profile → categories ─────────────────────────────────────────────────────

def target_categories(profile: dict) -> list[str]:
    cats = []
    cats += PROFILE_CATEGORIES.get(profile.get("employment", ""), [])
    cats += AGE_CATEGORIES.get(profile.get("age_group", ""), [])
    cats += GOAL_CATEGORIES.get(profile.get("main_goal", ""), [])
    if profile.get("has_family") == "Да":
        cats.append("FAMILY")
    interests = profile.get("interests", [])
    if isinstance(interests, list):
        cats = interests + cats
    seen: set = set()
    result = []
    for c in cats:
        if c not in seen:
            seen.add(c)
            result.append(c)
    return result or ["FINANCE", "CAREER"]


def is_eligible(row: dict, profile: dict) -> bool:
    eco = row.get("Ecological_Filter") or {}
    if not eco:
        return True
    age_map = {"16–25": 20, "26–35": 30, "36–45": 40, "46+": 50}
    user_age = age_map.get(profile.get("age_group", ""), 25)
    if eco.get("min_age") and user_age < eco["min_age"]:
        return False
    if eco.get("max_age") and user_age > eco["max_age"]:
        return False
    return True


# ─── NLP matching ─────────────────────────────────────────────────────────────

_RU_SUFFIXES = sorted([
    "ами", "ями", "ого", "его", "ому", "ему", "ыми", "ими",
    "ов", "ев", "ей", "ий", "ой", "ый", "ая", "яя", "ое", "ее",
    "ом", "ем", "ах", "ях", "ые", "ие", "ую", "юю",
    "ть", "ся", "ет", "ит", "ут", "ют", "ал", "ил", "ла", "ли",
    "ка", "ки", "ку", "ке", "ок", "ек", "ик",
    "ам", "ям",
    "ия", "ию",
    "а", "о", "у", "е", "и", "ы", "й", "я", "ю",
], key=len, reverse=True)


def ru_stem(word: str) -> str:
    for s in _RU_SUFFIXES:
        if len(word) - len(s) >= 3 and word.endswith(s):
            return word[:-len(s)]
    return word


def match_prompts_to_query(
    user_msg: str,
    profile: dict,
    user_id: int = 0,
    top_n: int = 3,
) -> tuple[list[str], str]:
    lake = get_lake()
    msg_lower = user_msg.lower()

    stop = {"я", "мне", "как", "что", "это", "на", "в", "с", "и", "а", "но", "для",
            "по", "от", "до", "не", "или", "мой", "свой", "себе", "чтобы", "хочу",
            "могу", "буду", "есть", "быть", "также", "можно", "нужно"}
    raw_words = {w.strip("?.!,;") for w in msg_lower.split() if len(w) > 2 and w not in stop}
    stems = set()
    for w in raw_words:
        stems.add(w)
        stems.add(ru_stem(w))

    if not stems:
        return [], ""

    profile_cats = set(target_categories(profile))
    seen_texts = set()
    scored = []
    cat_hits: dict[str, float] = {}

    for node_rows in lake.values():
        for r in node_rows:
            prompt_text = str(r.get("NLP_Prompt", "")).strip()
            if not prompt_text or prompt_text in seen_texts:
                continue
            prompt_lower = prompt_text.lower()
            hits = sum(1 for w in stems if re.search(r'\b' + re.escape(w), prompt_lower))
            if hits > 0:
                base = hits * float(r.get("Priority_Score") or 1)
                cat = r.get("Category_Tag", "")
                affinity = 2.0 if cat in profile_cats else 1.0
                eff = base * affinity
                scored.append((eff, prompt_text, cat))
                seen_texts.add(prompt_text)
                cat_hits[cat] = cat_hits.get(cat, 0) + eff

    scored.sort(key=lambda x: x[0], reverse=True)
    top_cat = max(cat_hits, key=cat_hits.get) if cat_hits else ""
    return [text for _, text, _ in scored[:top_n]], top_cat


def pick_triggers(
    profile: dict,
    user_id: int = 0,
    per_node: int = 3,
    users: dict | None = None,
) -> list[dict]:
    from db.database import category_boost
    lake = get_lake()
    cats = target_categories(profile)
    cat_set = set(cats)
    boosts = category_boost(user_id, users=users) if user_id else {}
    results = []

    for node, rows in lake.items():
        eligible = [
            r for r in rows
            if r.get("Category_Tag") in cat_set and is_eligible(r, profile)
        ]
        scored = [
            (float(r.get("Priority_Score") or 0) * boosts.get(r.get("Category_Tag", ""), 1.0), r)
            for r in eligible
        ]
        scored.sort(key=lambda x: x[0], reverse=True)
        results.extend(scored[:per_node])

    results.sort(key=lambda x: x[0], reverse=True)
    return [r for _, r in results[:24]]
