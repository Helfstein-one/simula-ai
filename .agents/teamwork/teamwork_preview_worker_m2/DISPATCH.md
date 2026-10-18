## 2026-10-12T23:33:50Z
You are the Worker for Milestone 2 (CoALA Cognitive Loop & Sandbox) of Simula-AI.
Your working directory is: /Users/mauriciohelfstein/dev/simula-ai/.agents/teamwork/teamwork_preview_worker_m2/
Project root: /Users/mauriciohelfstein/dev/simula-ai

MANDATORY: Read /Users/mauriciohelfstein/dev/simula-ai/.agents/teamwork/ORIGINAL_REQUEST.md before starting work. Do NOT skip reading it.
Read /Users/mauriciohelfstein/dev/simula-ai/.agents/teamwork/orchestrator_1/PROJECT.md.

Read Explorer handoffs and verified drop-in blueprints:
- /Users/mauriciohelfstein/dev/simula-ai/.agents/teamwork/teamwork_preview_explorer_m2_1/handoff.md, analysis.md, and drop-in blueprints:
  * proposed_state.py (for core/state.py)
  * proposed_memory.py (for core/memory.py)
  * proposed_llm_client.py (for core/llm_client.py)
- /Users/mauriciohelfstein/dev/simula-ai/.agents/teamwork/teamwork_preview_explorer_m2_2/handoff.md and analysis.md (specifications and blueprints for core/code_parser.py and core/sandbox.py)
- /Users/mauriciohelfstein/dev/simula-ai/.agents/teamwork/teamwork_preview_explorer_m2_3/handoff.md, analysis.md, and drop-in blueprints:
  * proposed_core_graph.py (for core/graph.py)
  * proposed_test_coala_loop.py (for tests/unit/test_coala_loop.py)

Write Ownership:
You own exclusively and must implement/create:
- core/state.py
- core/memory.py
- core/llm_client.py
- core/code_parser.py
- core/sandbox.py
- core/graph.py
- core/__init__.py (export models, clients, sandbox, loop runner)
- tests/unit/test_coala_loop.py

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_preview_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

Execution & Verification:
1. Implement all owned files with genuine logic and integrate cleanly with existing core/contract_parser.py.
2. Run pytest on tests/unit/test_coala_loop.py (e.g. uv run pytest tests/unit/test_coala_loop.py -v).
3. Run all unit tests: uv run pytest tests/unit/ -v.
4. Run relevant E2E tests:
   uv run pytest tests/e2e/test_tier1_features.py -k "r1" -v
   uv run pytest tests/e2e/test_tier2_boundaries.py -k "think_tag or sandbox or max_iterations" -v
   uv run pytest tests/e2e/test_tier3_pairwise.py -k "self_correction" -v
5. Run ruff linter: ruff check core/ tests/unit/.
6. Document commands and verbatim outputs in /Users/mauriciohelfstein/dev/simula-ai/.agents/teamwork/teamwork_preview_worker_m2/handoff.md and report back via message.
