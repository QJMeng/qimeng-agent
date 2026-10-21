"""Offline approval correlation, queue ownership, and phone routing checks."""
import json
import unittest
from unittest.mock import Mock, patch

from telegram_mode import TelegramMode


class PhoneTests(unittest.TestCase):
    def mode(self):
        plugins = Mock()
        plugins.routes = {'telegram__send_message': (), 'telegram__wait_for_messages': (), 'seismic__get_event_details': ()}
        plugins.tools = [{'type':'function','function':{'name':name,'parameters':{'type':'object'}}} for name in plugins.routes]
        plugins.skill_prompt.return_value = ''
        plugins.redact.side_effect = lambda text: text
        mode = TelegramMode(plugins)
        mode.audit = Mock()
        mode.send = Mock(return_value=100)
        return mode

    def test_poll_hidden_and_fabricated_call_blocked(self):
        mode = self.mode()
        self.assertNotIn('telegram__wait_for_messages', [t['function']['name'] for t in mode.agent.tools])
        result = mode.agent.handle({'id':'x','function':{'name':'telegram__wait_for_messages','arguments':'{}'}})
        self.assertIn('reserved', result)
        mode.plugins.call.assert_not_called()

    def test_stale_yes_cannot_approve_new_command(self):
        mode = self.mode()
        mode.poll = Mock(side_effect=[[], [{'message_id':99,'text':'yes'}], [{'message_id':101,'text':'no'}]])
        self.assertFalse(mode.approve('bash', {'command':'printf test'}, 'x'))
        self.assertEqual(list(mode.inbox), [{'message_id':99,'text':'yes'}])

    def test_yes_approves_once_and_preserves_later_questions(self):
        mode = self.mode()
        later = {'message_id':102,'text':'Next question'}
        mode.poll = Mock(side_effect=[[], [{'message_id':101,'text':'YES'}, later]])
        self.assertTrue(mode.approve('bash', {'command':'printf test'}, 'x'))
        self.assertEqual(list(mode.inbox), [later])

    def test_anything_other_than_yes_denies_without_new_turn(self):
        mode = self.mode()
        mode.poll = Mock(side_effect=[[], [{'message_id':101,'text':'y'}]])
        self.assertFalse(mode.approve('bash', {'command':'printf test'}, 'x'))
        self.assertFalse(mode.inbox)

    def test_timeout_denies(self):
        mode = self.mode()
        mode.poll = Mock(return_value=[])
        with patch('telegram_mode.time.monotonic', side_effect=[0,301]):
            self.assertFalse(mode.approve('bash', {'command':'printf test'}, 'x'))
        self.assertIn('timed out', mode.send.call_args.args[0])

    def test_duplicate_messages_not_replayed(self):
        mode = self.mode()
        mode.plugins.call.return_value = json.dumps([{'message_id':10,'text':'test'}])
        self.assertEqual(len(mode.poll(0)), 1)
        self.assertEqual(mode.poll(0), [])

    def test_real_mcp_list_result_reaches_phone_poll(self):
        from types import SimpleNamespace
        from plugin_loader import tool_text
        mode = self.mode()
        payload = [{'message_id':1,'text':'one'},{'message_id':2,'text':'two'}]
        result = SimpleNamespace(structured_content={'result':payload}, content=[])
        mode.plugins.call.return_value = tool_text(result)
        self.assertEqual(mode.poll(0), payload)

    def test_denial_never_executes_bash(self):
        mode = self.mode()
        mode.poll = Mock(side_effect=[[], [{'message_id':101,'text':'no'}]])
        with patch('bash_tool.run_bash') as run:
            result = mode.agent.handle({'id':'x','function':{'name':'bash','arguments':'{"command":"printf blocked"}'}})
            self.assertIn('declined', result)
            run.assert_not_called()

    def test_questions_share_history_and_final_answer_is_sent(self):
        mode = self.mode()
        mode.poll = Mock(return_value=[{'message_id':1,'text':'Remember a label'}, {'message_id':2,'text':'What label?'}, {'message_id':3,'text':'/stop'}])
        def turn(messages, question, on_event=None):
            messages.append({'role':'user','content':question})
            return 'test answer'
        mode.agent.turn = Mock(side_effect=turn)
        mode.run()
        self.assertEqual(mode.agent.turn.call_count, 2)
        histories = [c.args[0] for c in mode.agent.turn.call_args_list]
        self.assertIs(histories[0], histories[1])
        self.assertEqual(sum(c.args[0] == 'test answer' for c in mode.send.call_args_list), 2)


if __name__ == '__main__':
    unittest.main()
