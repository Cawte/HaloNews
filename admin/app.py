from __future__ import annotations

import base64
import json
import os
import sys
from pathlib import Path
from typing import Any

import requests
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from halo_news_bot.classifier import classify
from halo_news_bot.config import Config, load_config
from halo_news_bot.generator import generate_posts
from halo_news_bot.models import Classification, GeneratedPosts, NewsItem, QueueItem, dumps_pretty, stable_id, utc_now_iso
from halo_news_bot.runner import fetch_and_queue
from halo_news_bot.storage import JsonStorage
from halo_news_bot.telegram_client import TelegramClient

st.set_page_config(page_title="Halo News Admin", page_icon="🎮", layout="wide")


def secret(name: str, default: str = "") -> str:
    try:
        if name in st.secrets:
            return str(st.secrets[name])
    except Exception:
        pass
    return os.getenv(name, default)


class RepoJsonStore:
    def __init__(self):
        self.token = secret("GITHUB_TOKEN")
        self.repo = secret("GITHUB_REPO")
        self.branch = secret("GITHUB_BRANCH", "main")
        self.queue_path = secret("QUEUE_PATH", "data/queue.json")
        self.state_path = secret("STATE_PATH", "data/state.json")
        self.enabled = bool(self.token and self.repo)

    @property
    def headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def _url(self, path: str) -> str:
        return f"https://api.github.com/repos/{self.repo}/contents/{path}"

    def read_json(self, path: str, default: Any) -> tuple[Any, str | None]:
        if not self.enabled:
            local = ROOT / path
            if not local.exists():
                return default, None
            return json.loads(local.read_text(encoding="utf-8") or json.dumps(default)), None
        response = requests.get(self._url(path), headers=self.headers, params={"ref": self.branch}, timeout=30)
        if response.status_code == 404:
            return default, None
        response.raise_for_status()
        data = response.json()
        content = base64.b64decode(data["content"]).decode("utf-8")
        return json.loads(content or json.dumps(default)), data.get("sha")

    def write_json(self, path: str, value: Any, message: str, sha: str | None = None) -> None:
        content = dumps_pretty(value)
        if not self.enabled:
            local = ROOT / path
            local.parent.mkdir(parents=True, exist_ok=True)
            local.write_text(content, encoding="utf-8")
            return
        payload: dict[str, Any] = {
            "message": message,
            "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
            "branch": self.branch,
        }
        if sha:
            payload["sha"] = sha
        response = requests.put(self._url(path), headers=self.headers, json=payload, timeout=30)
        response.raise_for_status()


repo_store = RepoJsonStore()


def require_auth() -> None:
    password = secret("ADMIN_PANEL_PASSWORD")
    if not password:
        st.warning("ADMIN_PANEL_PASSWORD is not set. Set it before deploying the admin panel publicly.")
        return
    if st.session_state.get("auth_ok"):
        return
    st.title("🎮 Halo News Admin")
    entered = st.text_input("Admin password", type="password")
    if st.button("Login") and entered == password:
        st.session_state["auth_ok"] = True
        st.rerun()
    st.stop()


def load_queue_raw() -> tuple[list[dict[str, Any]], str | None]:
    return repo_store.read_json(repo_store.queue_path, [])


def save_queue_raw(queue: list[dict[str, Any]], sha: str | None, message: str) -> None:
    repo_store.write_json(repo_store.queue_path, queue, message, sha)


def get_telegram(*, dry_run: bool) -> TelegramClient:
    return TelegramClient(secret("TELEGRAM_BOT_TOKEN"), dry_run=dry_run)


def update_item(queue: list[dict[str, Any]], item_id: str, updater) -> bool:
    for index, raw in enumerate(queue):
        if raw.get("id") == item_id:
            item = QueueItem.from_dict(raw)
            updater(item)
            item.updated_at = utc_now_iso()
            queue[index] = item.to_dict()
            return True
    return False


def render_metric_row(queue_items: list[QueueItem]) -> None:
    counts = {"pending": 0, "draft": 0, "published": 0, "skipped": 0, "failed": 0}
    for item in queue_items:
        counts[item.status] = counts.get(item.status, 0) + 1
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Pending", counts.get("pending", 0))
    c2.metric("Drafts", counts.get("draft", 0))
    c3.metric("Published", counts.get("published", 0))
    c4.metric("Skipped", counts.get("skipped", 0))
    c5.metric("Failed", counts.get("failed", 0))


def publish_item(item: QueueItem, *, dry_run: bool, send_ru: bool) -> tuple[bool, str]:
    channel_id = secret("TELEGRAM_CHANNEL_ID", "@Halo_Combat_Evolved")
    admin_id = secret("ADMIN_CHAT_ID")
    telegram = get_telegram(dry_run=dry_run)
    result = telegram.publish_post(
        channel_id,
        item.posts.en_post,
        image_url=item.article.image_url,
        button_text=item.posts.source_button_text,
        button_url=item.posts.source_button_url,
    )
    if not result.ok:
        return False, result.description
    if send_ru and admin_id:
        ru_result = telegram.publish_post(
            admin_id,
            item.posts.ru_admin_post,
            image_url=item.article.image_url,
            button_text=item.posts.source_button_text,
            button_url=item.posts.source_button_url,
        )
        if not ru_result.ok:
            return False, "EN posted, but RU admin message failed: " + ru_result.description
    return True, "Published" if not dry_run else "Dry-run OK"


def item_editor(item: QueueItem, queue_raw: list[dict[str, Any]], sha: str | None, index: int) -> None:
    article = item.article
    c = item.classification
    with st.container(border=True):
        top_left, top_right = st.columns([3, 1])
        with top_left:
            st.subheader(article.title)
            st.caption(f"{article.source_name} · {c.news_type} · score {c.importance_score}/100 · {item.status}")
            st.write(article.url)
        with top_right:
            if article.image_url:
                st.image(article.image_url, use_container_width=True)

        with st.expander("Source summary and classifier reasons", expanded=False):
            st.write(article.summary or article.body[:1200])
            st.json(c.to_dict())

        en_key = f"en_{item.id}_{index}"
        ru_key = f"ru_{item.id}_{index}"
        note_key = f"note_{item.id}_{index}"
        en_text = st.text_area("EN post for channel", value=item.posts.en_post, height=220, key=en_key)
        ru_text = st.text_area("RU admin version", value=item.posts.ru_admin_post, height=220, key=ru_key)
        note = st.text_input("Admin note", value=item.admin_note, key=note_key)

        action_cols = st.columns([1, 1, 1, 1, 1, 1])
        dry_run = st.session_state.get("dry_run", False)
        send_ru = st.session_state.get("send_ru", True)

        if action_cols[0].button("💾 Save", key=f"save_{item.id}"):
            def updater(x: QueueItem) -> None:
                x.posts.en_post = en_text
                x.posts.ru_admin_post = ru_text
                x.admin_note = note
                if x.status == "pending":
                    x.status = "draft"
            update_item(queue_raw, item.id, updater)
            save_queue_raw(queue_raw, sha, f"Edit post {item.id}")
            st.success("Saved")
            st.rerun()

        if action_cols[1].button("🚀 Publish", key=f"publish_{item.id}"):
            item.posts.en_post = en_text
            item.posts.ru_admin_post = ru_text
            item.admin_note = note
            ok, message = publish_item(item, dry_run=dry_run, send_ru=send_ru)
            def updater(x: QueueItem) -> None:
                x.posts.en_post = en_text
                x.posts.ru_admin_post = ru_text
                x.admin_note = note
                x.mark("published" if ok else "failed", error="" if ok else message)
            update_item(queue_raw, item.id, updater)
            save_queue_raw(queue_raw, sha, f"Publish post {item.id}" if ok else f"Mark failed {item.id}")
            st.success(message) if ok else st.error(message)
            st.rerun()

        if action_cols[2].button("🇷🇺 Send RU", key=f"ru_{item.id}"):
            admin_id = secret("ADMIN_CHAT_ID")
            result = get_telegram(dry_run=dry_run).publish_post(
                admin_id,
                ru_text,
                image_url=article.image_url,
                button_text=item.posts.source_button_text,
                button_url=item.posts.source_button_url,
            )
            st.success("RU sent") if result.ok else st.error(result.description)

        if action_cols[3].button("✨ Regenerate", key=f"regen_{item.id}"):
            new_posts = generate_posts(article, c, provider="template", style="hype")
            def updater(x: QueueItem) -> None:
                x.posts = new_posts
                x.status = "draft"
            update_item(queue_raw, item.id, updater)
            save_queue_raw(queue_raw, sha, f"Regenerate post {item.id}")
            st.success("Regenerated with hype template")
            st.rerun()

        if action_cols[4].button("🙈 Skip", key=f"skip_{item.id}"):
            def updater(x: QueueItem) -> None:
                x.mark("skipped")
            update_item(queue_raw, item.id, updater)
            save_queue_raw(queue_raw, sha, f"Skip post {item.id}")
            st.warning("Skipped")
            st.rerun()

        if action_cols[5].button("🔄 Pending", key=f"pending_{item.id}"):
            def updater(x: QueueItem) -> None:
                x.mark("pending")
            update_item(queue_raw, item.id, updater)
            save_queue_raw(queue_raw, sha, f"Return post to pending {item.id}")
            st.rerun()


def main() -> None:
    require_auth()
    st.title("🎮 Halo News Admin Panel")
    st.caption("Editor for EN channel posts + RU admin versions")

    with st.sidebar:
        st.header("Mode")
        st.write("Storage:", "GitHub repo" if repo_store.enabled else "local files")
        st.session_state["dry_run"] = st.toggle("Dry-run publishing", value=secret("DRY_RUN", "true").lower() == "true")
        st.session_state["send_ru"] = st.toggle("Send RU to admin when publishing", value=True)
        status_filter = st.multiselect(
            "Statuses",
            ["pending", "draft", "failed", "published", "skipped"],
            default=["pending", "draft", "failed"],
        )

    queue_raw, sha = load_queue_raw()
    queue_items = [QueueItem.from_dict(raw) for raw in queue_raw]
    render_metric_row(queue_items)

    tab_queue, tab_tools, tab_settings = st.tabs(["Queue", "Tools", "Settings"])

    with tab_queue:
        shown = [item for item in queue_items if item.status in set(status_filter)]
        if not shown:
            st.info("No items for selected statuses.")
        for idx, item in enumerate(shown):
            item_editor(item, queue_raw, sha, idx)

    with tab_tools:
        st.subheader("Manual tools")
        st.write("Use this locally, or on Streamlit if your secrets are configured.")
        if st.button("Fetch news now and add to queue"):
            cfg = load_config()
            # Local storage mode only. In GitHub mode, scheduled Actions should fetch and commit queue updates.
            if repo_store.enabled:
                st.info("In GitHub storage mode, use the GitHub Actions workflow_dispatch button for fetching. This avoids write conflicts.")
            else:
                storage = JsonStorage(cfg.queue_path, cfg.state_path, cfg.log_path)
                result = fetch_and_queue(cfg, storage)
                st.success(result)
        if st.button("Reload queue"):
            st.rerun()

    with tab_settings:
        st.subheader("Recommended secrets")
        st.code(
            """ADMIN_PANEL_PASSWORD=choose-a-strong-password
TELEGRAM_BOT_TOKEN=123456:bot-token
TELEGRAM_CHANNEL_ID=@Halo_Combat_Evolved
ADMIN_CHAT_ID=123456789
GITHUB_TOKEN=github_pat_...    # only for Streamlit Cloud editor
GITHUB_REPO=yourname/halo-news-ai-bot-pro
GITHUB_BRANCH=main
DRY_RUN=false""",
            language="bash",
        )
        st.write("Current queue path:", repo_store.queue_path)
        st.write("Current state path:", repo_store.state_path)


if __name__ == "__main__":
    main()
