"""One shell tool, with approval, timeout, and bounded output."""
import json
import os
import signal
import subprocess
import tempfile
from pathlib import Path

WORKDIR = Path.cwd().resolve()
TIMEOUT = 60
OUTPUT_LIMIT = 10_000
SHELL = ['powershell', '-NoProfile', '-Command'] if os.name == 'nt' else ['bash', '-c']
TOOL = {'type': 'function', 'function': {
    'name': 'bash',
    'description': f'Run a command in {WORKDIR} after user approval. Uses PowerShell on Windows, bash otherwise. Returns output and exit code; 60 second timeout.',
    'parameters': {'type': 'object', 'properties': {'command': {'type': 'string'}},
                   'required': ['command'], 'additionalProperties': False}}}

def run_bash(command):
    timed_out = False
    with tempfile.TemporaryFile() as output:
        process = subprocess.Popen(SHELL + [command], cwd=WORKDIR,
                                   stdin=subprocess.DEVNULL, stdout=output,
                                   stderr=subprocess.STDOUT, start_new_session=os.name != 'nt')
        try:
            process.wait(timeout=TIMEOUT)
        except subprocess.TimeoutExpired:
            timed_out = True
            if os.name == 'nt':
                subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], capture_output=True)
            else:
                os.killpg(process.pid, signal.SIGKILL)
            process.wait()
        size = output.tell()
        output.seek(max(0, size - OUTPUT_LIMIT * 4))
        text = output.read().decode('utf-8', errors='replace')
    return json.dumps({'exit_code': process.returncode, 'timed_out': timed_out,
                       'output': text[-OUTPUT_LIMIT:],
                       'truncated': size > OUTPUT_LIMIT * 4 or len(text) > OUTPUT_LIMIT}, ensure_ascii=False)

def handle_tool(call):
    if call['function']['name'] != 'bash':
        return 'Unknown tool. Only bash is available.'
    try:
        arguments = json.loads(call['function']['arguments'])
        command = arguments['command']
        if not isinstance(command, str) or not command.strip():
            return 'Invalid command: expected a nonempty string.'
    except (ValueError, KeyError, TypeError):
        return 'Invalid tool arguments: expected JSON with a command string.'
    print('\nRequested command:\n' + command)
    try:
        approved = input('Approve execution? [y/N]: ').strip().lower() == 'y'
    except (EOFError, KeyboardInterrupt):
        approved = False
    if not approved:
        return 'The user declined to run this command.'
    try:
        result = run_bash(command)
    except OSError as error:
        result = json.dumps({'error': str(error)}, ensure_ascii=False)
    print('Tool result:', result)
    return result
