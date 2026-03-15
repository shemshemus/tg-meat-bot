from app.config import settings
from app.models.models import Product


# ──────────────────────────────────────────────
# Rule-based generator (always available)
# ──────────────────────────────────────────────

TEMPLATES: dict[str, dict[str, str]] = {
    "friendly": {
        "en": (
            "Hey there! Have you tried our {name}? "
            "Made with {ingredients} — only {price} per kg! "
            "{description} "
            "Come grab some while it's fresh!"
        ),
        "ru": (
            "Привет! Вы уже пробовали наш {name}? "
            "Приготовлено из {ingredients} — всего {price} за кг! "
            "{description} "
            "Заходите, пока свежее!"
        ),
    },
    "professional": {
        "en": (
            "Introducing {name} from our {category} collection. "
            "{description} "
            "Crafted with quality ingredients: {ingredients}. "
            "Available at {price}/kg."
        ),
        "ru": (
            "Представляем {name} из нашей коллекции {category}. "
            "{description} "
            "Изготовлено из качественных ингредиентов: {ingredients}. "
            "Цена: {price}/кг."
        ),
    },
    "funny": {
        "en": (
            "Your taste buds called — they're BEGGING for our {name}! "
            "We packed it with {ingredients} so you don't have to. "
            "Just {price}/kg. {description} "
            "Seriously, your fridge is judging you for not having this yet."
        ),
        "ru": (
            "Ваши вкусовые рецепторы звонят — они УМОЛЯЮТ попробовать наш {name}! "
            "Мы добавили {ingredients}, чтобы вам не пришлось. "
            "Всего {price}/кг. {description} "
            "Серьёзно, ваш холодильник уже осуждает вас за отсутствие этого!"
        ),
    },
    "urgent": {
        "en": (
            "LIMITED STOCK: {name} — only {price}/kg! "
            "{description} "
            "Made with {ingredients}. "
            "Don't miss out — order now before it's gone!"
        ),
        "ru": (
            "ОГРАНИЧЕННЫЙ ЗАПАС: {name} — всего {price}/кг! "
            "{description} "
            "Состав: {ingredients}. "
            "Не упустите — закажите, пока не разобрали!"
        ),
    },
}


def generate_rule_based(product: Product, tone: str, language: str = "ru") -> str:
    """Generate marketing text using string templates."""
    tone_templates = TEMPLATES.get(tone, TEMPLATES["friendly"])
    template = tone_templates.get(language, tone_templates["ru"])
    return template.format(
        name=product.name,
        category=product.category,
        price=f"{product.price_per_kg:,.0f} ₸",
        description=product.description or "A premium product from our kitchen.",
        ingredients=product.ingredients or "the finest ingredients",
    )


# ──────────────────────────────────────────────
# OpenAI generator (optional, used when API key is set)
# ──────────────────────────────────────────────

LANGUAGE_INSTRUCTIONS = {
    "ru": "Напиши ТОЛЬКО текст рекламы на русском языке, без кавычек и пометок.",
    "en": "Write ONLY the ad text in English, no quotes or labels.",
}


def generate_with_ai(product: Product, tone: str, language: str = "ru") -> str:
    """Generate marketing text using OpenAI. Falls back to rule-based on error."""
    try:
        from openai import OpenAI

        client = OpenAI(api_key=settings.openai_api_key)

        lang_label = "Russian" if language == "ru" else "English"
        instruction = LANGUAGE_INSTRUCTIONS.get(language, LANGUAGE_INSTRUCTIONS["ru"])

        prompt = (
            f"Write a short marketing post (2-3 sentences) for a food product in {lang_label}.\n"
            f"Product: {product.name}\n"
            f"Category: {product.category}\n"
            f"Price: {product.price_per_kg:,.0f} ₸/kg\n"
            f"Description: {product.description}\n"
            f"Ingredients: {product.ingredients}\n"
            f"Tone: {tone}\n\n"
            f"{instruction}"
        )

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=200,
            temperature=0.8,
        )

        return response.choices[0].message.content.strip()

    except Exception:
        # Any failure → fall back to rule-based
        return generate_rule_based(product, tone, language)


def generate_post(product: Product, tone: str, language: str = "ru") -> str:
    """Main entry point. Uses AI if available, otherwise rule-based."""
    if settings.openai_api_key:
        return generate_with_ai(product, tone, language)
    return generate_rule_based(product, tone, language)
