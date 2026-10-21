"""Real-model chained research test; public data is removed at session exit.

Uses API tokens. Only exact cat commands for the seismic skill are approved.
The temporary plugin root loads research only, avoiding a second bot poller.
"""
import json
import shlex
import tempfile
from pathlib import Path

from agent_core import Agent
from check_api import config
from plugin_loader import Plugins

ROOT = Path(__file__).resolve().parent


def run():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        (root/'plugins').mkdir()
        (root/'plugins/qjmeng-seismic').symlink_to(ROOT/'plugins/qjmeng-seismic', target_is_directory=True)
        with Plugins(config, root=root) as plugins:
            allowed_reads = {('cat', skill['path']) for skill in plugins.skills}
            def approve(name, arguments, call_id):
                try:
                    return name == 'bash' and tuple(shlex.split(arguments['command'])) in allowed_reads
                except (KeyError, ValueError):
                    return False
            agent = Agent(plugins, approve)
            messages = agent.messages()
            def emit(kind, **data):
                if kind == 'result':
                    print('Tool result returned:', data['id'], flush=True)
                elif kind == 'assistant':
                    print(data['text'], flush=True)
            agent.turn(messages,
                'Query earthquakes from 2021-10-21T00:00:00Z to 2026-10-21T00:00:00Z within 100 km of 33.3,-115.8 and M>=3.0. '
                'Using that catalog, summarize hypocentral depths, summarize mechanism classes and coverage, and calculate pooled b with user-specified Mc=3.0 and magnitude_bin_width=0. '
                'Report all requested statistics and limitations. Use plugin tools; call search first and wait for its actual catalog_id before requesting the statistics. Never read a whole raw catalog using bash.', on_event=emit)
            calls = {c['id']:c['function']['name'] for m in messages for c in m.get('tool_calls', [])}
            outputs = {calls[m['tool_call_id']]:m['content'] for m in messages if m['role']=='tool'}
            expected = {'seismic__search_earthquakes','seismic__summarize_catalog','seismic__summarize_mechanisms','seismic__calculate_b_value'}
            assert expected <= outputs.keys(), 'A requested research tool was omitted.'
            for name in expected:
                assert not outputs[name].startswith(('Tool error:', 'Not executed', 'MCP call failed')), name + ' did not complete.'
            search = json.loads(outputs['seismic__search_earthquakes'])
            b = json.loads(outputs['seismic__calculate_b_value'])
            assert b['catalog_id'] == search['catalog_id'] and b['n'] == search['count']
            snapshot = Path(search['snapshot_path'])
            assert snapshot.exists()
            print('PASS: all requested chained tools succeeded with the returned catalog ID.', flush=True)
        assert not snapshot.exists(), 'Session results were retained unexpectedly.'
        print('PASS: session data files were automatically deleted.', flush=True)


if __name__ == '__main__':
    run()
