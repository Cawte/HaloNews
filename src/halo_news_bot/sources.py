from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from typing import Callable, Iterable
from urllib.parse import urlencode, urljoin

try:
    import feedparser  # type: ignore
except Exception:  # pragma: no cover - optional dependency fallback
    feedparser = None
import requests
from bs4 import BeautifulSoup
from xml.etree import ElementTree as ET

from .models import NewsItem

log = logging.getLogger(__name__)

USER_AGENT = "HaloNewsBot/2.0 (+https://t.me/Halo_Combat_Evolved)"

HALO_KEYWORDS = (
    "halo",
    "halo infinite",
    "halo studios",
    "halo waypoint",
    "halo: combat evolved",
    "halo combat evolved",
    "halo ce",
    "master chief",
    "spartan",
    "cortana",
    "343 industries",
    "hcs",
    "halo championship series",
    "forerunner",
    "covenant",
    "flood",
)


def _clean_text(text: str, max_chars: int = 6000) -> str:
    text = BeautifulSoup(unescape(text or ""), "lxml").get_text(" ", strip=True)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_chars]


def _is_halo_related(*parts: str) -> bool:
    haystack = " ".join(parts).lower()
    return any(keyword in haystack for keyword in HALO_KEYWORDS)


def _http_get(url: str, *, timeout: int = 25) -> requests.Response:
    response = requests.get(url, timeout=timeout, headers={"User-Agent": USER_AGENT})
    response.raise_for_status()
    return response




def _parse_feed(feed_url: str, limit: int = 20) -> tuple[str, list[dict[str, object]]]:
    """Parse RSS/Atom feeds. Uses feedparser when installed, with a stdlib fallback."""
    if feedparser is not None:
        parsed = feedparser.parse(feed_url)
        feed_title = str(parsed.feed.get("title", "Custom RSS")).strip() or "Custom RSS"
        entries: list[dict[str, object]] = []
        for entry in parsed.entries[:limit]:
            entries.append(
                {
                    "title": str(getattr(entry, "title", "")).strip(),
                    "link": str(getattr(entry, "link", "")).strip(),
                    "summary": str(getattr(entry, "summary", "")),
                    "published": getattr(entry, "published", None),
                    "media_thumbnail": getattr(entry, "media_thumbnail", None),
                }
            )
        return feed_title, entries

    xml = _http_get(feed_url).content
    root = ET.fromstring(xml)
    channel = root.find("channel")
    feed_title = "Custom RSS"
    entries: list[dict[str, object]] = []
    if channel is not None:
        feed_title = (channel.findtext("title") or feed_title).strip()
        for item in channel.findall("item")[:limit]:
            thumb = None
            for elem in item.iter():
                if elem.tag.endswith("thumbnail") and elem.attrib.get("url"):
                    thumb = [{"url": elem.attrib["url"]}]
                    break
            entries.append(
                {
                    "title": (item.findtext("title") or "").strip(),
                    "link": (item.findtext("link") or "").strip(),
                    "summary": item.findtext("description") or "",
                    "published": item.findtext("pubDate"),
                    "media_thumbnail": thumb,
                }
            )
    return feed_title, entries


def _parse_date(value: str | None) -> str | None:
    if not value:
        return None
    try:
        dt = parsedate_to_datetime(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat()
    except Exception:
        return None


def _date_from_timestamp(value: object) -> str | None:
    try:
        return datetime.fromtimestamp(int(value), tz=timezone.utc).replace(microsecond=0).isoformat()
    except Exception:
        return None


def extract_article(url: str) -> tuple[str, str | None]:
    try:
        html = _http_get(url).text
    except Exception as exc:
        log.warning("Could not fetch article %s: %s", url, exc)
        return "", None

    soup = BeautifulSoup(html, "lxml")
    image_url = None
    for attrs in ({"property": "og:image"}, {"name": "twitter:image"}, {"property": "twitter:image"}):
        tag = soup.find("meta", attrs=attrs)
        if tag and tag.get("content"):
            image_url = urljoin(url, tag["content"])
            break

    for bad in soup(["script", "style", "noscript", "svg", "nav", "footer", "header", "aside"]):
        bad.decompose()

    pieces: list[str] = []
    meta = soup.find("meta", attrs={"name": "description"})
    if meta and meta.get("content"):
        pieces.append(meta["content"])

    main = soup.find("article") or soup.find("main") or soup
    for tag in main.find_all(["h1", "h2", "h3", "p", "li"]):
        text = tag.get_text(" ", strip=True)
        if len(text) >= 25 and text not in pieces:
            pieces.append(text)
        if sum(len(p) for p in pieces) > 9000:
            break

    return _clean_text(" ".join(pieces), 7000), image_url


def fetch_halo_waypoint(limit: int = 10) -> list[NewsItem]:
    base_url = "https://www.halowaypoint.com"
    news_url = f"{base_url}/news"
    try:
        html = _http_get(news_url).text
    except Exception as exc:
        log.warning("Halo Waypoint failed: %s", exc)
        return []

    soup = BeautifulSoup(html, "lxml")
    seen_urls: set[str] = set()
    links: list[tuple[str, str]] = []
    for a in soup.find_all("a", href=True):
        href = a.get("href", "")
        text = _clean_text(a.get_text(" ", strip=True), 220)
        if "/news/" not in href or not text or len(text) < 8:
            continue
        url = urljoin(base_url, href)
        if url in seen_urls:
            continue
        seen_urls.add(url)
        links.append((text, url))

    items: list[NewsItem] = []
    for title, url in links[:limit]:
        body, image_url = extract_article(url)
        if not _is_halo_related(title, body):
            continue
        items.append(
            NewsItem(
                title=title,
                url=url,
                source_key="halo_waypoint",
                source_name="Halo Waypoint",
                summary=body[:1000],
                body=body,
                image_url=image_url,
                official=True,
            )
        )
    return items


def fetch_xbox_wire(limit: int = 18) -> list[NewsItem]:
    feed_url = "https://news.xbox.com/en-us/feed/"
    _feed_title, entries = _parse_feed(feed_url, limit)
    items: list[NewsItem] = []
    for entry in entries:
        title = str(entry.get("title", "")).strip()
        url = str(entry.get("link", "")).strip()
        summary = _clean_text(str(entry.get("summary", "")), 1200)
        if not _is_halo_related(title, summary):
            continue
        body, image_url = extract_article(url) if url else (summary, None)
        items.append(
            NewsItem(
                title=title,
                url=url,
                source_key="xbox_wire",
                source_name="Xbox Wire",
                summary=summary or body[:1000],
                body=body or summary,
                image_url=image_url,
                published_at=_parse_date(entry.get("published") if isinstance(entry.get("published"), str) else None),
                official=True,
            )
        )
    return items


def fetch_steam_halo_infinite(limit: int = 15) -> list[NewsItem]:
    params = {"appid": "1240440", "count": str(limit), "maxlength": "7000", "format": "json"}
    api_url = "https://api.steampowered.com/ISteamNews/GetNewsForApp/v2/?" + urlencode(params)
    try:
        data = _http_get(api_url).json()
    except Exception as exc:
        log.warning("Steam News failed: %s", exc)
        return []

    items: list[NewsItem] = []
    for entry in data.get("appnews", {}).get("newsitems", []):
        title = _clean_text(str(entry.get("title", "")), 220)
        url = str(entry.get("url", "")).strip()
        body = _clean_text(str(entry.get("contents", "")), 6000)
        if not _is_halo_related(title, body):
            continue
        items.append(
            NewsItem(
                title=title,
                url=url,
                source_key="steam_halo_infinite",
                source_name="Steam News: Halo Infinite",
                summary=body[:1000],
                body=body,
                image_url=None,
                published_at=_date_from_timestamp(entry.get("date")),
                official=True,
                raw={"gid": entry.get("gid")},
            )
        )
    return items


def fetch_custom_rss(urls: Iterable[str], limit_per_feed: int = 15) -> list[NewsItem]:
    items: list[NewsItem] = []
    for feed_url in urls:
        source_title, entries = _parse_feed(feed_url, limit_per_feed)
        for entry in entries:
            title = str(entry.get("title", "")).strip()
            url = str(entry.get("link", "")).strip()
            summary = _clean_text(str(entry.get("summary", "")), 1200)
            if not _is_halo_related(title, summary):
                continue
            image_url = None
            media_thumbnail = entry.get("media_thumbnail")
            if isinstance(media_thumbnail, list) and media_thumbnail:
                first = media_thumbnail[0]
                if isinstance(first, dict):
                    image_url = first.get("url")
            items.append(
                NewsItem(
                    title=title,
                    url=url,
                    source_key="custom_rss",
                    source_name=source_title,
                    summary=summary,
                    body=summary,
                    image_url=image_url,
                    published_at=_parse_date(entry.get("published") if isinstance(entry.get("published"), str) else None),
                    official=False,
                )
            )
    return items


SOURCE_REGISTRY: dict[str, Callable[[], list[NewsItem]]] = {
    "halo_waypoint": fetch_halo_waypoint,
    "xbox_wire": fetch_xbox_wire,
    "steam_halo_infinite": fetch_steam_halo_infinite,
}


def fetch_all(enabled_sources: tuple[str, ...], *, custom_rss_urls: tuple[str, ...] = ()) -> list[NewsItem]:
    results: list[NewsItem] = []
    for key in enabled_sources:
        if key == "custom_rss":
            results.extend(fetch_custom_rss(custom_rss_urls))
            continue
        fetcher = SOURCE_REGISTRY.get(key)
        if not fetcher:
            log.warning("Unknown source: %s", key)
            continue
        try:
            results.extend(fetcher())
        except Exception as exc:
            log.exception("Source %s failed: %s", key, exc)

    deduped: dict[str, NewsItem] = {}
    normalized_seen: set[str] = set()
    for item in results:
        if item.normalized_title and item.normalized_title in normalized_seen:
            continue
        deduped[item.fingerprint] = item
        normalized_seen.add(item.normalized_title)

    return sorted(deduped.values(), key=lambda item: item.published_at or "", reverse=True)
