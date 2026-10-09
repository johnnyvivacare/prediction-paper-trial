# GitHub deployment references

Official documentation checked while preparing the GitHub edition, October 8, 2026. Platform behaviour, prices and permissions may change. These sources describe infrastructure, not the profitability of this bot.

- Scheduled events: five-minute minimum, possible delays/dropped jobs, default-branch restrictions.
  https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule
- Actions billing: standard public-runner compute versus private plan quotas and storage.
  https://docs.github.com/en/billing/managing-billing-for-github-actions/about-billing-for-github-actions
- Actions-specific terms: development/testing constraints and excessive/unrelated resource-use restrictions.
  https://docs.github.com/en/site-policy/github-terms/github-terms-for-additional-products-and-features#actions
- GitHub Secrets and encrypted-file pattern; avoid printing decrypted secrets.
  https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-secrets
- Publishing a Pages report through Actions.
  https://docs.github.com/en/get-started/start-your-journey/deploying-your-website-automatically
- Disable a workflow after the bounded trial.
  https://cli.github.com/manual/gh_workflow_disable
- Official actions used:
  https://github.com/actions/checkout
  https://github.com/actions/setup-python
  https://github.com/actions/upload-artifact
  https://github.com/actions/upload-pages-artifact
  https://github.com/actions/deploy-pages

The code was adapted from the supplied v3 ZIP. No external trading bot code or claimed-profitable strategy was added in this deployment update. The prior provenance documentation remains in PROVENANCE.md.
