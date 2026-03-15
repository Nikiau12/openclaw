from __future__ import annotations

import json
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
OFFER_PATH = BASE_DIR / "offer.txt"
EXAMPLES_PATH = BASE_DIR / "examples" / "examples.json"
OUTPUT_DIR = BASE_DIR / "output"


def load_offer() -> str:
    return OFFER_PATH.read_text(encoding="utf-8").strip()


def load_examples() -> list[dict]:
    data = json.loads(EXAMPLES_PATH.read_text(encoding="utf-8"))
    if not isinstance(data, list) or not data:
        raise ValueError("examples.json must contain a non-empty list")
    return data


def make_telegram_post(offer: str, examples: list[dict]) -> str:
    lines = [
        "MarketAnalyst AI",
        "",
        "Я сделал Telegram-бота для быстрой криптоаналитики.",
        "Он помогает быстрее понять рынок без часов ручного анализа.",
        "",
        "Что умеет:",
        "- быстро разбирать BTC, ETH и альты",
        "- давать понятную рыночную картину простым языком",
        "- помогать отсеивать шум",
        "",
        "Примеры запросов:",
    ]
    for ex in examples[:3]:
        lines.append(f'- "{ex["user_query"]}"')
    lines += [
        "",
        "У новых пользователей есть 3 бесплатные попытки.",
        "Дальше — полный доступ по подписке.",
        "",
        offer,
    ]
    return "\n".join(lines).strip() + "\n"


def make_x_posts(examples: list[dict]) -> str:
    posts = []

    posts.append(
        "\n".join(
            [
                "I built MarketAnalyst AI — a Telegram bot for fast crypto analysis.",
                "It helps turn market noise into a clearer picture.",
                "New users get 3 free tries.",
            ]
        )
    )

    posts.append(
        "\n".join(
            [
                'Example prompt: "что по btc"',
                f'Result: {examples[0]["bot_answer"]}',
                "That’s the idea behind MarketAnalyst AI: faster clarity, less noise.",
            ]
        )
    )

    posts.append(
        "\n".join(
            [
                "Most traders waste time jumping between charts, news, and random takes.",
                "MarketAnalyst AI puts the first structured view directly into Telegram.",
                "3 free tries for new users.",
            ]
        )
    )

    return "\n\n---\n\n".join(posts).strip() + "\n"


def make_ad_copy() -> str:
    return (
        "MarketAnalyst AI — Telegram-бот для быстрой криптоаналитики.\n"
        "Помогает быстро понять, что происходит по BTC, ETH и альтам.\n"
        "\n"
        "Что внутри:\n"
        "- быстрый разбор рынка\n"
        "- структурированные ответы\n"
        "- понятный язык без лишнего шума\n"
        "\n"
        "Новым пользователям доступны 3 бесплатные попытки.\n"
        "Дальше — полный доступ по подписке.\n"
    )


def make_outreach() -> str:
    return (
        "Привет. Я сделал Telegram-бота MarketAnalyst AI для быстрой криптоаналитики.\n"
        "Он помогает быстро понять рынок простым языком прямо в Telegram.\n"
        "\n"
        "У новых пользователей есть 3 бесплатные попытки, поэтому продукт легко протестировать без трения.\n"
        "Если тебе интересно, могу отправить демо и дать протестировать.\n"
    )


def write_output(filename: str, content: str) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / filename).write_text(content, encoding="utf-8")


def main() -> None:
    offer = load_offer()
    examples = load_examples()

    write_output("telegram_post.txt", make_telegram_post(offer, examples))
    write_output("x_posts.txt", make_x_posts(examples))
    write_output("ad_copy.txt", make_ad_copy())
    write_output("outreach.txt", make_outreach())

    print("✅ marketing pack generated:")
    for name in [
        "telegram_post.txt",
        "x_posts.txt",
        "ad_copy.txt",
        "outreach.txt",
    ]:
        print(f" - marketing/output/{name}")


if __name__ == "__main__":
    main()
