"""Local web chat with explicit tool approval and an agent loop."""
import json
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from bash_tool import TOOL, WORKDIR, run_bash
from check_api import request

ROOT = Path(__file__).resolve().parent
TOKEN = secrets.token_urlsafe(32)
lock = threading.Condition()
events = []
messages = [{'role': 'system', 'content': (ROOT / 'system_prompt.md').read_text()}]
busy = False
pending = None

def emit(kind, **data):
    with lock:
        events.append({'kind': kind, **data})

def tool(call):
    global pending
    try:
        command = json.loads(call['function']['arguments'])['command']
        if call['function']['name'] != 'bash' or not isinstance(command, str) or not command.strip():
            raise ValueError('Invalid bash call')
    except (ValueError, KeyError, TypeError):
        return 'Invalid tool arguments.'
    with lock:
        pending = {'id': call['id'], 'decision': None}
        emit('command', id=call['id'], command=command)
        decided = lock.wait_for(lambda: pending['decision'] is not None, timeout=300)
        approved = decided and pending['decision']
        pending = None
    if approved:
        try:
            result = run_bash(command)
        except OSError as error:
            result = json.dumps({'error': str(error)})
    else:
        result = 'The user declined to run this command.'
    emit('result', id=call['id'], text=result)
    return result

def turn(question):
    global busy
    messages.append({'role': 'user', 'content': question})
    try:
        for number in range(21):
            reply = request({'messages': messages, 'tools': [TOOL],
                             'tool_choice': 'none' if number == 20 else 'auto'},
                            on_usage=lambda usage: emit('usage', usage=usage))
            messages.append(reply)
            calls = reply.get('tool_calls', [])
            if not calls:
                emit('assistant', text=reply.get('content') or '(No text response)')
                break
            for call in calls:
                result = tool(call) if number < 20 else 'Tool round limit reached.'
                messages.append({'role': 'tool', 'tool_call_id': call['id'], 'content': result})
        else:
            emit('error', text='Tool round limit reached.')
    except (Exception, SystemExit):
        emit('error', text='The API request failed. Check the server terminal for details and retry.')
        # Complete any unanswered calls so the next request has valid history.
        if messages[-1].get('tool_calls'):
            for call in messages[-1]['tool_calls']:
                messages.append({'role':'tool','tool_call_id':call['id'],'content':'Request interrupted.'})
    finally:
        with lock:
            busy = False
        emit('done')

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def respond(self, status, data, content_type='application/json'):
        body = data.encode() if isinstance(data, str) else json.dumps(data).encode()
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)

    def authorized(self):
        return self.headers.get('Host') in ('127.0.0.1:8765', 'localhost:8765')

    def do_GET(self):
        if not self.authorized():
            return self.respond(403, {'error': 'Invalid host'})
        if self.path == '/':
            html = (ROOT / 'web.html').read_text().replace('__TOKEN__', TOKEN)
            return self.respond(200, html, 'text/html; charset=utf-8')
        if self.path == '/events' and self.headers.get('X-Token') == TOKEN:
            with lock:
                return self.respond(200, {'events': list(events), 'busy': busy, 'cwd': str(WORKDIR)})
        self.respond(404, {'error': 'Not found'})

    def do_POST(self):
        global busy
        if not self.authorized() or self.headers.get('X-Token') != TOKEN:
            return self.respond(403, {'error': 'Access denied'})
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 32000:
                raise ValueError()
            data = json.loads(self.rfile.read(length))
        except (ValueError, TypeError):
            return self.respond(400, {'error':'Invalid request'})
        with lock:
            if self.path == '/chat':
                question = data.get('message')
                if not isinstance(question, str) or not question.strip():
                    return self.respond(400, {'error':'Enter a message'})
                if busy:
                    return self.respond(409, {'error':'Wait for the current response'})
                busy = True
                emit('user', text=question)
                threading.Thread(target=turn, args=(question,), daemon=True).start()
            elif self.path == '/approve':
                if not pending or data.get('id') != pending['id'] or pending['decision'] is not None or type(data.get('approve')) is not bool:
                    return self.respond(409, {'error':'No matching pending command'})
                pending['decision'] = data['approve']
                lock.notify_all()
            else:
                return self.respond(404, {'error':'Not found'})
        self.respond(200, {'ok': True})

if __name__ == '__main__':
    print('Open http://127.0.0.1:8765 in your browser.')
    print('Working directory:', WORKDIR)
    ThreadingHTTPServer(('127.0.0.1', 8765), Handler).serve_forever()
