# /// script
# requires-python = ">=3.11"
# dependencies = ["mcp>=2,<3", "httpx>=0.28,<1"]
# ///
"""Offline checks: uv run --script plugins/qjmeng-telegram/test_server.py."""
import json
import unittest
from unittest.mock import patch

import httpx
from mcp import Client
import server


class TelegramTests(unittest.IsolatedAsyncioTestCase):
    async def test_filter_offset_and_timeout(self):
        requests = []

        def respond(request):
            requests.append(json.loads(request.content))
            updates = [
                {"update_id": 8, "message": {"message_id": 1, "chat": {"id": 999}, "text": "intruder"}},
                {"update_id": 9, "message": {"message_id": 2, "chat": {"id": 123}, "text": "hello"}},
            ] if len(requests) == 1 else []
            return httpx.Response(200, json={"ok": True, "result": updates})

        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            bot = server.Telegram("fake", 123, client)
            with self.assertLogs("qjmeng.telegram", level="WARNING"):
                self.assertEqual(await bot.wait(100), [{"message_id": 2, "text": "hello"}])
            self.assertEqual(await bot.wait(0), "No new messages.")
        self.assertEqual(requests[0]["timeout"], 50)
        self.assertEqual(requests[1]["offset"], 10)

    async def test_backlog_and_unicode_chunks(self):
        requests = []

        def respond(request):
            parameters = json.loads(request.content)
            requests.append((request.url.path.rsplit("/", 1)[-1], parameters))
            result = [{"update_id": 42}] if len(requests) == 1 else ({"message_id": len(requests)} if request.url.path.endswith('sendMessage') else [])
            return httpx.Response(200, json={"ok": True, "result": result})

        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            bot = server.Telegram("fake", 123, client)
            await bot.skip_backlog()
            await bot.send("😀" * 3000)
        self.assertEqual(requests[0][1]["offset"], -1)
        self.assertEqual(requests[1][1]["offset"], 43)
        parts = [data for method, data in requests if method == "sendMessage"]
        self.assertEqual(len(parts), 2)
        self.assertEqual("".join(part["text"] for part in parts), "😀" * 3000)
        self.assertTrue(all(part["chat_id"] == 123 for part in parts))
        self.assertTrue(all(len(part["text"].encode("utf-16-le")) // 2 <= 4096 for part in parts))

    async def test_errors_do_not_expose_token(self):
        def respond(request):
            raise httpx.ConnectError(f"failed: {request.url}", request=request)

        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            bot = server.Telegram("secret-for-test", 123, client)
            with self.assertRaises(RuntimeError) as caught:
                await bot.wait()
        self.assertNotIn("secret-for-test", str(caught.exception))

    async def test_mcp_tools_and_dispatch(self):
        async def skip(bot):
            pass

        def respond(request):
            return httpx.Response(200, json={"ok": True, "result": {"message_id": 55}})

        original_client = httpx.AsyncClient
        with patch.dict("os.environ", TELEGRAM_BOT_TOKEN="fake", TELEGRAM_CHAT_ID="123"), \
             patch.object(server.Telegram, "skip_backlog", skip), \
             patch.object(server.httpx, "AsyncClient", lambda **kw: original_client(transport=httpx.MockTransport(respond), **kw)):
            async with Client(server.mcp) as client:
                tools = await client.list_tools()
                names = {tool.name for tool in tools.tools}
                self.assertEqual(names, {"send_message", "wait_for_messages"})
                result = await client.call_tool("send_message", {"text": "offline test"})
                self.assertFalse(result.is_error)


if __name__ == "__main__":
    unittest.main()
