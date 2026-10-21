"""Terminal entry point; shared explicit loop plus local MCP plugins."""
import argparse
from pathlib import Path

from agent_core import Agent
from bash_tool import WORKDIR
from check_api import config
from plugin_loader import Plugins

ROOT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--ask', help='Run one terminal question and exit.')
    mode.add_argument('--telegram', action='store_true', help='Receive questions and approvals through Telegram.')
    parser.add_argument('--idle-timeout', type=int, help='Stop Telegram mode after this many idle seconds (optional).')
    args = parser.parse_args()
    if args.idle_timeout is not None and (not args.telegram or args.idle_timeout <= 0):
        parser.error('--idle-timeout requires --telegram and a positive number of seconds.')
    with Plugins(config) as plugins:
        plugins.announce()
        if args.telegram:
            from telegram_mode import TelegramMode
            TelegramMode(plugins, idle_timeout=args.idle_timeout).run()
            return
        agent = Agent(plugins)
        messages = agent.messages()
        print('Working directory:', WORKDIR)
        if args.ask:
            agent.turn(messages, args.ask)
            return
        print('Terminal chat: enter /exit to quit.')
        while True:
            try:
                question = input('You: ').strip()
            except (EOFError, KeyboardInterrupt):
                break
            if question == '/exit':
                break
            if question:
                agent.turn(messages, question)


if __name__ == '__main__':
    main()
