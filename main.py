"""A small explicit agent loop; no agent frameworks."""
from pathlib import Path
from check_api import request
from bash_tool import TOOL, WORKDIR, handle_tool

ROOT = Path(__file__).resolve().parent

def agent_turn(messages):
    # Send the full conversation and the single tool definition each time.
    for round_number in range(21):
        reply = request({'messages': messages, 'tools': [TOOL],
                         'tool_choice': 'none' if round_number == 20 else 'auto'})
        messages.append(reply)
        calls = reply.get('tool_calls', [])
        if not calls:
            print('Agent:', reply.get('content') or '(No text response)')
            return
        for call in calls:
            result = handle_tool(call) if round_number < 20 else 'Tool round limit reached.'
            messages.append({'role': 'tool', 'tool_call_id': call['id'], 'content': result})
    print('Tool round limit reached. Ask another question or narrow the task.')

def main():
    messages = [
        {'role': 'system', 'content': (ROOT / 'system_prompt.md').read_text()},
    ]
    print('Terminal chat: enter /exit to quit.')
    print('Working directory:', WORKDIR)
    while True:
        try:
            question = input('You: ').strip()
        except (EOFError, KeyboardInterrupt):
            break
        if question == '/exit':
            break
        if not question:
            continue
        messages.append({'role': 'user', 'content': question})
        agent_turn(messages)

if __name__ == '__main__':
    main()
