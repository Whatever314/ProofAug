# AGENTS.md — ProofAug

## Project Overview

ProofAug is an LLM-based automated theorem proving system. The `isabelle_src/` subdirectory
contains the Isabelle prover implementation (Python), which communicates with Isabelle via
a gRPC/PISA backend (Scala JAR). The `lean_src/` directory contains the Lean implementation.

This file covers `isabelle_src/` exclusively.

## Build & Run

### Prerequisites
- Python >= 3.11 (codebase uses 3.10+ syntax: `X | None`, walrus `:=`, `typing.Self`)
- PISA server (Scala JAR) providing gRPC access to Isabelle
- An LLM service (OpenAI-compatible API, e.g. vllm)

### Running the Main Experiment
```bash
python -m main online_chat \
  --dp_processor "proof_aug_1dp" \
  --dst_fp "output/result.jsonl" \
  --src_fp "datasets/minif2f-test.jsonl" \
  --template_fp "templates/few-shot.json" \
  --example_fp "examples/few-shot.jsonl" \
  --n_shots 1 --num_try 100 --temperature 0.6 \
  --chat False --comple_sep "concat" \
  --model "$model" --base_url "$base_url" \
  --id_key "problem_name" \
  --proof_aug True --use_erp True \
  --port_base 8100 --copy_root /path/to/isa/copies \
  --num_checkers 12
```
Run from `isabelle_src/` directory. Uses `fire.Fire()` for CLI dispatch.

## Architecture

```
isabelle_src/
  main.py              — Entry point: proof_aug_1dp(), online_chat(), extract_train_dps()
  utils/
    assistant.py       — OpenAI API wrapper (Assistant class, post_request, offline_chat)
    pisa_client.py     — gRPC client for PISA/Isabelle (PisaEnv, PisaStepEnv)
    pisa.py            — Isabelle instance management (init_checker)
    prompter.py        — Few-shot prompt construction (MessagesPrompter)
    misc.py            — I/O utilities (read_json, jsonl2dps, write_as_jsonl, kill_pid_tree)
    exceptions.py      — Custom exceptions
    time_utils.py      — Timeout decorators, timing utilities
    server_pb2.py      — Auto-generated protobuf (DO NOT EDIT)
    server_pb2_grpc.py — Auto-generated gRPC stubs (DO NOT EDIT)
  datasets/            — JSONL benchmark files (miniF2F)
  templates/           — JSON prompt templates
  examples/            — JSONL few-shot example files
```

Key patterns:
- `ThreadPoolExecutor` + `queue.Queue` for parallel proof checking
- `fire.Fire()` as CLI entry point in main.py, assistant.py, pisa.py
- `@dataclass` for parameter structs (`RequestParameters`)
- Custom timeout decorators: `@with_timeout()`, `@func_set_timeout()`

## Code Style Guidelines

### Naming Conventions
- **Functions/methods**: `snake_case` (exception: `callATP` is camelCase)
- **Classes**: `PascalCase` — acronyms stay uppercase (`PISAError`, `PisaStepEnv`)
- **Constants**: `UPPER_CASE` at module level (`MAX_MESSAGE_LENGTH`, `THEOREM_SEPARATOR`)
- **Variables**: `snake_case` with heavy abbreviations:
  - `dp` = data point, `fp` = file path, `tls` = top-level state
  - `xf` = formal statement, `yf` = formal proof, `xi`/`yi` = informal
  - `yf_p` = proof prefix, `yf_c` = proof complement, `ps` = proof state
  - `sc` = step complement, `yf_woi` = proof without informal
  - Loop indices: `i_try`, `i_step`, `i_prob`
- **`2` as "to"**: `output2dict`, `msg2prompt`, `sep2stop`, `yf2yf_woi`

### String Formatting
- **f-strings** dominant (90%+), including `f'{var=}'` debug format
- `.format()` only in template rendering (`prompter.py`)
- No `%` formatting

### Indentation & Line Length
- 4 spaces, no tabs
- No line length limit enforced; lines routinely exceed 100 chars (max ~273)
- Line continuation with `\` used occasionally

### Error Handling
- Custom exceptions in `utils/exceptions.py`: `ContextTooLongError`, `PISAError`,
  `PISAParseError`, `UnkRequestException`
- Error tolerance pattern: counter incremented on each error, re-raised when exceeding threshold
- Bare `except:` clauses exist (pisa_client.py, main.py) — avoid adding more
- Error strings parsed from PISA observation text (not structured error types)
- Retry loops for API calls with regex-based error parsing

### Logging
- Per-module loggers with individual `FileHandler`s (NOT centralized)
- Log files: `sv.log` (main + pisa_client), `assistant.log`, `main.log`, `time.log`
- Format: `%(asctime)s:%(levelname)s:%(name)s:%(message)s`
- `print()` used alongside `logger` calls for dual console/file output
- `time_logger` (named logger) for timing info

### Other Patterns
- Date-stamped comments for tracking changes (`# 1127 add ...`, `# 0801`)
- Significant commented-out code throughout
- `deepcopy` used heavily (mutable dict data structures)
- `partial()` for currying worker functions
- Walrus operator `:=` used in conditionals
- Research code: prioritizes rapid iteration over clean architecture
- God functions: `proof_aug_1dp` (~305 lines), `extract_train_dps` (~200 lines)

## Files NOT to Edit
- `utils/server_pb2.py` — auto-generated protobuf
- `utils/server_pb2_grpc.py` — auto-generated gRPC stubs
- `datasets/*.jsonl` — benchmark data
- `cum.tar.gz` — archived results (do not distribute)
