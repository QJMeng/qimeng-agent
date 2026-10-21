"""Offline HTTP checks for shared web-agent routing and approvals."""
import json
import threading
import time
import unittest
from http.server import ThreadingHTTPServer
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from unittest.mock import Mock

import web


class WebTests(unittest.TestCase):
    def setUp(self):
        web.events.clear()
        web.messages = []
        web.pending = None
        web.busy = False
        web.agent = Mock()
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), web.Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def post(self, path, data):
        request = Request(f'http://127.0.0.1:{self.server.server_port}{path}', data=json.dumps(data).encode(),
            headers={'Host':'127.0.0.1:8765', 'X-Token':web.TOKEN, 'Content-Type':'application/json'})
        with urlopen(request, timeout=5) as result:
            return json.load(result)

    def test_chat_uses_shared_agent_and_rejects_non_object(self):
        self.assertTrue(self.post('/chat', {'message':'hello'})['ok'])
        for _ in range(100):
            if web.agent.turn.called:
                break
            time.sleep(.01)
        web.agent.turn.assert_called_once_with(web.messages, 'hello', on_event=web.emit)
        with self.assertRaises(HTTPError) as error:
            self.post('/chat', [])
        self.assertEqual(error.exception.code, 400)

    def test_mcp_approval_denial(self):
        result = []
        worker = threading.Thread(target=lambda: result.append(web.approve('fixture__write', {'value':1}, 'approve-1')))
        worker.start()
        for _ in range(100):
            if web.pending:
                break
            time.sleep(.01)
        self.assertTrue(self.post('/approve', {'id':'approve-1', 'approve':False})['ok'])
        worker.join(timeout=2)
        self.assertEqual(result, [False])
        self.assertIn('fixture__write', web.events[-1]['command'])


if __name__ == '__main__':
    unittest.main()
