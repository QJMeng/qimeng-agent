"""Local web chat with explicit tool approval and an agent loop."""
import json
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from bash_tool import WORKDIR
from check_api import config
from agent_core import Agent
from plugin_loader import Plugins

ROOT = Path(__file__).resolve().parent
TOKEN = secrets.token_urlsafe(32)
lock = threading.Condition()
events = []
messages = []
agent = None
busy = False
pending = None

def emit(kind, **data):
    with lock:
        events.append({'kind': kind, **data})

def approve(name, arguments, call_id):
    global pending
    with lock:
        pending = {'id': call_id, 'decision': None}
        display = arguments.get('command') if name == 'bash' else name + '\n' + json.dumps(arguments, ensure_ascii=False)
        emit('command', id=call_id, command=display)
        decided = lock.wait_for(lambda: pending['decision'] is not None, timeout=300)
        approved = bool(decided and pending['decision'])
        pending = None
        return approved

def turn(question):
    global busy
    try:
        agent.turn(messages, question, on_event=emit)
    except (Exception, SystemExit):
        emit('error', text='The request failed. Check local configuration and retry.')
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
            if not isinstance(data, dict):
                raise ValueError()
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
    with Plugins(config) as plugins:
        plugins.announce()
        agent = Agent(plugins, approve=approve)
        messages = agent.messages()
        print('Open http://127.0.0.1:8765 in your browser.')
        print('Working directory:', WORKDIR)
        with ThreadingHTTPServer(('127.0.0.1', 8765), Handler) as server:
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                pass
