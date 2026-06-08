from __future__ import annotations

from .models import Classification, NewsItem

TYPE_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("trailer", ("trailer", "teaser", "gameplay", "showcase", "premiere", "reveal")),
    ("patch", ("patch", "update", "hotfix", "balance", "playlist", "operation", "season")),
    ("event", ("event", "anniversary", "halo fest", "tournament", "championship", "hcs", "world championship")),
    ("release", ("launch", "released", "available now", "release date", "coming to", "beta")),
    ("community", ("community", "forge", "fan", "spotlight", "cosplay", "art", "map")),
    ("rumor", ("rumor", "rumour", "leak", "reportedly", "insider", "unconfirmed", "datamine")),
    ("sale", ("sale", "discount", "deal", "free weekend")),
]

BOOSTS: list[tuple[int, tuple[str, ...], str]] = [
    (35, ("halo: combat evolved", "halo combat evolved", "halo ce"), "Combat Evolved / CE mention"),
    (30, ("trailer", "teaser", "gameplay", "reveal"), "media reveal"),
    (30, ("halo studios", "343 industries", "xbox game studios"), "studio mention"),
    (25, ("release date", "available now", "launch", "beta"), "release information"),
    (20, ("master chief", "campaign", "remake", "remaster"), "high-interest Halo topic"),
    (15, ("halo infinite", "operation", "patch", "update"), "Halo Infinite update"),
    (10, ("hcs", "championship", "tournament"), "esports item"),
]

BLACKLIST: tuple[str, ...] = (
    "giveaway",
    "sponsored",
    "coupon",
    "wallpaper dump",
    "unrelated",
)


def classify(item: NewsItem, *, auto_post_official: bool, auto_post_min_score: int) -> Classification:
    text = f"{item.title}\n{item.summary}\n{item.body}".lower()
    reasons: list[str] = []
    matched: list[str] = []

    news_type = "general"
    for candidate, words in TYPE_RULES:
        hits = [word for word in words if word in text]
        if hits:
            news_type = candidate
            matched.extend(hits[:4])
            reasons.append(f"type={candidate}: " + ", ".join(hits[:3]))
            break

    score = 20 if item.official else 5
    if item.official:
        reasons.append("official source")

    for amount, words, reason in BOOSTS:
        hits = [word for word in words if word in text]
        if hits:
            score += amount
            matched.extend(hits[:3])
            reasons.append(f"+{amount}: {reason}")

    if news_type == "rumor":
        score -= 35
        reasons.append("rumor penalty")
    elif news_type == "community":
        score -= 10
    elif news_type in {"trailer", "release"}:
        score += 10

    blacklist_hits = [word for word in BLACKLIST if word in text]
    if blacklist_hits:
        score -= 40
        reasons.append("blacklist: " + ", ".join(blacklist_hits))

    # Strong baseline for official Halo Waypoint/Xbox/Steam articles that passed source filtering.
    if item.official and score < 55:
        score = 55

    score = max(0, min(100, score))
    should_queue = score >= 35 and not blacklist_hits
    autopost_allowed = (
        item.official
        and auto_post_official
        and score >= auto_post_min_score
        and news_type not in {"rumor", "community", "sale"}
    )

    return Classification(
        news_type=news_type,
        importance_score=score,
        autopost_allowed=autopost_allowed,
        should_queue=should_queue,
        reasons=reasons,
        matched_keywords=sorted(set(matched)),
    )
