from __future__ import annotations

import logging
from datetime import datetime, timezone

from .classifier import classify
from .config import Config, validate_runtime_config
from .generator import generate_posts
from .models import QueueItem, stable_id, utc_now_iso
from .sources import fetch_all
from .storage import JsonStorage
from .telegram_client import TelegramClient

log = logging.getLogger(__name__)


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _make_queue_item(cfg: Config, article) -> QueueItem:
    classification = classify(
        article,
        auto_post_official=cfg.auto_post_official,
        auto_post_min_score=cfg.auto_post_min_score,
    )
    posts = generate_posts(
        article,
        classification,
        provider=cfg.ai_provider,
        openai_api_key=cfg.openai_api_key,
        openai_model=cfg.openai_model,
        hf_api_token=cfg.hf_api_token,
    )
    return QueueItem(
        id=stable_id(article.fingerprint, article.normalized_title),
        article=article,
        classification=classification,
        posts=posts,
    )


def fetch_and_queue(cfg: Config, storage: JsonStorage) -> dict[str, int]:
    state = storage.load_state()
    state["last_run_at"] = utc_now_iso()
    state["stats"]["runs"] = int(state["stats"].get("runs", 0)) + 1
    storage.save_state(state)

    articles = fetch_all(cfg.enabled_sources, custom_rss_urls=cfg.custom_rss_urls)
    storage.increment_stat("fetched", len(articles))
    queued = 0
    skipped = 0

    for article in articles[: cfg.max_items_per_run]:
        if storage.is_seen(article.fingerprint, article.normalized_title):
            skipped += 1
            continue
        queue_item = _make_queue_item(cfg, article)
        if not queue_item.classification.should_queue:
            storage.mark_seen(article.fingerprint, article.normalized_title)
            storage.increment_stat("skipped")
            storage.append_log({"event": "skipped_low_score", "title": article.title, "score": queue_item.classification.importance_score})
            skipped += 1
            continue
        created = storage.add_or_update_queue_item(queue_item)
        storage.mark_seen(article.fingerprint, article.normalized_title)
        if created:
            queued += 1
            storage.increment_stat("queued")
            storage.append_log({"event": "queued", "id": queue_item.id, "title": article.title, "score": queue_item.classification.importance_score})

    return {"fetched": len(articles), "queued": queued, "skipped": skipped}


def publish_queue(cfg: Config, storage: JsonStorage) -> dict[str, int]:
    validate_runtime_config(cfg, need_telegram=True)
    telegram = TelegramClient(cfg.telegram_bot_token, dry_run=cfg.dry_run)
    queue = storage.load_queue()

    allowed_today = max(0, cfg.max_posts_per_day - storage.published_today_count()) if cfg.max_posts_per_day else 999999
    allowed_this_run = min(cfg.max_posts_per_run, allowed_today) if cfg.max_posts_per_run else 0
    published = 0
    failed = 0

    if cfg.post_mode == "queue":
        return {"published": 0, "failed": 0}

    for item in queue:
        if published >= allowed_this_run:
            break
        if item.status not in {"pending", "draft"}:
            continue
        if cfg.post_mode == "auto":
            can_publish = item.classification.autopost_allowed
        elif cfg.post_mode == "hybrid":
            can_publish = item.classification.autopost_allowed
        else:
            can_publish = False
        if not can_publish:
            continue

        result = telegram.publish_post(
            cfg.telegram_channel_id,
            item.posts.en_post,
            image_url=item.article.image_url,
            button_text=item.posts.source_button_text,
            button_url=item.posts.source_button_url,
        )
        if result.ok:
            item.mark("published")
            published += 1
            storage.increment_stat("published")
            storage.increment_published_today()
            storage.append_log({"event": "published", "id": item.id, "title": item.article.title})
            if cfg.send_ru_to_admin:
                telegram.publish_post(
                    cfg.admin_chat_id,
                    item.posts.ru_admin_post,
                    image_url=item.article.image_url,
                    button_text=item.posts.source_button_text,
                    button_url=item.posts.source_button_url,
                )
        else:
            item.mark("failed", error=result.description)
            failed += 1
            storage.append_log({"event": "publish_failed", "id": item.id, "error": result.description})

    storage.save_queue(queue)
    return {"published": published, "failed": failed}


def run_once(cfg: Config) -> dict[str, int]:
    storage = JsonStorage(cfg.queue_path, cfg.state_path, cfg.log_path)
    queued = fetch_and_queue(cfg, storage)
    published = publish_queue(cfg, storage)
    return {**queued, **published}
