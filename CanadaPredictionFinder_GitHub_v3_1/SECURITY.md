# Security — GitHub Edition 3.1

Paper trading only. No account login, wallet key, authenticated trading endpoint or live-order adapter exists. Public market calls remain GET-only and allowlisted, with redirects/access-denial bypass refused.

The GitHub workflow requires one random `STATE_PASSPHRASE` repository secret to encrypt paper state using GnuPG/AES256. It is sent to GnuPG through standard input, not command-line arguments. Decryption must succeed, archive members must match an allowlist, identity/hashes must match, and cash accounting must reconcile before use. Never print or commit the passphrase, decrypted state, application logs or forecasts.

The automatic GitHub token can write repository contents and disable the trial workflow. The runner writes only the reserved state branch. A force-with-lease comparison rejects a conflicting writer; code/index/main are not rewritten. Pull-request tests run without secrets and with a read-only token. There is no pull_request_target scanner trigger. A fork is not automatically granted scheduling access.

Restrict write access to trusted collaborators. A malicious trusted workflow change can exfiltrate a secret; encryption does not protect against someone who controls the code consuming it. GitHub, the runner environment, GnuPG and official GitHub Actions are part of the trust boundary. Official action release references are used and Dependabot is configured; version tags are not cryptographic immutability guarantees. Review changes before approval, and pin vetted full commit SHAs under stricter supply-chain policies.

Optional Pages publication is allowlisted aggregate data only and off until PUBLISH_PAPER_SUMMARY=true. Assume that publication is public. Turning that variable off stops future publication but does not remove an already-public site. GitHub administrators and infrastructure can still access runtime plaintext while a job executes. This is not confidential-computing software.

Back up your passphrase separately. Keep encrypted offline checkpoints. Rotating Git commits and expiring artifacts are not guaranteed immediate secure deletion of historical server objects. Do not place genuine broker secrets or personal medical/financial account data in this project.
