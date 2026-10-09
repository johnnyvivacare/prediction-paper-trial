# GitHub edition test report

## Passed locally

153 unittest tests on Linux, including the 109 inherited v3 tests and 44 GitHub-related tests. Full output: `test-evidence/github-unittest.txt`.

New coverage includes encrypted SQLite save/restore of actual simulated fills and changed cash; authentication/corruption/identity errors; no-overwrite and no-silent-initialization behaviour; archive path traversal rejection; same/older completed-run receipts; deadlines and no catch-up bursts; explicit private-cost acknowledgement; reserved-branch/DEX-repository protection; concurrent writer rejection with force-with-lease; source-code/index preservation; persisted source backoff across different monotonic clocks; compacted observation history; aggregate-report privacy; and complete initialization/run/restore against a local bare Git remote.

Workflow YAML was parsed with a YAML parser and manually checked for trusted default-branch execution, no pull_request_target entry point, serialized writer concurrency, proper state-only writes, optional Pages publication, and bounded-trial workflow-disable behaviour. This is not a GitHub-hosted workflow execution test.

The report was rendered using installed Chromium at 1440×1150 and 390×844. No horizontal overflow or JavaScript exceptions occurred; zero-trade initial equity was US$500 and P&L US$0. The browser environment blocks HTTP navigation by administrator policy, so this used local HTML injection and direct evaluation of the generated report script. It verifies layout and script behaviour, not Pages routing, CSP response headers or remote deployment. See `test-evidence/github-browser.json`.

## Not verified

No repository was created or changed on the user's GitHub account. No scheduled run, cloud-side persistence, permissions, Actions charges, Pages publish or automatic workflow-disable call has been exercised there. Outbound DNS to live providers was unavailable in this build environment. GitHub's future scheduling and external data accessibility are not guaranteed.

No profitability validation, eligible Canadian brokerage quote mapping or funded-account trading integration was performed. All trading examples inside tests are fabricated, labelled fixtures, not performance evidence. Actual GitHub paper state is initialized from zero trades on the user's first explicit initialization.
