from __future__ import annotations

import json
import logging
import re
from typing import Any

import requests

from .models import Classification, GeneratedPosts, NewsItem

log = logging.getLogger(__name__)

HASHTAGS_BY_TYPE = {
    "trailer": "#Halo #HaloCE #Xbox #MasterChief #GamingNews",
    "patch": "#Halo #HaloInfinite #Xbox #HaloNews",
    "event": "#Halo #HCS #Xbox #HaloNews",
    "release": "#Halo #Xbox #MasterChief #GamingNews",
    "community": "#Halo #HaloCommunity #Xbox",
    "rumor": "#Halo #Xbox #HaloRumors",
    "sale": "#Halo #Xbox #GamingDeals",
    "general": "#Halo #HaloCombatEvolved #Xbox #MasterChief",
}

HOOKS_BY_TYPE = {
    "trailer": "🔥 New Halo trailer / video update",
    "patch": "🛠 Halo update",
    "event": "🏆 Halo event update",
    "release": "🚀 Halo release update",
    "community": "👥 Halo community update",
    "rumor": "👀 Halo rumor watch",
    "sale": "💸 Halo deal alert",
    "general": "🔥 Halo news update",
}

RU_TYPE = {
    "trailer": "трейлер / видео",
    "patch": "патч / обновление",
    "event": "ивент / турнир",
    "release": "релиз / запуск",
    "community": "комьюнити",
    "rumor": "слух / неподтверждённое",
    "sale": "скидка / распродажа",
    "general": "общая новость",
}


def _clean(text: str, limit: int) -> str:
    text = re.sub(r"\s+", " ", (text or "").strip())
    if len(text) <= limit:
        return text
    cut = text[: limit - 1].rsplit(" ", 1)[0]
    return cut.rstrip(".,;: ") + "…"


def _source_name(article: NewsItem) -> str:
    return article.source_name or "Source"


def _first_summary(article: NewsItem) -> str:
    summary = article.summary or article.body or "A new Halo-related update has appeared from an official/community source."
    return _clean(summary, 320)


def generate_template_posts(article: NewsItem, c: Classification, *, style: str = "balanced") -> GeneratedPosts:
    hook = HOOKS_BY_TYPE.get(c.news_type, HOOKS_BY_TYPE["general"])
    hashtags = HASHTAGS_BY_TYPE.get(c.news_type, HASHTAGS_BY_TYPE["general"])
    title = _clean(article.title, 180)
    summary = _first_summary(article)
    source = _source_name(article)

    if c.news_type == "rumor":
        middle = "This is not officially confirmed yet, so treat it as a rumor until a trusted source says otherwise."
    elif c.news_type == "trailer":
        middle = "Halo fans have a fresh video update to check out. The post is based on the source below, without adding unconfirmed details."
    elif c.news_type == "patch":
        middle = "The update appears to focus on Halo-related changes, fixes, events, or playlist/content information from the source."
    elif c.news_type == "event":
        middle = "The update points to fresh Halo activity around events, community plans, competition, or anniversary content."
    elif c.news_type == "community":
        middle = "A new community-focused Halo item is making the rounds. Worth checking if you follow the wider Halo scene."
    else:
        middle = "A new Halo-related update has been posted. Here are the key details from the source."

    if style == "short":
        en = f"""{hook}\n\n{title}\n\n{summary}\n\nSource: {source}\n{hashtags}"""
    elif style == "hype":
        en = f"""{hook}\n\n{title}\n\n{summary}\n\n{middle}\n\nKeep your eyes on the Halo universe.\n\nSource: {source}\n{hashtags}"""
    else:
        en = f"""{hook}\n\n{title}\n\n{summary}\n\n{middle}\n\nSource: {source}\n{hashtags}"""

    ru = f"""🇷🇺 RU admin version\n\nТип: {RU_TYPE.get(c.news_type, 'общая новость')}\nВажность: {c.importance_score}/100\nИсточник: {source}\nАвтопост разрешён: {'да' if c.autopost_allowed else 'нет'}\n\nЗаголовок:\n{title}\n\nКратко:\n{summary}\n\nПочему бот выбрал это:\n- """ + "\n- ".join(c.reasons[:6]) + f"\n\nСсылка:\n{article.url}"

    return GeneratedPosts(
        en_post=_clean(en, 3900),
        ru_admin_post=_clean(ru, 3900),
        source_button_text="Read source",
        source_button_url=article.url,
    )


OPENAI_INSTRUCTIONS = """
You are an accurate Telegram editor for a Halo news channel.
Create a short English Telegram post and a Russian admin version from the provided source only.
Never invent facts, dates, platforms, leaks, quotes, release windows, or prices.
Use natural gaming-news style, but stay factual.
Return JSON only with keys: en_post, ru_admin_post, source_button_text.
English post must include 3-6 hashtags and Source line.
Russian admin version must include article type, score, and a natural Russian summary.
""".strip()


def _try_openai(article: NewsItem, c: Classification, *, api_key: str, model: str) -> GeneratedPosts | None:
    if not api_key:
        return None
    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key)
        payload = {
            "article": article.to_dict(),
            "classification": c.to_dict(),
            "max_lengths": {"en_post": 1200, "ru_admin_post": 1700},
        }
        response = client.responses.create(
            model=model,
            instructions=OPENAI_INSTRUCTIONS,
            input=json.dumps(payload, ensure_ascii=False),
        )
        raw = response.output_text.strip()
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        data = json.loads(raw)
        return GeneratedPosts(
            en_post=_clean(str(data.get("en_post", "")), 3900),
            ru_admin_post=_clean(str(data.get("ru_admin_post", "")), 3900),
            source_button_text=str(data.get("source_button_text", "Read source"))[:32] or "Read source",
            source_button_url=article.url,
        )
    except Exception as exc:
        log.warning("OpenAI generation failed, using template: %s", exc)
        return None


def _try_huggingface(article: NewsItem, c: Classification, *, token: str) -> GeneratedPosts | None:
    """Optional experimental free/credit-based provider. Falls back automatically."""
    if not token:
        return None
    try:
        prompt = (
            "Write a concise English Telegram post about this Halo news. "
            "Do not invent facts. Include hashtags and Source line.\n\n"
            f"Title: {article.title}\nSummary: {_first_summary(article)}\nSource: {article.source_name}\nURL: {article.url}\n"
        )
        response = requests.post(
            "https://api-inference.huggingface.co/models/mistralai/Mistral-7B-Instruct-v0.3",
            headers={"Authorization": f"Bearer {token}"},
            json={"inputs": prompt, "parameters": {"max_new_tokens": 350, "temperature": 0.4}},
            timeout=45,
        )
        if response.status_code >= 400:
            return None
        data = response.json()
        text = data[0].get("generated_text", "") if isinstance(data, list) and data else ""
        text = text.replace(prompt, "").strip()
        if not text:
            return None
        template = generate_template_posts(article, c)
        return GeneratedPosts(
            en_post=_clean(text, 3900),
            ru_admin_post=template.ru_admin_post,
            source_button_text="Read source",
            source_button_url=article.url,
        )
    except Exception as exc:
        log.warning("HF generation failed, using template: %s", exc)
        return None


def generate_posts(
    article: NewsItem,
    classification: Classification,
    *,
    provider: str = "template",
    openai_api_key: str = "",
    openai_model: str = "gpt-4.1-mini",
    hf_api_token: str = "",
    style: str = "balanced",
) -> GeneratedPosts:
    provider = (provider or "template").lower()
    if provider == "openai":
        result = _try_openai(article, classification, api_key=openai_api_key, model=openai_model)
        if result:
            return result
    if provider in {"huggingface", "hf"}:
        result = _try_huggingface(article, classification, token=hf_api_token)
        if result:
            return result
    return generate_template_posts(article, classification, style=style)
