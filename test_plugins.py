"""Offline permission/loop tests plus real stdio plugin lifecycle checks."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from agent_core import Agent
from plugin_loader import Plugins


def call(name, args, ident="call-1"):
    return {"id": ident, "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}


class PermissionTests(unittest.TestCase):
    def setUp(self):
        self.plugins = Mock()
        self.plugins.tools = []
        self.plugins.routes = {"seismic__summarize_catalog": (), "other__write": ()}
        self.plugins.redact.side_effect = lambda text: text
        self.plugins.skill_prompt.return_value = "Skill metadata only."
        self.approve = Mock(return_value=False)
        self.agent = Agent(self.plugins, self.approve)

    def test_denial_never_executes_and_allowlist_cannot_enable_bash(self):
        self.agent.allowed.add("bash")
        with patch('bash_tool.run_bash') as run:
            result = self.agent.handle(call("bash", {"command": "printf blocked"}))
            self.assertIn("declined", result)
            run.assert_not_called()

    def test_mcp_default_denial_and_explicit_allow(self):
        self.assertIn("declined", self.agent.handle(call("other__write", {})))
        self.plugins.call.assert_not_called()
        self.agent.handle(call("seismic__summarize_catalog", {"catalog_id": "test"}))
        self.plugins.call.assert_called_once()

    def test_bad_arguments_do_not_execute(self):
        result = self.agent.handle(call("bash", {"command": "echo bad", "unexpected": True}))
        self.assertIn("Invalid", result)
        self.approve.assert_not_called()

    def test_failed_second_call_completes_batch_history(self):
        batch = {"role": "assistant", "tool_calls": [call("other__write", {}, "one"), call("other__write", {}, "two")]}
        self.approve.side_effect = [False]
        messages = self.agent.messages()
        def interrupt(*args, **kwargs):
            raise KeyboardInterrupt()
        with patch('agent_core.request', return_value=batch), self.assertRaises(KeyboardInterrupt):
            self.agent.turn(messages, 'test', on_event=interrupt)
        ids = [m['tool_call_id'] for m in messages if m['role'] == 'tool']
        self.assertEqual(ids, ['one', 'two'])

    def test_dependent_calls_deferred_until_model_observes_result(self):
        batch = {'role':'assistant','tool_calls':[call('seismic__summarize_catalog', {'catalog_id':'real'}, 'one'), call('other__write', {}, 'two')]}
        self.plugins.call.return_value = 'first result'
        messages = self.agent.messages()
        with patch('agent_core.request', side_effect=[batch, {'role':'assistant','content':'done'}]) as request:
            self.agent.turn(messages, 'test', on_event=lambda *args, **kw: None)
        self.plugins.call.assert_called_once()
        self.assertIn('Not executed', messages[-2]['content'])
        self.assertFalse(request.call_args_list[0].args[0]['parallel_tool_calls'])


class LoaderTests(unittest.TestCase):
    def test_stdio_state_schema_disclosure_and_shutdown(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root / 'plugins' / 'test'
            (folder / '.claude-plugin').mkdir(parents=True)
            (folder / '.claude-plugin/plugin.json').write_text('{"name":"test"}')
            (folder / '.mcp.json').write_text(json.dumps({'mcpServers': {'fixture': {'command': sys.executable, 'args': ['${CLAUDE_PLUGIN_ROOT}/server.py']}}}))
            (folder / 'skills' / 'fixture').mkdir(parents=True)
            (folder / 'skills/fixture/SKILL.md').write_text('---\nname: fixture\ndescription: A fixture skill\n---\nBODY_MUST_NOT_ENTER_PROMPT')
            (folder / 'server.py').write_text('from mcp.server import MCPServer\nmcp=MCPServer("fixture")\nn=0\n@mcp.tool()\ndef increment()->int:\n global n\n n+=1\n return n\n@mcp.tool()\ndef messages()->list[dict]|str:\n return [{"message_id":10,"text":"one"},{"message_id":11,"text":"two"}]\nmcp.run()\n')
            with Plugins({}, root) as plugins:
                self.assertIn('fixture__increment', [t['function']['name'] for t in plugins.tools])
                self.assertNotIn('BODY_MUST_NOT_ENTER_PROMPT', plugins.skill_prompt())
                self.assertIn('SKILL.md', plugins.skill_prompt())
                self.assertIn('1', plugins.call('fixture__increment', {}))
                self.assertIn('2', plugins.call('fixture__increment', {}))
                self.assertEqual(json.loads(plugins.call('fixture__messages', {})),
                                 [{'message_id':10,'text':'one'},{'message_id':11,'text':'two'}])
            self.assertFalse(plugins.thread.is_alive())

    def test_expansion_missing_variables_and_redaction(self):
        loader = Plugins({'TELEGRAM_BOT_TOKEN': 'fake-test-secret'})
        self.assertEqual(loader.expand('${TELEGRAM_BOT_TOKEN}', Path('.')), 'fake-test-secret')
        self.assertEqual(loader.redact('value fake-test-secret'), 'value [REDACTED]')
        with self.assertRaises(ValueError):
            loader.expand('${MISSING_TEST_VARIABLE_9382}', Path('.'))


if __name__ == '__main__':
    unittest.main()
