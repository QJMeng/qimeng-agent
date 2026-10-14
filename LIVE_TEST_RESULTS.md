# Live integration test results

Date: 2026-10-14 (America/Los_Angeles)
Model: gpt-4.1-mini
Command: python3 test_live.py
Final result: exit code 0; all four scenarios passed.

- Continuous conversation: recalled seismic-check-729 from the previous turn.
- Approved execution: printf harness-live-ok returned harness-live-ok with exit code 0; the model reported the output.
- Failed execution: doesnotexist returned command not found with exit code 127; the model explained the failure.
- Denied execution: the tool returned the user-declined message; the execution function was never called, and the model acknowledged the denial without another command.

The first run passed the first three scenarios but failed denial because the model asked for approval in text instead of proposing a tool call. The system prompt was clarified to let the application handle approval. The second full run passed.

The final run made eight API calls: 2,205 input tokens, 256 output tokens (2,461 total); cached input was zero. Input increased from 248 to 285 tokens between the first and second chat turns.

The real model and actual shell were used. Approval responses were supplied by the test driver; execution was restricted to two exact commands. Human terminal interaction and longer multi-tool research workflows remain separate checks.
