"""Shared explicit loop and permissions for terminal and web."""
import json
from pathlib import Path

import bash_tool
from check_api import request

ROOT = Path(__file__).resolve().parent


def terminal_approve(name, arguments, call_id):
    print("\nRequested tool:", name)
    print(arguments.get("command") if name == "bash" else json.dumps(arguments, ensure_ascii=False))
    try:
        return input("Approve execution? [y/N]: ").strip().lower() == "y"
    except (EOFError, KeyboardInterrupt):
        return False


class Agent:
    def __init__(self, plugins, approve=terminal_approve, hidden_tools=()):
        self.plugins, self.approve = plugins, approve
        self.hidden_tools = set(hidden_tools)
        self.tools = [bash_tool.TOOL] + [tool for tool in plugins.tools if tool['function']['name'] not in self.hidden_tools]
        settings = json.loads((ROOT / "settings.json").read_text())
        self.allowed = set(settings.get("allow", [])) - {"bash"}
        self.first_usage = True

    def messages(self):
        return [{"role": "system", "content": (ROOT / "system_prompt.md").read_text() + "\n\n" + self.plugins.skill_prompt()}]

    def handle(self, call):
        try:
            name = call["function"]["name"]
            if name in self.hidden_tools:
                return "This tool is reserved for the harness and cannot be called by the model."
            arguments = json.loads(call["function"]["arguments"])
            if not isinstance(arguments, dict):
                raise ValueError()
            if name == "bash":
                if set(arguments) != {"command"} or not isinstance(arguments["command"], str) or not arguments["command"].strip():
                    raise ValueError()
            elif name not in self.plugins.routes:
                return "Unknown tool."
        except (KeyError, ValueError, TypeError):
            return "Invalid tool arguments; expected a JSON object matching the tool schema."
        if (name == "bash" or name not in self.allowed) and not self.approve(name, arguments, call["id"]):
            return "The user declined to run this tool. Respect this denial; do not try another route."
        try:
            result = bash_tool.run_bash(arguments["command"]) if name == "bash" else self.plugins.call(name, arguments)
            return self.plugins.redact(result)
        except Exception:
            return "Tool execution failed; check local configuration and retry."

    def turn(self, messages, question=None, on_event=None):
        if question is not None:
            messages.append({"role": "user", "content": question})
        emit = on_event or (lambda kind, **data: print("Agent:" if kind == "assistant" else "Tool result:", data.get("text", "")))

        def usage(value):
            if self.first_usage:
                print("First model call tokens:", json.dumps(value))
                self.first_usage = False
            if on_event:
                on_event("usage", usage=value)
            else:
                print("Usage:", value)

        try:
            for number in range(21):
                reply = request({"messages": messages, "tools": self.tools, "parallel_tool_calls": False,
                                 "tool_choice": "none" if number == 20 else "auto"}, on_usage=usage)
                messages.append(reply)
                calls = reply.get("tool_calls", [])
                if not calls:
                    text = reply.get("content") or "(No text response)"
                    emit("assistant", text=text)
                    return text
                for index, call in enumerate(calls):
                    if number == 20:
                        result = "Tool round limit reached."
                    elif index:
                        result = "Not executed: this harness accepts one tool call per model reply. Observe the first call's result, then propose this tool again using the exact returned identifiers. Do not invent catalog IDs."
                    else:
                        result = self.handle(call)
                    messages.append({"role": "tool", "tool_call_id": call["id"], "content": result})
                    emit("result", id=call["id"], text=result)
            emit("error", text="Tool round limit reached.")
            return "Tool round limit reached."
        except BaseException:
            answered = {m.get("tool_call_id") for m in messages if m.get("role") == "tool"}
            for message in list(messages):
                for call in message.get("tool_calls", []):
                    if call["id"] not in answered:
                        messages.append({"role": "tool", "tool_call_id": call["id"], "content": "Request interrupted."})
            raise
