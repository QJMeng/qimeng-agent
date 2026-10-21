"""Harness-owned Telegram input, final replies, and explicit command approval."""
import json
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

from agent_core import Agent


class StopRequested(Exception):
    pass


def decode(text):
    if text.startswith('Tool error:') or text.startswith('MCP call failed'):
        raise RuntimeError('Telegram MCP call failed; check the local server.')
    try:
        value = json.loads(text)
    except ValueError:
        value = text
    # String returns from an MCP server may be encoded as a JSON string.
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            pass
    return value


class TelegramMode:
    def __init__(self, plugins, approval_timeout=300, idle_timeout=None):
        for name in ('telegram__send_message', 'telegram__wait_for_messages'):
            if name not in plugins.routes:
                raise ValueError('Telegram mode requires the Telegram plugin and local credentials.')
        self.plugins = plugins
        self.approval_timeout = approval_timeout
        self.idle_timeout = idle_timeout
        self.inbox = deque()
        self.seen_ids = set()
        self.agent = Agent(plugins, self.approve, hidden_tools={'telegram__wait_for_messages'})
        self.messages = self.new_messages()
        self.audit_path = Path.cwd() / 'work' / 'telegram-mode-audit.jsonl'

    def audit(self, kind, **data):
        self.audit_path.parent.mkdir(parents=True, exist_ok=True)
        row = {'utc': datetime.now(timezone.utc).isoformat(), 'event': kind, **data}
        with self.audit_path.open('a') as file:
            file.write(self.plugins.redact(json.dumps(row, ensure_ascii=False)) + '\n')
        print('Telegram:', kind, flush=True)

    def new_messages(self):
        messages = self.agent.messages()
        messages[0]['content'] += (
            '\n\nTelegram mode: the harness owns all message polling and approvals. '
            'Do not call wait_for_messages or ask the user to approve in prose. '
            'Call tools to propose actions. The harness sends your final answer; '
            'do not also send it through send_message. Use send_message only for '
            'a separate requested notification or progress update. Keep phone '
            'answers short and plain. Reply in the language the user uses. '
            'Never send secrets or entire catalog files. Ask for missing or '
            'ambiguous research parameters. Respect denied commands.')
        return messages

    def send(self, text):
        result = decode(self.plugins.call('telegram__send_message', {'text': self.plugins.redact(text)}))
        if not isinstance(result, dict) or not result.get('message_ids'):
            raise RuntimeError('Telegram delivery did not return message IDs; update the Telegram plugin.')
        return max(result['message_ids'])

    def poll(self, seconds=30):
        result = decode(self.plugins.call('telegram__wait_for_messages', {'seconds': seconds}))
        if result == 'No new messages.':
            return []
        if not isinstance(result, list):
            raise RuntimeError('Unexpected Telegram receive result.')
        fresh = []
        for item in result:
            if not isinstance(item, dict) or not isinstance(item.get('message_id'), int) or not isinstance(item.get('text'), str):
                raise RuntimeError('Invalid Telegram message format.')
            if item['message_id'] not in self.seen_ids:
                self.seen_ids.add(item['message_id'])
                fresh.append(item)
        return fresh

    def approve(self, name, arguments, call_id):
        # Messages queued before this prompt cannot approve a later command.
        self.inbox.extend(self.poll(0))
        display = arguments['command'] if name == 'bash' else name + '\n' + json.dumps(arguments, ensure_ascii=False)
        prompt_id = self.send('Run this command?\n' + display + '\nReply yes or no. Approval expires in ' + str(self.approval_timeout) + ' seconds.')
        self.audit('approval_requested', tool=name, call_id=call_id)
        deadline = time.monotonic() + self.approval_timeout
        while time.monotonic() < deadline:
            batch = self.poll(min(30, max(0, int(deadline - time.monotonic()))))
            for index, item in enumerate(batch):
                if item['message_id'] <= prompt_id:
                    # Preserve old research questions; never consume them as approvals.
                    self.inbox.append(item)
                    continue
                self.inbox.extend(batch[index + 1:])
                answer = item['text'].strip().lower()
                if answer == '/stop':
                    self.audit('approval_denied', tool=name, reason='stop')
                    raise StopRequested()
                approved = answer == 'yes'
                self.audit('approval_approved' if approved else 'approval_denied', tool=name)
                return approved
        self.audit('approval_denied', tool=name, reason='timeout')
        self.send('Approval timed out. The tool was not approved.')
        return False

    def on_event(self, kind, **data):
        if kind == 'usage':
            self.audit('usage', usage=data['usage'])
        elif kind == 'result':
            text = data['text']
            status = 'denied' if 'user declined' in text else 'error' if text.startswith(('Tool error:', 'Tool execution failed', 'MCP call failed')) else 'returned'
            tool = next((c['function']['name'] for m in reversed(self.messages) for c in m.get('tool_calls', []) if c['id'] == data['id']), 'unknown')
            self.audit('tool_result', tool=tool, status=status)

    def run(self):
        self.send('Qimeng agent is online. Send a question. Commands require yes/no approval. /new clears conversation; /stop stops the agent.')
        self.audit('online')
        last_activity = time.monotonic()
        failed_polls = 0
        stop_reason = 'stopped'
        try:
            while True:
                if self.idle_timeout is not None and time.monotonic() - last_activity >= self.idle_timeout:
                    self.audit('idle_timeout')
                    stop_reason = 'idle_timeout'
                    break
                if not self.inbox:
                    try:
                        self.inbox.extend(self.poll())
                        failed_polls = 0
                    except RuntimeError:
                        failed_polls += 1
                        self.audit('poll_failed', consecutive=failed_polls)
                        if failed_polls >= 3:
                            raise
                        time.sleep(1)
                        continue
                if not self.inbox:
                    continue
                item = self.inbox.popleft()
                text = item['text'].strip()
                last_activity = time.monotonic()
                if not text:
                    continue
                if text.lower() == '/stop':
                    break
                if text.lower() in ('/new', '/start'):
                    self.messages = self.new_messages()
                    self.send('New conversation. Send your research question.')
                    self.audit('conversation_reset')
                    continue
                if text.lower() in ('yes', 'no'):
                    self.send('No approval is pending. Send a new question.')
                    continue
                self.audit('user_turn')
                self.send('Working on your request...')
                try:
                    answer = self.agent.turn(self.messages, text, on_event=self.on_event)
                    self.send(answer)
                    self.audit('answer_sent')
                except StopRequested:
                    break
                except (Exception, SystemExit):
                    self.audit('turn_failed')
                    self.send('The request failed. Check the computer terminal and try again. No command is automatically approved.')
        except KeyboardInterrupt:
            pass
        except RuntimeError:
            stop_reason = 'connection_or_receive_error'
            self.audit('receive_failed')
        finally:
            try:
                self.send('Qimeng agent is offline (' + stop_reason + '). Messages sent while offline will be skipped at next startup.')
            except RuntimeError:
                self.audit('offline_notice_failed')
            self.audit('offline', reason=stop_reason)
