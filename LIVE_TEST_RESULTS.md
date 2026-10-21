# Live integration test results

## Plugin-loader integration (October 21, 2026, America/Los_Angeles)

- Six offline loader/permission tests passed, including persistent stdio state,
  clean shutdown, skill metadata disclosure, missing variable handling,
  mandatory bash approval and denied execution prevention.
- Two offline local HTTP tests passed for shared web-agent dispatch and MCP
  approval denial.
- The real configured model selected telegram__send_message and
  seismic__get_event_details through the shared Agent loop. The latter returned
  ci40925991, M5.21, 14.29 km depth, and strike-slip classification.
- A separate normal terminal `main.py --ask` invocation sent exactly
  "Hello from the qimeng-agent terminal." with a successful tool result.
  Its first model request reported 1618 input and 23 output tokens.
- The full plugin integration test's first request reported 1636 input and 51
  output tokens. Its local results are in work/harness-plugin-live-results.json.
  No configured API key or bot token appeared in its recorded model history.
- The baseline live regression suite was rerun after the loop refactor: memory,
  approved command, command failure and denial scenarios all passed.
- Final syntax compilation and git diff whitespace checks passed.

The student confirmed receipt of the normal terminal greeting and explained
tool schemas, progressive skill disclosure and credential separation. That
course checkpoint passed.

## Telegram mode (October 21, 2026, America/Los_Angeles)

Telegram input and approval-by-reply mode is implemented. Eight new offline
tests passed for harness-owned polling, fabricated polling-call rejection,
stale approval rejection, explicit yes, denial/default denial, timeout,
deduplication and conversation/final-answer routing. Together with loader and
web tests, all 16 harness tests passed. The four Telegram plugin tests also
passed after adding sent-message IDs for approval correlation. Syntax and
whitespace checks passed.

A bounded live phone session started successfully and sent its online message.
Live phone approval, denial, multi-step task and research-query checks are
pending; an online message alone does not establish those checks.

The initial session exited after about 95 seconds due to a receive-format
error, not its idle timeout. The SDK represents list elements as separate
text blocks; joining them lost the list shape. The loader now reads
structured_content and unwraps its result envelope. A real stdio list-response
regression and phone decoder regression were added; all 17 harness tests
passed. Receive failures are retried twice and an error shutdown reports a
distinct reason. Approvals remain fail-closed. Live checks are being repeated.

After the fix, live phone turns completed successfully. The audit recorded
fresh bash approval prompts, explicit approvals, returned tool results and
final answers sent back to Telegram. The student confirmed the phone workflow
works. A denial was also logged, but the deliberate no-denial acceptance case,
multi-step task and research question are still to be confirmed explicitly.

The student subsequently confirmed the deliberate no-denial check passed.
The first full phone research query returned 205 events, but the model had
batched the search and dependent statistics before observing a real catalog
ID. The statistics failed, so that phone research test did not pass.

The shared loop now requests parallel_tool_calls=false and executes at most
one call per model reply, deferring additional calls until the result can be
observed. The system prompt requires exact returned identifiers. Unknown
catalog IDs now return actionable ToolError content. All 18 harness tests and
10 research-plugin tests passed. A real-model full research-chain test then
returned 205 events, depths 1.87/9.67/22.82 km (min/median/max), 181 usable
mechanisms with counts 146/1/6/28, and pooled b=0.966 +/- 0.060.

At the student's request, old generated catalog/statistic files were removed.
Research MCP sessions now use unique temporary output directories, delete
their data on exit, and clear in-memory catalogs. Stale directories are removed
on the next startup only when the recorded owner process no longer exists.
Active or unrecognized folders are preserved. The real-model chain test also
verified its catalog existed during the session and was deleted on close.
Code, English validation documentation and compact audit logs are retained.
The phone research query must still be repeated after the ordering fix.

The repeated phone research query passed after the fix. Audit records show
search_earthquakes, summarize_catalog, summarize_mechanisms and
calculate_b_value each returned successfully in separate model rounds,
followed by answer_sent. The student confirmed satisfaction with the phone
result. This also exercises a multi-step research task with dependent tools.
The scientific-review checkpoint is accepted for this exploratory case;
the documented Mc, magnitude-scale and mechanism-quality caveats still apply.

## Original week 2 checks

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
