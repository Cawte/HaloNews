from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


def _bool(value: str | None, default: bool = False) -> bool:
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _int(value: str | None, default: int) -> int:
    try:
        return int(str(value).strip()) if value not in (None, "") else default
    except ValueError:
        return default


def _list(value: str | None, default: str) -> tuple[str, ...]:
    raw = value if value not in (None, "") else default
    return tuple(part.strip() for part in raw.split(",") if part.strip())


@dataclass(frozen=True)
class Config:
    telegram_bot_token: str
    telegram_channel_id: str
    admin_chat_id: str
    dry_run: bool
    post_mode: str
    auto_post_official: bool
    auto_post_min_score: int
    send_ru_to_admin: bool
    max_items_per_run: int
    max_posts_per_run: int
    max_posts_per_day: int
    enabled_sources: tuple[str, ...]
    data_dir: Path
    queue_path: Path
    state_path: Path
    log_path: Path
    ai_provider: str
    openai_api_key: str
    openai_model: str
    hf_api_token: str
    custom_rss_urls: tuple[str, ...]


def load_config() -> Config:
    load_dotenv()
    data_dir = Path(os.getenv("DATA_DIR", "data"))
    return Config(
        telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN", "").strip(),
        telegram_channel_id=os.getenv("TELEGRAM_CHANNEL_ID", "@Halo_Combat_Evolved").strip(),
        admin_chat_id=os.getenv("ADMIN_CHAT_ID", "").strip(),
        dry_run=_bool(os.getenv("DRY_RUN"), True),
        post_mode=os.getenv("POST_MODE", "queue").strip().lower(),
        auto_post_official=_bool(os.getenv("AUTO_POST_OFFICIAL"), True),
        auto_post_min_score=max(0, min(100, _int(os.getenv("AUTO_POST_MIN_SCORE"), 82))),
        send_ru_to_admin=_bool(os.getenv("SEND_RU_TO_ADMIN"), True),
        max_items_per_run=max(1, _int(os.getenv("MAX_ITEMS_PER_RUN"), 8)),
        max_posts_per_run=max(0, _int(os.getenv("MAX_POSTS_PER_RUN"), 2)),
        max_posts_per_day=max(0, _int(os.getenv("MAX_POSTS_PER_DAY"), 5)),
        enabled_sources=_list(os.getenv("ENABLED_SOURCES"), "halo_waypoint,xbox_wire,steam_halo_infinite"),
        data_dir=data_dir,
        queue_path=Path(os.getenv("QUEUE_PATH", str(data_dir / "queue.json"))),
        state_path=Path(os.getenv("STATE_PATH", str(data_dir / "state.json"))),
        log_path=Path(os.getenv("LOG_PATH", str(data_dir / "run_log.json"))),
        ai_provider=os.getenv("AI_PROVIDER", "template").strip().lower(),
        openai_api_key=os.getenv("OPENAI_API_KEY", "").strip(),
        openai_model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini").strip(),
        hf_api_token=os.getenv("HF_API_TOKEN", "").strip(),
        custom_rss_urls=_list(os.getenv("CUSTOM_RSS_URLS"), ""),
    )


def validate_runtime_config(cfg: Config, *, need_telegram: bool = True) -> None:
    missing: list[str] = []
    if need_telegram:
        if not cfg.telegram_bot_token:
            missing.append("TELEGRAM_BOT_TOKEN")
        if not cfg.telegram_channel_id:
            missing.append("TELEGRAM_CHANNEL_ID")
        if not cfg.admin_chat_id:
            missing.append("ADMIN_CHAT_ID")
    if cfg.ai_provider == "openai" and not cfg.openai_api_key:
        missing.append("OPENAI_API_KEY")
    if missing:
        raise RuntimeError("Missing required environment variables: " + ", ".join(missing))
