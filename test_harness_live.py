"""Opt-in real-model/plugin checks; reads local credentials without printing them.

Uses model API credit and sends one Telegram message. Only exact skill-reading
commands are approved by the test. Run: uv run test_harness_live.py
"""
import json
import shlex
from pathlib import Path

from agent_core import Agent
from check_api import config
from plugin_loader import Plugins

ROOT = Path(__file__).resolve().parent


def run():
    with Plugins(config) as plugins:
        plugins.announce()
        skill_commands = {('cat', s['path']) for s in plugins.skills}
        def approve(name, arguments, call_id):
            if name != 'bash':
                return False
            try:
                return tuple(shlex.split(arguments['command'])) in skill_commands
            except (KeyError, ValueError):
                return False
        agent = Agent(plugins, approve)
        messages = agent.messages()
        usage_log = []
        def emit(kind, **data):
            if kind == 'usage':
                usage_log.append(data['usage'])
            elif kind in ('assistant', 'error'):
                print(kind + ':', data['text'])
        agent.turn(messages, 'Send exactly this Telegram message with the Telegram plugin: Hello from qimeng-agent! My own harness now loads MCP plugins. Read the telegram skill first if needed. Do not use other tools except the exact cat command for that skill.', on_event=emit)
        sent = [m for m in messages if m.get('tool_calls') for c in m['tool_calls'] if c['function']['name'] == 'telegram__send_message']
        assert sent, 'Model did not call the Telegram tool.'
        assert any('Sent 1 message(s)' in m.get('content', '') for m in messages if m['role'] == 'tool'), 'Telegram call did not succeed.'
        agent.turn(messages, 'Now use the seismic plugin to get event ci40925991 and briefly report its magnitude, depth, and mechanism class. Read its skill first if needed. Do not download a catalog or use other shell commands.', on_event=emit)
        assert any(c['function']['name'] == 'seismic__get_event_details' for m in messages for c in m.get('tool_calls', [])), 'Research plugin was not called.'
        assert any('strike-slip' in m.get('content', '') and 'ci40925991' in m.get('content', '') for m in messages if m['role'] == 'tool'), 'Expected event result missing.'
        for key in ('API_KEY', 'TELEGRAM_BOT_TOKEN'):
            if config.get(key):
                assert config[key] not in json.dumps(messages), 'A credential entered model history.'
        path = ROOT/'work/harness-plugin-live-results.json'
        path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps({'status':'passed', 'plugins':plugins.names, 'tools':list(plugins.routes), 'usage':usage_log,
            'tool_calls':[c['function']['name'] for m in messages for c in m.get('tool_calls', [])],
            'final_answer':messages[-1].get('content')}, indent=2))
        print('PASS: real model selected Telegram and seismic MCP tools; credentials absent from history.')
    assert not plugins.thread.is_alive(), 'MCP clients did not close.'
    print('PASS: MCP worker shut down cleanly.')


if __name__ == '__main__':
    run()
