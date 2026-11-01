# Plan #703: Remove dead and broken chunked-upload code

- Status: implementing

## Steps
- [x] 1. api/blobs.py: delete everything from the "chunked transfers (issue #576)" header through the end of the console chunk routes, and unused `ChunkUploadRequest`; fix any now-unused imports
- [x] 2. sync_client.py: delete CHUNK_SIZE block (lines ~17-22), `_chunked_push`, `_normal_push`; fix "chunked" docstrings on pull_save/push_save
- [x] 3. store/blobs.py: delete `_extract_memcard_archive`
- [x] 4. store/_base.py: delete `_chunk_dir` creation and `_chunk_status_path`
- [x] 5. store/models.py: delete `ChunkStatus`
- [x] 6. grep for leftovers in src, tests, docs; run `make test-changed`
