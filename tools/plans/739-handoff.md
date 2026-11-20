# Handoff: #739 Replace save blob formats with a manifest payload

## Metadata
- Issue: #739
- Branch: feature/739-evaluate-manifest-format
- PR: #752
- Status: shipped
- Created: 2026-11-20
- Fix attempts: 0

## 1. Issue
### Summary
Evaluate replacing raw/tar/tar.gz enveloped blobs with a manifest payload (Phase D) and merging game/console history, baseline and conflict tables into owner-keyed tables (Phase E). Split from #737.
### Motivation
Remaining after #737/#749: CardFormatMismatch (#718), envelope-skipping hashes, no per-file info, two table families.
### Proposed Behavior / Steps to Reproduce
Evaluation only; deliverable is a written evaluation and a proceed/close decision.
### Affected Area
src/server/sync_client.py, src/server/store/{blobs,conflicts,schema,devices}.py, src/server/api/{blobs,conflicts}.py, src/cli/run_reconcile.py
### Acceptance Criteria
- [x] Written evaluation posted on the issue (issuecomment-7047489929)
- [x] Decision recorded: proceed with Phase D only, Phase E dropped
- [ ] Saves, states and memory cards push/pull/restore through one manifest format
- [ ] Envelope header-skipping hash helpers removed (CardFormatMismatch stays: layout difference, not encoding)
- [ ] One-time server conversion with backup (DB snapshot, originals kept until verified)
- [ ] Docs updated

## 2. Design
### Scope: backend only (Phase D). Phase E dropped by user decision 2026-11-20.
### Backend Changes: new manifest envelope format in sync_client.py; one manifest-driven extract/merge/restore replacing raw/tar/tar.gz paths; manifest-derived content hash (replaces _payload_sha256/_memcard_payload_bytes header skipping); remove CardFormatMismatch and its run_reconcile handling; schema migration converting all stored blobs with DB snapshot + originals kept until verified; old-client upload wrapping in api/blobs.py.
### UI Changes: none (GUI push/pull shell out to CLI, #479)
### Plan Target: bplan
### Sub-issues: none
### Difficulty: 9/10 (includes +2 breaking)
### Backwards Compatibility: breaking. Server updates first; clients require the manifest format. Accepted: one user, three self-managed devices.

## 4. Backend Plan
### Design Alignment: shared codec module (src/server/blob_tree.py) used by client, store, API and migration; server-first strict rollout as in #749; schema-gated one-time file conversion as in v36/v37; hashes stay envelope-free, now manifest-derived.
### Backend Pattern: envelope format 3 = uncompressed tar with leading .emusync-manifest.json; file hash = file sha256 (unchanged, GUI getFileHash stays valid), dir hash = sha256 of sorted [path,size,sha256] JSON.
### Recommendations: CardFormatMismatch cannot be removed; issue criterion corrected.

## 6. Testing Plan
### Test File: src/tests/test_blob_tree.py, src/tests/test_tree_migration.py, conftest.py helper, existing suites updated
### Test Cases: 10 (file/dir round trip, filename-independent file hash, deterministic pack, filters, API push/pull, old-format 400, CardFormatMismatch, migration, migration idempotence)
### Edge Cases: tampered blob, hostile tar members, empty folder, integrity damaged, migration skips, restore of pre-conversion generation
### Integration Points: SyncClient vs live_server folder card A->B; rom-folder transfer both paths; GUI getFileHash relies on unchanged single-file hash
### Outline:
Backend
- 1. New codec module src/server/blob_tree.py (pack, hash, verify, extract, legacy convert); tar helpers move in from sync_client
- 2. Client pulls/writes for saves, cards, states, mods go through extract_tree; CardFormatMismatch kept
- 3. Client pushes and local hashes use pack_tree/content_hash; _memcard_payload_bytes deleted
- 4. rom-folder transfer receive path: enveloped via _write_memcard, bare GUI tar via the shared swap
- 5. Server: plain staging, verify_blob hash on push, old formats rejected with 400, integrity uses verify_blob
- 6. Schema v38: DB backup, convert every stored blob with originals kept in blobs/.pre-v38, remap dir hashes in rows, baselines, conflicts
- 8. Docs: CLAUDE.md, GOTCHAS, ARCHITECTURE, design guide
Tests
- 7a. conftest tree()/raw_env helper; mechanical wrap of raw-byte posts and store pushes in existing suites
- 7b. test_blob_tree.py: codec, API and edge cases
- 7c. test_tree_migration.py: v38 conversion, remap, backup, idempotence
- 7d. extend test_memcard_folder_sync and test_rom_transfer for cross-device and transfer paths
### Summary: Replaces the raw/tar/tar.gz save blob formats with a single manifest tar format, converts all stored blobs once (with a DB backup and originals kept), and requires the new format from clients.

## 8. Implementation Steps
### Steps: see tools/plans/739-manifest-save-format.md
- 1. [done] codec module: src/server/blob_tree.py (new), sync_client.py. Reuses _safe_extract_tar, _extract_tar_to_tmp, _pack_envelope, sorted rglob walk. New module because four callers need it and sync_client.py is already 852 lines.
- 2. [done] client writes: sync_client.py. Reuses _write_memcard_raw_bytes, swap block of _write_memcard_tar_bytes, _backup_state_files, merge loop. No new code paths.
- 3. [done] client pushes/hashes: sync_client.py, cli/run_reconcile.py, cli/run.py. Reuses pack_tree/content_hash; deletes _memcard_payload_bytes.
- 4. [done] rom-folder transfer: cli/transfer.py, sync_client.py. Reuses _extract_tar_to_tmp + swap; drops _FMT_TAR wrap.
- 5. [done] server upload/store/integrity: api/blobs.py, api/mods.py, store/blobs.py. Reuses verify_blob and existing staging cleanup; removes header-skip hashing.
- 6. [done] schema v38 conversion (in store/tree_migration.py): store/schema.py. Reuses v36/v37 loop shape, .part + os.replace, conn.backup.
- 7. [done] tests: new test_blob_tree.py, test_tree_migration.py; updates 10 existing files. New files because nothing covers the codec or v38.
- 8. [done] docs: CLAUDE.md, GOTCHAS.md, ARCHITECTURE.md, backend-design-guide.md.

## 9. Review
### Findings: 2 nits. (1) blob_tree.py: filenames with a backslash or named .emusync-manifest.json pack but fail server verification (400 on every push). (2) store/blobs.py restore of a generation that failed v38 conversion raises ValueError -> 500.
### Blocked: no
### Blockers: none

## 10. Ship
### Status: shipped
### PR: #752
### Server Sync: pending
### Doc Sync: pending

## 12. Log
- 2026-11-20 issue: workflow initialized (resume from #739)
- 2026-11-20 design: scope=none (evaluation), plan_target=none, difficulty=1/10, breaking=no; evaluation posted, recommendation close
- 2026-11-20 design: user decision proceed with D only; scope=backend, plan_target=bplan, difficulty=9/10, breaking=yes
- 2026-11-20 bplan: 8 steps written, backend_pattern=shared manifest codec + schema-gated conversion + strict server-first rollout
- 2026-11-20 tplan: test_file=src/tests/test_blob_tree.py + test_tree_migration.py, 10 test cases defined
- 2026-11-20 implement: step 1 done (blob_tree.py codec; tar helpers moved, re-exported from sync_client)
- 2026-11-20 implement: steps 2-3 done (client pulls/pushes/hashes on manifest format; size = content bytes)
- 2026-11-20 implement: step 4 done (rom-folder receive: manifest via _write_memcard, bare GUI tar via _write_memcard_tar_bytes)
- 2026-11-20 implement: step 5 done (server verifies uploads via verify_blob, 400 on old formats; store/integrity use manifest hash and content size)
- 2026-11-20 implement: step 6 done (v38 conversion with DB backup, originals in blobs/.pre-v38, hash remap)
- 2026-11-20 implement: step 7 done (conftest tree/tree_dir helpers, 25 suites updated, test_blob_tree.py + test_tree_migration.py; 800 passed)
- 2026-11-20 implement: step 8 done (CLAUDE.md, GOTCHAS, ARCHITECTURE updated); all steps done
- 2026-11-20 review: 2 findings (nits), blocked=no
- 2026-11-20 ship: tests passed (800), PR #752 opened
