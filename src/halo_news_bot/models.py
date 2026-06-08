from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

NewsStatus = Literal["pending", "draft", "published", "skipped", "failed"]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def stable_id(*parts: str) -> str:
    raw = "|".join(part.strip().lower() for part in parts if part)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


def normalize_title(title: str) -> str:
    text = title.lower()
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\b(the|a|an|official|new|latest|update|news)\b", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:160]


@dataclass(slots=True)
class NewsItem:
    title: str
    url: str
    source_key: str
    source_name: str
    summary: str = ""
    body: str = ""
    image_url: str | None = None
    published_at: str | None = None
    official: bool = False
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def fingerprint(self) -> str:
        return stable_id(self.url or self.title, self.source_name)

    @property
    def normalized_title(self) -> str:
        return normalize_title(self.title)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["fingerprint"] = self.fingerprint
        data["normalized_title"] = self.normalized_title
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "NewsItem":
        allowed = {"title", "url", "source_key", "source_name", "summary", "body", "image_url", "published_at", "official", "raw"}
        return cls(**{k: data.get(k) for k in allowed if k in data})


@dataclass(slots=True)
class Classification:
    news_type: str
    importance_score: int
    autopost_allowed: bool
    should_queue: bool
    reasons: list[str] = field(default_factory=list)
    matched_keywords: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Classification":
        return cls(
            news_type=str(data.get("news_type", "general")),
            importance_score=int(data.get("importance_score", 0)),
            autopost_allowed=bool(data.get("autopost_allowed", False)),
            should_queue=bool(data.get("should_queue", True)),
            reasons=list(data.get("reasons", [])),
            matched_keywords=list(data.get("matched_keywords", [])),
        )


@dataclass(slots=True)
class GeneratedPosts:
    en_post: str
    ru_admin_post: str
    source_button_text: str = "Read source"
    source_button_url: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GeneratedPosts":
        return cls(
            en_post=str(data.get("en_post", "")),
            ru_admin_post=str(data.get("ru_admin_post", "")),
            source_button_text=str(data.get("source_button_text", "Read source")),
            source_button_url=str(data.get("source_button_url", "")),
        )


@dataclass(slots=True)
class QueueItem:
    id: str
    article: NewsItem
    classification: Classification
    posts: GeneratedPosts
    status: NewsStatus = "pending"
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)
    published_at: str | None = None
    admin_note: str = ""
    error: str = ""

    def mark(self, status: NewsStatus, *, error: str = "") -> None:
        self.status = status
        self.updated_at = utc_now_iso()
        if status == "published":
            self.published_at = utc_now_iso()
        if error:
            self.error = error

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "article": self.article.to_dict(),
            "classification": self.classification.to_dict(),
            "posts": self.posts.to_dict(),
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "published_at": self.published_at,
            "admin_note": self.admin_note,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "QueueItem":
        return cls(
            id=str(data["id"]),
            article=NewsItem.from_dict(data["article"]),
            classification=Classification.from_dict(data.get("classification", {})),
            posts=GeneratedPosts.from_dict(data.get("posts", {})),
            status=data.get("status", "pending"),
            created_at=data.get("created_at") or utc_now_iso(),
            updated_at=data.get("updated_at") or utc_now_iso(),
            published_at=data.get("published_at"),
            admin_note=data.get("admin_note", ""),
            error=data.get("error", ""),
        )


def dumps_pretty(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
