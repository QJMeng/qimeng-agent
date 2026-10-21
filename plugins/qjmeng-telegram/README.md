# qjmeng-telegram

A stdio MCP server with two tools: `send_message(text)` sends plain text only
to the configured private chat, and `wait_for_messages(seconds=30)` long-polls
for new text from that chat (maximum 50 seconds). It uses the official MCP
Python SDK v2 and Telegram Bot API. No public port or webhook is needed.

## Configure

Create a bot with https://t.me/BotFather (`/newbot`). In the harness's local,
gitignored `.env`, enter these values yourself; never paste tokens into AI chat:

```dotenv
TELEGRAM_BOT_TOKEN=replace_with_your_bot_token
TELEGRAM_CHAT_ID=replace_with_your_positive_private_chat_id
```

Open your bot on your phone and send `/start`. The token is a password; revoke
it through BotFather `/revoke` if leaked. The chat ID is a numeric identifier.
The host must export these variables; the server does not read arbitrary `.env`
files automatically. Requires `uv`; Python >=3.11 is selected by the script.

## Claude Code

From the harness root, after entering your credentials locally:

```sh
set -a
source .env
set +a
claude plugin validate plugins/qjmeng-telegram
claude --plugin-dir plugins/qjmeng-telegram
```

Check `/mcp`, then request: "Send hello from Claude Code to my Telegram."
Confirm delivery on your phone. Only run one host with this bot at a time.

## Codex

The plugin's `.mcp.json` is for Claude-compatible plugin loaders. To use the
server in Codex, run the following in your own terminal; the shell reads the
token locally and the command saves it in Codex's local MCP configuration:

```sh
set -a
source .env
set +a
codex mcp add qjmeng-telegram \
  --env TELEGRAM_BOT_TOKEN="$TELEGRAM_BOT_TOKEN" \
  --env TELEGRAM_CHAT_ID="$TELEGRAM_CHAT_ID" \
  -- uv run --script "$PWD/plugins/qjmeng-telegram/server.py"
```

Open a new Codex session and ask it to send a hello message. MCP registration
exposes tool schemas; it does not automatically load this plugin's skill into
Codex. Ask the agent to read `skills/telegram/SKILL.md` when using it.
Never share the generated credential configuration.

## qimeng-agent

Keep this folder under `plugins/`. The manifest identifies the plugin and
`.mcp.json` declares its stdio command and environment substitutions. The
harness plugin loader is implemented for normal terminal and web chat. Run
`uv run main.py` or `uv run web.py` from the harness root. The host loads the
local .env and offers these tools automatically. Sending is on its explicit
allow list; polling requires approval in normal chat. Phone input and
approval-by-reply mode are available with `uv run main.py --telegram`.

The host will add MCP tool names, descriptions, and parameter schemas to the
model's tools list. It will list skill metadata and its path in the system
prompt, and the model reads the full skill only when needed. Credentials stay
in the server environment, not in tool parameters or tool results.

## Checks and safety

Offline tests (mocked Telegram, no credentials or real messages):

```sh
uv run --script plugins/qjmeng-telegram/test_server.py
```

The server skips queued updates on startup, advances an in-memory offset for
each received update, discards other chats, and logs drops to stderr. stdout is
reserved for MCP. Text over Telegram's message limit is split conservatively
using UTF-16 units. HTTP calls have timeouts and errors omit secret URLs.
Stop any other poller before starting this server; existing webhooks must be
removed by the bot owner before using long polling.

Only your configured private chat gets in. Bot messages are not end-to-end
encrypted: do not send secrets or whole files. This plugin does not execute
shell commands; when attached to a harness with bash, keep every command's
approval enabled. The harness must own polling during Telegram mode so the
model cannot consume approval replies.

Live safety and interoperability checks have passed. The student confirmed
receipt of the Codex-host greeting on their phone.

Status: four offline tests passed on Python 3.13 with the official MCP SDK v2.
Live stdio SDK client testing discovered both tools and successfully called
send_message against Telegram. The student confirmed phone receipt, replied
with test123, and received the automatic acknowledgement. wait_for_messages
received that reply and an immediate second poll did not repeat it.
Live filtering also passed: a test-only process used a different allowed chat
ID, the student sent a message from their actual chat, and stderr recorded
the dropped update without returning it as an accepted message. The local
.env was not changed. The restart test also passed: offline123 was confirmed
queued before startup and absent after startup; fresh123 sent after startup
was received and acknowledged on the phone. Codex CLI v0.163.0-alpha.10.2
loaded the stdio server and called send_message once, returning
"Sent 1 message(s) to the configured chat." with isError=false.
This used ephemeral CLI configuration, environment-variable credentials,
and a per-tool approval for the authorized send_message test; no global
configuration was modified. An initial attempt was blocked by the CLI's
noninteractive approval policy before sending. Final phone confirmation of
the Codex greeting was received from the student. Credentials were loaded only from local .env.

Phone mode now uses returned send_message message IDs to correlate approval
replies; only messages newer than the approval prompt can approve its tool.
The send result is JSON text containing confirmation and message_ids.
