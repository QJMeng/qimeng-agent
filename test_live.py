"""Live integration checks with an explicit allowlist of harmless commands."""
import json
from unittest.mock import patch

import main
import bash_tool

def conversation():
    return [{'role': 'system', 'content': (main.ROOT / 'system_prompt.md').read_text()}]

def ask(messages, question):
    print('\nYou:', question)
    messages.append({'role': 'user', 'content': question})
    main.agent_turn(messages)

def tool_results(messages):
    return [item['content'] for item in messages if item['role'] == 'tool']

def execute_case(label, question, expected_command, check):
    messages = conversation()
    actual_run = bash_tool.run_bash
    executed = []
    def restricted_run(command):
        if command.strip() != expected_command:
            raise OSError('Live test only permits: ' + expected_command)
        executed.append(command)
        return actual_run(command)
    def approve(prompt):
        print(prompt + 'y (test-approved; exact allowlist enforced)')
        return 'y'
    with patch('builtins.input', approve), patch.object(bash_tool, 'run_bash', restricted_run):
        ask(messages, question)
    assert executed, 'Expected command was not executed'
    results = [json.loads(value) for value in tool_results(messages)]
    assert any(check(value) for value in results), label
    assert messages[-1]['role'] == 'assistant' and messages[-1].get('content')
    print('PASS:', label)

def run():
    messages = conversation()
    with patch.object(bash_tool, 'run_bash', side_effect=AssertionError('No execution allowed')):
        ask(messages, 'Remember the project label: seismic-check-729. Reply briefly without tools.')
        ask(messages, 'What project label did I just give you? Reply without tools.')
    assert 'seismic-check-729' in messages[-1]['content']
    print('PASS: continuous conversation')

    execute_case('approved execution',
                 'Use bash to run exactly printf harness-live-ok and report the output. Do not use other commands.',
                 'printf harness-live-ok', lambda result: result.get('exit_code') == 0 and result.get('output') == 'harness-live-ok')
    execute_case('failed command returned to model',
                 'Use bash to run exactly doesnotexist. Then explain its exit code and error. Do not try other commands.',
                 'doesnotexist', lambda result: result.get('exit_code') == 127 and 'not found' in result.get('output', ''))

    messages = conversation()
    def deny(prompt):
        print(prompt + 'n (test denial)')
        return 'n'
    with patch('builtins.input', deny), patch.object(bash_tool, 'run_bash', side_effect=AssertionError('Denied command was executed')):
        ask(messages, 'Use bash to run exactly printf denial-check. If I decline, acknowledge the denial and stop without trying another command.')
    assert tool_results(messages) and all('declined' in value for value in tool_results(messages))
    assert messages[-1]['role'] == 'assistant' and messages[-1].get('content')
    print('PASS: denial returned to model; execution never called')

if __name__ == '__main__':
    run()
