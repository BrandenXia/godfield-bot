# Post-team cleanup:2026-11-03

Performed only after team feature commit `22d89ac` and its12618 passing
nonbrowser tests. The user explicitly requested cleanup after the feature.

## Confirmed duplicate sources removed

Removed these two ignored experiment copies after verifying exact SHA256
equality with their committed archival counterparts:

- `runs/experiments/official-client-2026-09-28.js` →
  `data/snapshots/2026-09-28/official-client.js`, SHA256
  `764a50524e4b6b3f510415da7128abd8ad99dcb87b45b8572d98ddd96889cabd`.
- `runs/experiments/official-client-2026-11-03.js` →
  `data/snapshots/2026-11-03/official-client.js`, SHA256
  `5ece06c224b6a7a5d877eb45d22ea18b82a03aaf1b7161cbbdf6a1e23ceab2cd`.

Updated three historical architecture references to the tracked September
fixture. Bytes and referenced line numbers are unchanged. Both removed copies
can be recovered from the listed archives in Git commits `a443325`/`d96dcaa`.

## Regenerable caches moved out of the project

Moved `.pytest_cache`, `.ruff_cache` and `.mypy_cache` (55 MB combined) into
`/private/tmp/godfield-cleanup-20261103.F4vX0u`. They are recoverable there until
temporary-directory cleanup, or regenerable through their respective tools.
This cleans the project; it does not claim55 MB of immediately reclaimed disk
space. The private temporary folder is not source/runtime data or a checkpoint.

## Deliberately retained

- Training/gameplay runs, models, checkpoints and captured evidence.
- All pinned source snapshots, catalogs, provenance and architecture records.
- Credentials, browser profiles, persistent identity and account state.
- `.playwright` (needed for the official-bot browser harness) and `.uv-cache`
  (needed for reproducible offline native builds). No broad cache purge.
- Existing curriculum code and old checkpoint interfaces; these are required
  compatibility paths, not safely disposable duplicates.

No training run, account or live game was changed. Post-cleanup verification
uses pytest with its cache provider disabled so these caches stay absent.
