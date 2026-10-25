# Testing Guide

## Python Testing Patterns

### Framework
- pytest for all tests
- Real file I/O (no mocks for state management)
- HTTP mock for llama-swap (responses library or pytest-httpx)
- Subprocess mock for bash/gh actions

### Test Structure
```
workflow-cli/tests/
├── conftest.py          # shared fixtures (tmp dirs, mock LLM, test repo)
├── test_config.py       # config parsing, repo discovery
├── test_state.py        # handoff file + state.json
├── test_stages.py       # stage transitions
├── test_skills.py       # skill loading + prompt assembly
├── test_llm.py          # LLM client + retry logic
├── test_actions.py      # action executor
├── test_progress.py     # progress output
├── test_gates.py        # gate logic
├── test_project.py      # hook execution
├── test_cli.py          # arg parsing + main loop
└── test_schema.py       # JSON schema validation
```

### Fixtures (conftest.py)
- `tmp_project`: temporary project directory with config.yaml
- `tmp_handoff_dir`: temporary handoff directory
- `mock_llm`: mock llama-swap endpoint returning valid JSON batches
- `test_repo`: temporary git repo for init/discovery tests

### Rules
- No mocks for state management — use real file I/O
- HTTP mock for llama-swap (it's an external service)
- Subprocess mock for bash/gh actions (isolated testing)
- Each test is independent (no shared mutable state)
- Test names use underscores: `test_valid_config_parsing`
