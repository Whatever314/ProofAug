# PLAN.md - ProofAugProver Wrapper Implementation

## Goal

Implement `provers/peer/ProofAug_prover.py` with a `ProofAugProver` class that
implements `ProverProtocol[ProofAugConfig]` and delegates proof search to the
original ProofAug `proof_aug_1dp` in `provers/peer/ProofAug/isabelle_src/main.py`.

Constraint:
- Do not import from `provers/ProofAug/`.
- Use only the original ProofAug code under `provers/peer/ProofAug/isabelle_src/`.
- Use PISA (`PisaStepEnv`) backend, not IsaRepl.

Design direction for this wrapper:
- Prover manages full PISA lifecycle (start server, create env, cleanup).
- Keep implementation minimal and type-safe.
- Do not construct or use `MessagesPrompter` in the wrapper.
- Key-map is configured as a stem name, not a path.

---

## Architecture Overview

```
BaseEvaluator                             Original ProofAug
     |
     |- prove(lemma, isa_port)
     |      |
     v      v
ProofAugProver -----------------------> proof_aug_1dp(dp, idx, env_queue, ...)
  (wrapper)                                 |
     |                                      |- uses env_queue.get() -> PisaStepEnv
     |                                      |- runs proof augmentation + LLM calls
     |                                      |- env_queue.put(env)
     |
     |- starts PISA server (java)
     |- creates PisaStepEnv
     |- wraps env in single-item queue
     |- converts result dict -> list[str]
```

The wrapper is responsible for:
1. Converting `LemmaProtocol` to ProofAug input `dp`.
2. Managing PISA server process and `PisaStepEnv` lifecycle.
3. Calling `proof_aug_1dp` with config-mapped kwargs.
4. Returning proof as `list[str]` expected by evaluator.

---

## Import Strategy (safe and minimal)

`isabelle_src/` uses bare imports like `from utils.pisa_client import PisaStepEnv`.
To make this work from repo root:

1. Compute `PROOFAUG_SRC_DIR = Path("provers/peer/ProofAug/isabelle_src")`.
2. Insert `str(PROOFAUG_SRC_DIR.resolve())` into `sys.path` before importing
   `main` / `utils.*` symbols.
3. Keep all ProofAug imports in one block after that insertion.

Required imported symbols:
- `proof_aug_1dp` from `main`
- `PisaStepEnv` from `utils.pisa_client`
- `kill_pid_tree` from `utils.misc`

Notes:
- Wrapper should avoid importing `MessagesPrompter`.
- Keep imports local to module setup and avoid mixing with project `utils.repl`.

---

## Data Mapping

### LemmaProtocol -> ProofAug `dp`

`proof_aug_1dp` expects dictionary fields used in prompt templates:

| dp field | Source | Notes |
|---|---|---|
| `xf` | `lemma.statement` | formal statement |
| `yf_p` | `""` | initial proof prefix |
| `yf_c` | `""` | complement placeholder |
| `xi` | optional attribute on lemma else `""` | informal statement |
| `yi` | optional attribute on lemma else `""` | informal proof |
| `init_proofs` | lemma init proof list if enabled | only when `use_init_proof=True` |

`ps` is produced internally by `proof_aug_1dp` from PISA state; wrapper does not set it.

### ProofAug result -> prover output

| result field | handling |
|---|---|
| `success` | must be `True` |
| `yf` | if non-empty, return `[yf]` |

Return:
- success: `[yf]`
- failure or `None`: `[]`

---

## Config Model

Keep config straightforward and typed. Core fields map directly to
`proof_aug_1dp` parameters.

### Prompt/request args

`ProofAugPromptArgs` should include existing request transport fields plus common
sampling fields passed via `**request_kwargs`:
- `model: str | None = None`
- `temperature: float = 0.6`
- `max_tokens: int = 2048`
- `top_p: float = 0.95`
- `n: int = 1`

### ProofAugConfig changes

1. Key-map setting:
- Replace `key_map_file: Path | None` with `key_map_stem: str | None`.
- This maps directly to `proof_aug_1dp(..., key_map_name=key_map_stem, ...)`.

2. PISA lifecycle settings (managed by prover):
- `pisa_port_offset: int = 10000`
- `pisa_copy_root: Path = Path(".cache/pisa")`
- `pisa_wait_server_time: int = 20`
- `pisa_use_heuristic: bool = True`
- `pisa_use_hammer: bool = True`
- `pisa_jar_path: Path`
- `pisa_isa_path: Path`
- `pisa_theory_name: str`

Runtime port rule:
- `pisa_port = isa_port + pisa_port_offset`

This avoids direct collision with evaluator checker port and keeps API unchanged.

---

## Prover Lifecycle

Wrapper owns the full PISA lifecycle per `prove()` call:

1. Compute `pisa_port` from `isa_port` and offset.
2. Start PISA Java server process via `subprocess.Popen`.
3. Wait configured startup duration.
4. Create `PisaStepEnv` bound to that port.
5. Put env into a one-element `queue.Queue`.
6. Call `proof_aug_1dp`.
7. Ensure env cleanup (`del_all_extra_tlss` best-effort).
8. Stop Java process tree (`kill_pid_tree(pid)` best-effort).

Minimal-effort reliability:
- No long-lived cache in first implementation.
- One fresh PISA process per `prove()`.
- All cleanup in `finally`.

---

## Config-to-`proof_aug_1dp` Mapping

| ProofAugConfig | `proof_aug_1dp` arg |
|---|---|
| `template_file` | `template_fp` |
| `prompt_dedup` | `prompt_dedup` |
| `n_shots` | `n_shots` |
| `example_file` | `example_fp` |
| `random_examples` | `random_sample` |
| `key_map_stem` | `key_map_name` |
| `num_try` | `num_try` |
| `err_tol` | `err_tol` |
| `proof_aug` | `proof_aug` |
| `allow_sorry` | `use_sorry` |
| `comment_start` | `comment_start` |
| `use_init_proof` | `from_offline` |
| `fo_start` | `fo_start` |
| `fo_end` | `fo_end` |
| `use_erp` | `use_erp` |
| `sc_add_ps` | `sc_add_ps` |
| `request_args.*` | `**request_kwargs` |

Path handling:
- `template_file` and `example_file` resolved relative to `PROOFAUG_SRC_DIR`
  when not absolute.

---

## Implementation Steps

### Step 1: Module setup and imports

- Add `PROOFAUG_SRC_DIR` constant.
- Insert ProofAug `isabelle_src` into `sys.path` before ProofAug imports.
- Import `proof_aug_1dp`, `PisaStepEnv`, `kill_pid_tree`.

### Step 2: Update config models

- Extend `ProofAugPromptArgs` with sampling fields (`model`, `temperature`, etc.).
- Replace key-map path field with `key_map_stem: str | None`.
- Add PISA lifecycle fields listed above.

### Step 3: Implement `ProofAugProver.__init__`

- Store config and logger.
- Keep simple counter for `idx` values.

### Step 4: Implement `load_config`

- Replace config, preserve simple behavior.

### Step 5: Implement helper methods

- `_resolve_path(path: Path) -> Path`
- `_build_dp(lemma: LemmaProtocol) -> dict[str, object]`
- `_next_idx() -> int`
- `_spawn_pisa_server(pisa_port: int) -> int` returning pid
- `_build_env(pisa_port: int) -> PisaStepEnv`

### Step 6: Implement `prove`

Core flow:
1. Build `dp` from lemma.
2. Derive `pisa_port` from `isa_port` + offset.
3. Spawn PISA server process and wait.
4. Create `PisaStepEnv`, wrap in queue.
5. Call `proof_aug_1dp` with mapped config and request kwargs.
6. Parse return dict and extract `yf`.
7. Cleanup env + server process in `finally`.

Return `[yf]` if successful, otherwise `[]`.

---

## Error Handling Policy

- If `proof_aug_1dp` returns `None` or malformed output, return `[]`.
- If env creation or server startup fails, log error and return `[]`.
- Never leak PISA process on error path: always attempt kill in `finally`.
- Keep `err_tol` behavior delegated to `proof_aug_1dp`.

---

## Type-Safety and Minimal Effort Principles

- Use concrete return types (`list[str]`, `dict[str, object]`) on wrapper methods.
- Keep all config fields typed in Pydantic models.
- Avoid additional abstractions beyond helper methods above.
- Do not refactor original ProofAug logic; wrapper only adapts and orchestrates.

---

## Out of Scope for This Iteration

- Reusing long-lived PISA env/process across lemmas.
- Parallel checker pool management inside prover.
- Refactoring `isabelle_src` imports or module layout.

These can be follow-up optimizations after correctness is established.
