"""Keep discovered stdio MCP clients on one async worker task."""
import asyncio
import json
import os
import re
import threading
from concurrent.futures import Future
from contextlib import AsyncExitStack
from pathlib import Path

import yaml
from mcp import Client
from mcp.client.stdio import StdioServerParameters

ROOT = Path(__file__).resolve().parent
NAME = re.compile(r"[A-Za-z0-9_-]{1,64}\Z")


def tool_text(result):
    """Preserve arrays and scalars; SDK text blocks may split list elements."""
    data = result.structured_content
    if data is not None:
        if isinstance(data, dict) and set(data) == {'result'}:
            data = data['result']
        return data if isinstance(data, str) else json.dumps(data, ensure_ascii=False)
    return '\n'.join(block.text for block in result.content if block.type == 'text')


class Plugins:
    def __init__(self, config, root=ROOT):
        self.root = Path(root)
        self.config = {**os.environ, **config}
        self.tools, self.skills, self.names, self.routes = [], [], [], {}
        self.ready = Future()
        self.stopping = False

    def expand(self, value, folder):
        def replace(match):
            key = match[1]
            if key == "CLAUDE_PLUGIN_ROOT":
                return str(folder.resolve())
            if not self.config.get(key):
                raise ValueError(f"Missing environment variable {key} for plugin {folder.name}.")
            return self.config[key]
        return re.sub(r"\$\{([^}]+)\}", replace, value)

    def redact(self, text):
        for key, value in self.config.items():
            if value and any(word in key.upper() for word in ("TOKEN", "KEY", "PASSWORD", "SECRET")):
                text = text.replace(value, "[REDACTED]")
        return text

    def __enter__(self):
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        try:
            self.ready.result(timeout=150)
        except BaseException:
            self.stopping = True
            if hasattr(self, "task"):
                self.loop.call_soon_threadsafe(self.task.cancel)
            self.thread.join(timeout=10)
            raise
        return self

    def _run(self):
        try:
            asyncio.run(self._serve())
        except BaseException as error:
            if not self.ready.done():
                self.ready.set_exception(RuntimeError(self.redact(f"Plugin startup failed: {error}")))
            elif not self.stopping:
                print("MCP worker stopped unexpectedly.")

    async def _serve(self):
        self.loop = asyncio.get_running_loop()
        self.task = asyncio.current_task()
        self.queue = asyncio.Queue()
        async with AsyncExitStack() as stack:
            servers_seen = set()
            for manifest in sorted((self.root / "plugins").glob("*/.claude-plugin/plugin.json")):
                folder = manifest.parent.parent
                self.names.append(json.loads(manifest.read_text())["name"])
                for skill in sorted(folder.glob("skills/*/SKILL.md")):
                    parts = skill.read_text().split("---", 2)
                    if len(parts) != 3 or parts[0].strip():
                        raise ValueError(f"Invalid skill frontmatter: {skill}")
                    header = yaml.safe_load(parts[1])
                    self.skills.append({"name": header["name"], "description": header["description"], "path": str(skill.resolve())})
                for server, spec in json.loads((folder / ".mcp.json").read_text())["mcpServers"].items():
                    if not NAME.fullmatch(server) or server in servers_seen:
                        raise ValueError(f"Invalid or duplicate MCP server name: {server}")
                    servers_seen.add(server)
                    env = {**os.environ, **{k: self.expand(v, folder) for k, v in spec.get("env", {}).items()}}
                    params = StdioServerParameters(command=self.expand(spec["command"], folder),
                        args=[self.expand(v, folder) for v in spec.get("args", [])], env=env, cwd=str(Path.cwd()))
                    client = await stack.enter_async_context(Client(params))
                    for tool in (await client.list_tools()).tools:
                        name = f"{server}__{tool.name}"
                        if not NAME.fullmatch(name) or name in self.routes:
                            raise ValueError(f"Invalid or duplicate MCP tool name: {name}")
                        self.routes[name] = (server, client, tool.name)
                        self.tools.append({"type": "function", "function": {"name": name,
                            "description": tool.description or "", "parameters": tool.input_schema}})
            self.ready.set_result(True)
            while True:
                item = await self.queue.get()
                if item is None:
                    break
                name, arguments, done = item
                try:
                    _, client, tool = self.routes[name]
                    result = await client.call_tool(tool, arguments, read_timeout_seconds=260)
                    content = tool_text(result)
                    done.set_result(self.redact(("Tool error: " if result.is_error else "") + content))
                except Exception:
                    done.set_result("MCP call failed; check the server and retry. No credentials displayed.")

    def call(self, name, arguments):
        if name not in self.routes:
            return "Unknown MCP tool."
        if not self.thread.is_alive():
            raise RuntimeError("MCP worker is unavailable; restart the harness.")
        done = Future()
        asyncio.run_coroutine_threadsafe(self.queue.put((name, arguments, done)), self.loop).result(timeout=5)
        return done.result(timeout=275)

    def skill_prompt(self):
        lines = ["Available plugin skills. To use a skill, read its SKILL.md with bash first."]
        lines += [f"- {s['name']}: {s['description']} Path: {s['path']}" for s in self.skills]
        return "\n".join(lines)

    def announce(self):
        print("Plugins:", ", ".join(self.names) or "none")
        print("MCP tools:", ", ".join(self.routes) or "none")
        print("Skills:", ", ".join(s["name"] for s in self.skills) or "none")

    def __exit__(self, *exc):
        self.stopping = True
        if self.thread.is_alive():
            asyncio.run_coroutine_threadsafe(self.queue.put(None), self.loop).result(timeout=5)
            self.thread.join(timeout=285)
            if self.thread.is_alive():
                self.loop.call_soon_threadsafe(self.task.cancel)
                self.thread.join(timeout=10)
