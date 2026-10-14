# qimeng-agent

A small Python agent for the AI in Research week 2 homework. Chat in a local web page or terminal using an OpenAI-compatible Chat Completions API. There is exactly one tool, `bash`, and the agent loop is written directly without agent frameworks.

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

Open http://127.0.0.1:8765 in your browser. The server binds only to your computer's loopback address. Enter a message and select Send. Each proposed command has Approve and Deny buttons. The page shows tool output and per-call input, cached input when available, and output token counts.

Only one question runs at a time. Approval expires after five minutes and defaults to denial. The server keeps conversation history in memory; restarting clears it. Keep the terminal open while using the page and press Ctrl+C to stop the server.

## Terminal chat

```sh
uv run main.py
```

Enter `y` to approve a command; any other response denies it. Enter `/exit` to quit.

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

- `main.py`: terminal conversation and explicit agent loop
- `web.py` / `web.html`: local server, web interface, and web agent loop
- `bash_tool.py`: tool definition, command approval, and command execution
- `check_api.py`: API configuration, HTTPS requests, token reporting, and connection checks
- `system_prompt.md`: editable model instructions
- `pyproject.toml` / `uv.lock`: project dependencies and locked versions

## Status

Implemented: API calls, conversation history, one bash tool, command approval, tool loop limits, terminal and web interfaces, and token usage reporting. Real-model integration checks passed for conversation, execution, command failure, and denial. The author has confirmed that the web interface works. Windows has not been tested. The repository has not yet been published; next steps are public GitHub publication, a fresh-install check, and the course installation-skill pull request.

## License

MIT. See `LICENSE`.
