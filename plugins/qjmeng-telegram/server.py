# /// script
# requires-python = ">=3.11"
# dependencies = ["mcp>=2,<3", "httpx>=0.28,<1"]
# ///
"""Single-chat Telegram MCP server. stdout belongs exclusively to MCP."""
import asyncio
import logging
import os
import sys
from contextlib import asynccontextmanager

import httpx
from mcp.server import MCPServer

log = logging.getLogger("qjmeng.telegram")
# HTTP request logs include the bot token in the URL. Disable those loggers.
logging.getLogger("httpx").disabled = True
logging.getLogger("httpcore").disabled = True


class Telegram:
    def __init__(self, token, chat_id, client):
        self.token = token
        self.chat_id = chat_id
        self.client = client
        self.offset = 0
        self.poll_lock = asyncio.Lock()

    async def api(self, method, **parameters):
        try:
            response = await self.client.post(
                f"https://api.telegram.org/bot{self.token}/{method}",
                json=parameters,
            )
            if response.status_code != 200:
                hint = {
                    401: "Check TELEGRAM_BOT_TOKEN in your local .env.",
                    403: "Open the bot on your phone and press Start; check the chat ID.",
                    409: "Stop other pollers for this bot and remove any existing webhook.",
                    429: "Telegram rate limit reached; wait before retrying.",
                }.get(response.status_code, "Check bot configuration and try again.")
                raise RuntimeError(f"Telegram HTTP {response.status_code}. {hint}")
            data = response.json()
            if not data.get("ok"):
                raise RuntimeError("Telegram rejected the request; check bot configuration.")
            return data["result"]
        except (httpx.HTTPError, ValueError, KeyError):
            # Do not expose exception strings: they may contain the secret URL.
            raise RuntimeError("Telegram connection or response failed; check network and retry.") from None

    async def skip_backlog(self):
        # Negative offset fetches the last update and forgets preceding updates.
        updates = await self.api("getUpdates", offset=-1, limit=1, timeout=0)
        if updates:
            self.offset = updates[-1]["update_id"] + 1
            # Acknowledge the last old update too, before accepting requests.
            await self.api("getUpdates", offset=self.offset, limit=1, timeout=0)

    async def send(self, text):
        if not text.strip():
            raise ValueError("Provide nonempty text to send.")
        # Count UTF-16 units conservatively, so emoji cannot exceed the limit.
        chunks, chunk, units = [], [], 0
        for character in text:
            width = 2 if ord(character) > 0xFFFF else 1
            if units + width > 4096:
                chunks.append("".join(chunk))
                chunk, units = [], 0
            chunk.append(character)
            units += width
        chunks.append("".join(chunk))
        message_ids = []
        for number, part in enumerate(chunks):
            try:
                sent = await self.api("sendMessage", chat_id=self.chat_id, text=part)
                message_ids.append(sent["message_id"])
            except RuntimeError as error:
                raise RuntimeError(f"Sent {number}/{len(chunks)} parts. {error}") from None
        import json
        return json.dumps({"confirmation": f"Sent {len(chunks)} message(s) to the configured chat.",
                           "message_ids": message_ids})

    async def wait(self, seconds=30):
        if seconds < 0:
            raise ValueError("seconds must be nonnegative; use 30 for normal polling.")
        seconds = min(seconds, 50)
        async with self.poll_lock:
            updates = await self.api("getUpdates", offset=self.offset, timeout=seconds, limit=100)
            messages = []
            for update in updates:
                self.offset = max(self.offset, update["update_id"] + 1)
                message = update.get("message", {})
                if message.get("chat", {}).get("id") != self.chat_id:
                    log.warning("Dropped update outside the configured chat or unsupported update.")
                    continue
                if isinstance(message.get("text"), str):
                    messages.append({"message_id": message["message_id"], "text": message["text"]})
            return messages or "No new messages."


telegram = None


@asynccontextmanager
async def lifespan(server):
    global telegram
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat:
        raise RuntimeError("Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in the host environment.")
    try:
        chat_id = int(chat)
    except ValueError:
        raise RuntimeError("TELEGRAM_CHAT_ID must be a numeric private chat ID.") from None
    if chat_id <= 0:
        raise RuntimeError("Use a positive private chat ID, not a group chat.")
    async with httpx.AsyncClient(timeout=httpx.Timeout(60, connect=10)) as client:
        telegram = Telegram(token, chat_id, client)
        try:
            await telegram.skip_backlog()
            yield {}
        finally:
            telegram = None


mcp = MCPServer("qjmeng-telegram", lifespan=lifespan)


@mcp.tool()
async def send_message(text: str) -> str:
    """Send plain text to the owner's configured Telegram private chat only.

    Use for requested replies, notifications, or brief progress updates. text is
    plain Unicode, e.g. 'Analysis finished.' Long text is split into messages of
    at most 4096 UTF-16 units. Returns a short JSON confirmation with Telegram
    message IDs so the host can correlate later approval replies. Never send secrets or whole files. There is no
    recipient parameter; delivery cannot be redirected to another chat.
    """
    return await telegram.send(text)


@mcp.tool()
async def wait_for_messages(seconds: int = 30) -> list[dict] | str:
    """Read new text messages from the owner's configured Telegram private chat.

    seconds is a nonnegative long-poll timeout in seconds, capped at 50; use 30
    normally or 0 to check immediately. Returns message IDs and text, or
    'No new messages.' Old startup messages and other chats are ignored. Use
    only when asked to listen; never call while the harness owns Telegram input
    or is waiting for an approval. Run only one polling host per bot.
    """
    return await telegram.wait(seconds)


if __name__ == "__main__":
    try:
        mcp.run()
    except Exception:
        # Lifespan errors can be wrapped in ExceptionGroups by the SDK.
        print("Telegram server failed. Check local environment, network, and competing pollers.", file=sys.stderr)
        sys.exit(1)
