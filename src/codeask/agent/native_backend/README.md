# Native Agent Backend

This package contains the legacy CodeAsk native agent backend.

Status for v1.0.5:

- Frozen reference code only.
- Not part of the active request path after the native backend is disconnected.
- Kept importable so historical behavior can be inspected and tested.

To revive this backend:

1. Reconnect it explicitly in `src/codeask/app.py`.
2. Restore an `agent_backend` branch in the session request path.
3. Keep `codeask.agent.sse`, `codeask.agent.trace`, and
   `codeask.agent.chat_runtime.events/context` as shared infrastructure unless
   there is a separate migration plan.
4. Use `src/codeask/rag/openviking/` for RAG access. Do not reintroduce FTS5,
   n-gram search, or an ILIKE-only retrieval path as the target architecture.

The minimal ILIKE logic used by native-only report tools is only a compatibility
fallback to keep this frozen package importable during the v1.0.5 migration.
