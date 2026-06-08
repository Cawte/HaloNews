from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import requests

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class TelegramResult:
    ok: bool
    description: str = ""
    message_id: int | None = None


class TelegramClient:
    def __init__(self, bot_token: str, *, dry_run: bool = False):
        self.bot_token = bot_token
        self.base_url = f"https://api.telegram.org/bot{bot_token}" if bot_token else ""
        self.dry_run = dry_run

    def _post(self, method: str, payload: dict[str, Any]) -> TelegramResult:
        if self.dry_run:
            log.info("DRY RUN Telegram %s: %s", method, payload)
            return TelegramResult(True, "dry-run", None)
        if not self.bot_token:
            return TelegramResult(False, "TELEGRAM_BOT_TOKEN is empty")
        try:
            response = requests.post(f"{self.base_url}/{method}", json=payload, timeout=30)
            data = response.json()
        except Exception as exc:
            log.exception("Telegram request failed: %s", exc)
            return TelegramResult(False, str(exc))
        if not data.get("ok"):
            return TelegramResult(False, str(data.get("description", data)))
        result = data.get("result", {})
        return TelegramResult(True, "ok", result.get("message_id"))

    @staticmethod
    def _reply_markup(button_text: str | None, button_url: str | None) -> dict[str, Any] | None:
        if not button_text or not button_url:
            return None
        return {"inline_keyboard": [[{"text": button_text[:64], "url": button_url}]]}

    def send_message(
        self,
        chat_id: str,
        text: str,
        *,
        disable_preview: bool = False,
        button_text: str | None = None,
        button_url: str | None = None,
    ) -> TelegramResult:
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "text": text[:4096],
            "disable_web_page_preview": disable_preview,
        }
        markup = self._reply_markup(button_text, button_url)
        if markup:
            payload["reply_markup"] = markup
        return self._post("sendMessage", payload)

    def send_photo(
        self,
        chat_id: str,
        photo_url: str,
        caption: str,
        *,
        button_text: str | None = None,
        button_url: str | None = None,
    ) -> TelegramResult:
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "photo": photo_url,
            "caption": caption[:1024],
        }
        markup = self._reply_markup(button_text, button_url)
        if markup:
            payload["reply_markup"] = markup
        return self._post("sendPhoto", payload)

    def publish_post(
        self,
        chat_id: str,
        text: str,
        *,
        image_url: str | None = None,
        button_text: str | None = None,
        button_url: str | None = None,
    ) -> TelegramResult:
        if image_url and len(text) <= 1024:
            result = self.send_photo(chat_id, image_url, text, button_text=button_text, button_url=button_url)
            if result.ok:
                return result
            log.warning("sendPhoto failed; falling back to sendMessage: %s", result.description)
        return self.send_message(chat_id, text, disable_preview=False, button_text=button_text, button_url=button_url)
