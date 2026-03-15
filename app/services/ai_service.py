from app.config import settings
from app.models.models import Product


# ──────────────────────────────────────────────
# Rule-based generator (always available)
# ──────────────────────────────────────────────

TEMPLATES: dict[str, str] = {
    "friendly": (
        "Hey there! Have you tried our {name}? "
        "Made with {ingredients} — only {price} per kg! "
        "{description} "
        "Come grab some while it's fresh!"
    ),
    "professional": (
        "Introducing {name} from our {category} collection. "
        "{description} "
        "Crafted with quality ingredients: {ingredients}. "
        "Available at {price}/kg."
    ),
    "funny": (
        "Your taste buds called — they're BEGGING for our {name}! "
        "We packed it with {ingredients} so you don't have to. "
        "Just {price}/kg. {description} "
        "Seriously, your fridge is judging you for not having this yet."
    ),
    "urgent": (
        "LIMITED STOCK: {name} — only {price}/kg! "
        "{description} "
        "Made with {ingredients}. "
        "Don't miss out — order now before it's gone!"
    ),
}


def generate_rule_based(product: Product, tone: str) -> str:
    """Generate marketing text using string templates."""
    template = TEMPLATES.get(tone, TEMPLATES["friendly"])
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

def generate_with_ai(product: Product, tone: str) -> str:
    """Generate marketing text using OpenAI. Falls back to rule-based on error."""
    try:
        from openai import OpenAI

        client = OpenAI(api_key=settings.openai_api_key)

        prompt = (
            f"Write a short marketing post (2-3 sentences) for a food product.\n"
            f"Product: {product.name}\n"
            f"Category: {product.category}\n"
            f"Price: {product.price_per_kg:,.0f} ₸/kg\n"
            f"Description: {product.description}\n"
            f"Ingredients: {product.ingredients}\n"
            f"Tone: {tone}\n\n"
            f"Write ONLY the ad text, no quotes or labels."
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
        return generate_rule_based(product, tone)


def generate_post(product: Product, tone: str) -> str:
    """Main entry point. Uses AI if available, otherwise rule-based."""
    if settings.openai_api_key:
        return generate_with_ai(product, tone)
    return generate_rule_based(product, tone)
