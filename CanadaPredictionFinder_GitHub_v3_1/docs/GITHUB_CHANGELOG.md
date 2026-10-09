# GitHub Edition 3.1 changes

Added a scheduled, bounded seven-day paper-testing workflow and explicit initialization; encrypted SQLite checkpoints in a dedicated rotating state branch; lease-protected state writes; default-branch-only controls; duplicate-run receipts; cross-run catalog/fee/provider-backoff preservation; private-repository cost gate; optional allowlisted static Pages report; expiry and workflow-disable attempt; daily encrypted artifact backup attempt; profile-aware confirmation timing; rolling observation compaction; and offline Git/encryption/end-to-end tests.

The existing 60-second engine confirmation window was hard-coded to a 50–180 second interval. This is unchanged for the minute profile but now scales with scan_seconds for the five-minute economy profile. Quote freshness thresholds are not relaxed.

Core v3 strategy assumptions are unchanged. There is still no proven profitable edge and no Canadian broker quote/execution adapter. The independent-value engine is retained, but the hosted read-only dashboard does not accept new forecasts; only the experimental reversion strategy has an autonomous data-input path in this GitHub edition.

All cash flows, trades and equity records remain in the checkpoint. Raw snapshots beyond the rolling retention count are intentionally pruned, so full-history book replay is not available afterward. Local-only launchers remain optional; see the GitHub guide for the primary deployment.
