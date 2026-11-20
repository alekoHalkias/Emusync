# Handoff: #739 Replace save blob formats with a manifest payload

## Metadata
- Issue: #739
- Branch: feature/739-evaluate-manifest-format
- PR: none
- Status: planned
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

## 8. Implementation Steps
### Steps: see tools/plans/739-manifest-save-format.md
- 1. codec module: src/server/blob_tree.py (new), sync_client.py. Reuses _safe_extract_tar, _extract_tar_to_tmp, _pack_envelope, sorted rglob walk. New module because four callers need it and sync_client.py is already 852 lines.
- 2. client writes: sync_client.py. Reuses _write_memcard_raw_bytes, swap block of _write_memcard_tar_bytes, _backup_state_files, merge loop. No new code paths.
- 3. client pushes/hashes: sync_client.py, cli/run_reconcile.py, cli/run.py. Reuses pack_tree/content_hash; deletes _memcard_payload_bytes.
- 4. rom-folder transfer: cli/transfer.py, sync_client.py. Reuses _extract_tar_to_tmp + swap; drops _FMT_TAR wrap.
- 5. server upload/store/integrity: api/blobs.py, api/mods.py, store/blobs.py. Reuses verify_blob and existing staging cleanup; removes header-skip hashing.
- 6. schema v38 conversion: store/schema.py. Reuses v36/v37 loop shape, .part + os.replace, conn.backup.
- 7. tests: new test_blob_tree.py, test_tree_migration.py; updates 10 existing files. New files because nothing covers the codec or v38.
- 8. docs: CLAUDE.md, GOTCHAS.md, ARCHITECTURE.md, backend-design-guide.md.

## 12. Log
- 2026-11-20 issue: workflow initialized (resume from #739)
- 2026-11-20 design: scope=none (evaluation), plan_target=none, difficulty=1/10, breaking=no; evaluation posted, recommendation close
- 2026-11-20 design: user decision proceed with D only; scope=backend, plan_target=bplan, difficulty=9/10, breaking=yes
- 2026-11-20 bplan: 8 steps written, backend_pattern=shared manifest codec + schema-gated conversion + strict server-first rollout
