"""Verify chat and tool calling without executing any commands."""
import json
import ssl
import certifi
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

config = {}
for line in Path(__file__).with_name('.env').read_text().splitlines():
    if '=' in line and not line.lstrip().startswith('#'):
        key, value = line.split('=', 1)
        config[key.strip()] = value.strip().strip('\"\x27')

def request(payload, on_usage=None):
    req = Request(config['BASE_URL'].rstrip('/') + '/chat/completions',
                  data=json.dumps({'model': config['MODEL'], **payload}).encode(),
                  headers={'Authorization': 'Bearer ' + config['API_KEY'],
                           'Content-Type': 'application/json'})
    try:
        context = ssl.create_default_context()
        context.load_verify_locations(cafile=certifi.where())
        with urlopen(req, timeout=45, context=context) as response:
            result = json.load(response)
    except HTTPError as error:
        detail = error.read().decode().replace(config['API_KEY'], '[REDACTED]')
        print(f'HTTP {error.code}: {detail[:1000]}')
        raise SystemExit(1)
    except URLError as error:
        print('Connection failed:', error.reason)
        raise SystemExit(2)
    if on_usage:
        on_usage(result.get('usage') or {})
    else:
        print('Usage:', result.get('usage'))
    return result['choices'][0]['message']

if __name__ == '__main__':
    print('Chat:', request({'messages': [{'role': 'user', 'content': 'Reply with API connection successful.'}]}).get('content'))
    message = request({
        'messages': [{'role': 'user', 'content': 'Use bash to print hello. Only propose the command.'}],
        'tools': [{'type': 'function', 'function': {
            'name': 'bash', 'description': 'Run a shell command after user approval.',
            'parameters': {'type': 'object', 'properties': {'command': {'type': 'string'}}, 'required': ['command'], 'additionalProperties': False}}}],
        'tool_choice': {'type': 'function', 'function': {'name': 'bash'}}})
    calls = message.get('tool_calls', [])
    if not calls or any(call['function']['name'] != 'bash' for call in calls):
        raise SystemExit('Tool calling check failed.')
    print('Tool calling passed. Proposed commands were NOT executed.')
