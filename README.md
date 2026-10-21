# qimeng-agent

A small Python agent for the AI in Research coursework. Chat in a local web page or terminal using an OpenAI-compatible Chat Completions API. The explicit agent loop offers bash plus tools discovered from local MCP plugins, without agent frameworks.

## Requirements

- macOS, Linux, or Windows
- Python 3.11 or newer, managed automatically by uv if needed
- [uv](https://docs.astral.sh/uv/getting-started/installation/)
- An API key and a model supporting tool calling

## Install

Download this repository and open a terminal in its folder. Install uv if necessary:

macOS / Linux:

```sh
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Restart your terminal after installation. On macOS / Linux, you can also run `source "$HOME/.local/bin/env"` to make uv available immediately.

Windows PowerShell:

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Then install the project dependencies:

```sh
uv sync --locked
```

## Configure

Copy the configuration template:

macOS / Linux:

```sh
cp .env.example .env
```

Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

Edit `.env` locally. Set `BASE_URL`, `API_KEY`, and `MODEL`. The example uses the OpenAI endpoint and `gpt-4.1-mini`; choose a model available to your account that supports tool calling. API usage may incur charges. Your ChatGPT subscription does not supply API credit.

Never upload `.env` or share your key. `.env` is excluded by `.gitignore`. TLS certificate verification stays enabled, with certifi supplying additional trusted certificate authorities.

## Web chat

From the project folder:

```sh
uv run web.py
```

Open http://127.0.0.1:8765 in your browser. The server binds only to your computer's loopback address. Enter a message and select Send. Each shell command and MCP tool outside the allow list has Approve and Deny buttons. The page shows tool output and per-call input, cached input when available, and output token counts.

Only one question runs at a time. Approval expires after five minutes and defaults to denial. The server keeps conversation history in memory; restarting clears it. Keep the terminal open while using the page and press Ctrl+C to stop the server.

## Terminal chat

```sh
uv run main.py
```

Enter `y` to approve a command; any other response denies it. Enter `/exit` to quit.

## Plugins and permissions

Both entry points discover folders under `plugins/` with
`.claude-plugin/plugin.json`. They expand `.mcp.json` environment references,
start stdio MCP servers and keep the sessions open until exit. Configure
TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in local `.env` before starting the
bundled Telegram plugin. Run only one polling host per bot at a time; startup
skips queued messages even when using normal terminal or web chat.

Loaded plugins:
- `qjmeng-telegram`: send and receive in the configured private Telegram chat.
- `qjmeng-seismic`: USGS catalog, depths, mechanisms, and exploratory b values.

The model receives MCP tool schemas beside bash, with names such as
`seismic__search_earthquakes`. The system prompt lists skill names,
descriptions and absolute paths; skill bodies enter context only if the
model reads them with an approved bash command. Credentials are passed to
server processes via environment variables, not model tool parameters.
Public catalogs and calculations stay in session-local files; tools return
summaries. Research files under work/qjmeng-seismic/session-* are removed
when the MCP session closes. Only explicit permanent exports should be kept;
crashed sessions are cleaned at the next startup after their owner exits.

`settings.json` explicitly allows Telegram sending and the five public-data
research tools. Bash always asks, even if someone adds it to the allow list.
Every other MCP tool asks before execution; terminal uses y/N and web uses
Approve/Deny. A denied tool is not executed and denial is returned to the model.
Startup prints loaded plugins/tools/skills; the first API call reports actual
input/output token usage, including the context cost of offered tools.

One terminal question:

```sh
uv run main.py --ask 'Get details for USGS event ci40925991 using the seismic plugin.'
```

## Telegram chat and approvals

```sh
uv run main.py --telegram
```

Wait for the online message on your phone, then send a question to your bot.
The computer must stay running. Only the configured private chat is accepted.
The harness owns polling; `telegram__wait_for_messages` is hidden from the
model and blocked even if a model attempts to call it by name.

The harness runs the same loop as terminal/web and sends the final answer.
It maintains conversation history between messages. `/new` starts a fresh
conversation; `/stop` stops phone mode; Ctrl+C stops it from the computer.
Startup skips offline messages. Do not run another host with this bot.

Every bash command and every tool outside settings.json's allow list needs
approval in the Telegram chat. Reply `yes` after the approval prompt to approve;
anything else denies. Approval expires after 300 seconds and defaults to deny.
The reply must have a message ID newer than the approval prompt, so a queued
old yes cannot authorize a later command. One yes approves one tool call.
Ordinary queued questions are kept for later turns; replies consumed as denial
are not replayed as new instructions. Unexpected bare yes/no messages outside
an approval are ignored. Full command and arguments are shown for review.

For an optionally bounded session:

```sh
uv run main.py --telegram --idle-timeout 600
```

Progress and short final answers go to the phone; whole catalogs remain in
local work files. Event/usage audit records (without full questions or results)
are stored in work/telegram-mode-audit.jsonl. Treat tool results as untrusted
content. Bots are not end-to-end encrypted; never send secrets. Keep command
approval enabled. Protect and revoke a leaked bot token with BotFather.


Offline checks:

```sh
uv run python -m unittest test_telegram_mode test_plugins test_web -v
```

Optional live plugin/harness test (uses model API tokens and sends a Telegram
message; only exact skill-reading shell commands are test-approved):

```sh
uv run test_harness_live.py
```

## Working directory and execution

Commands start in the directory where you launch the program, shown in the interface. A `cd` command does not persist into the next tool call. To work elsewhere, use explicit paths or run `uv run --project /path/to/qimeng-agent /path/to/qimeng-agent/web.py` from that directory.

The tool uses bash on macOS / Linux and PowerShell on Windows. stdout and stderr are combined, with the exit code returned. Commands have a 60-second timeout and output is limited to the last 10,000 characters. Each question permits up to 20 tool rounds followed by a text-only request.

The working directory is not a security sandbox. Review commands before approving them. Commands can access files allowed by your user account, and returned output is sent to the model service. Model instructions discourage reading secrets; they are not an access-control mechanism.

## Check that it works

Ask `What files are in this folder?` and approve the proposed listing command. You should see repository files in the tool output and an explanation from the model. Ask it to remember a label, then ask for the label again. Ask it to run `doesnotexist` and explain the error. Finally request a harmless command and deny it; the model should acknowledge the denial.

Optional automated live integration test (uses your API account and incurs token usage):

```sh
uv run test_live.py
```

This test uses two exact bash commands and is intended for macOS / Linux. It supplies test approval and denial responses automatically and rejects other commands. See `LIVE_TEST_RESULTS.md` for recorded results. Windows operation has not been verified.

## Code map

- `main.py`: terminal entry point and single-question mode
- `agent_core.py`: shared explicit loop and tool approval policy
- `plugin_loader.py`: plugin discovery, skill metadata, MCP client lifecycle and dispatch
- `settings.json`: explicit MCP tool allow list
- `telegram_mode.py`: harness-owned phone input, final replies and yes/no approvals
- `web.py` / `web.html`: local server, web interface, and web approval adapter
- `bash_tool.py`: tool definition, command approval, and command execution
- `check_api.py`: API configuration, HTTPS requests, token reporting, and connection checks
- `system_prompt.md`: editable model instructions
- `pyproject.toml` / `uv.lock`: project dependencies and locked versions

## Status

Week 3 in progress: `plugins/qjmeng-telegram/` contains the first Telegram MCP
plugin. All four local mocked checks passed (MCP tool discovery and dispatch,
chat filtering and offsets, startup backlog and Unicode splitting, and secret-safe errors).
The student configured the bot locally; a live stdio MCP SDK client discovered
both tools and successfully sent a test message. The student confirmed receipt
and completed a live reply/acknowledgement test; the duplicate check passed.
The live wrong-chat test logged and discarded the student's message with a
test-only allowed chat ID; local credentials were unchanged.
The live restart test confirmed that a queued offline123 message was skipped
and a fresh123 message sent after startup was received and acknowledged.
Codex CLI also loaded the server and successfully called send_message using
temporary configuration; the student confirmed receipt of its greeting on their phone.
The first plugin's implementation and acceptance checks are complete.
The research plugin `plugins/qjmeng-seismic/` now provides five tools for
catalog search, depth summaries, event details, mechanism classification and
b-value estimation. Ten research-plugin offline tests and live stdio MCP checks passed;
Codex host calls also passed. The Salton Sea 100 km, five-year, M>=3.0 case
returned 205 events; see the plugin's VALIDATION.md for scientific limitations.
Harness plugin loading is implemented for terminal and web. Six loader/permission
tests plus two web HTTP tests passed and a real model selected both Telegram and seismic tools through
the shared loop; no API key or bot token appeared in model history, and MCP
clients closed cleanly. The first model call used 1636 input tokens in this
validation run. See work/harness-plugin-live-results.json for local evidence.
The student confirmed the harness greeting and completed the context/skill
understanding checkpoint. Telegram input mode is now implemented with hidden
model polling, message-correlated approval and conversation history. Nine
phone-mode tests passed, including the MCP structured-list regression; all 18
harness tests passed, including dependency-order enforcement. An initial live receive-format failure was fixed.
Live phone approvals and final replies now work and were confirmed by the
student, including explicit refusal. The first phone research query exposed
a model batch containing dependent calls with invented catalog IDs. Calls are
now serialized, deferred calls must use returned IDs, and invalid IDs return
actionable errors. A real-model complete research chain subsequently passed.
Session data auto-cleanup passed both offline and live checks. The repeated
phone research query successfully ran all four dependent tools and sent the
final answer; the student confirmed satisfaction with the result. The
scientific-review checkpoint is accepted for this exploratory validation case,
with all documented limitations retained. The course submission package contains both plugins under
week-3/submissions/qjmeng/ in the homework repository.

Implemented: API calls, conversation history, one bash tool, command approval, tool loop limits, terminal and web interfaces, and token usage reporting. Real-model integration checks passed for conversation, execution, command failure, and denial. The author has confirmed that the web interface works. Windows has not been tested. The harness repository is public. Both plugin folders and setup instructions are included for week 3; Windows operation remains unverified.

## License

MIT. See `LICENSE`.
