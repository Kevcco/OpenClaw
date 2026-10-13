# Design

## Context

See proposal.md for motivation and specs for externally observable requirements. The current project stores a single instruction in `assistant_skills`, has `teacher` and `student` user roles only, and runs retrieval and assistant orchestration in Flask over SQLite plus Qdrant. `/api/ask` and conversation SSE both use the same configuration path; conversation messages currently snapshot only a single skill version. Existing class settings and databases must remain usable.

## Goals / Non-Goals

**Goals:**

- Introduce a validated deployment-owned skill package format and registry without making client-editable skill content.
- Make skill matching, token budgeting, and per-class enablement deterministic and testable.
- Persist minimal audit records that connect request, skill decisions, retrieval hits, and citations.
- Provide a server-side administrator grant path that cannot be invoked by public HTTP requests.

**Non-Goals:**

- Execute skill scripts, call Shell/MCP/tools, or permit model-directed tool execution.
- Add grading workflows, assignment submission, persistent grades, or automatic actions when enabling the two new skills.
- Store full answer text, chunk text, raw vector payloads, prompt text, or provider secrets in audit records.
- Change the existing authentication token format or retrieval/class-isolation behavior.

## Decisions

1. **Use a small, declarative package format, not runtime plugins.** Put one directory per skill under a server-owned `skills/` root. Each package has `skill.yaml`, `instructions.md`, and an optional `scripts/` folder; metadata includes stable key, display name, version, one-line description, declarative trigger terms/conditions, priority, and declared instruction token cost. Validate required fields, key uniqueness, normalized relative paths, and that resolved instruction paths remain under the package root. Do not import Python from skill directories. Scripts remain inert assets. This is easier to audit and package than arbitrary plugin modules and keeps untrusted content out of executable code paths.

2. **Keep deployment registry separate from class enablement.** The registry is the source of immutable package content. SQLite retains per-class enabled state and a settings version, keyed by class and skill key. Seed/migration reconciles the three built-in skill keys. For the existing `solution-guidance` row, preserve its enabled flag and map the new package definition to it; introduce `error-explanation` and `homework-review` disabled for existing classes. Keep `/api/assistant/skills/solution-guidance` as a compatibility adapter over the generalized skill endpoint. Alternative: copy full package instructions into every class row; rejected because it duplicates trusted deployment content and allows DB settings to drift from package versions.

3. **Make disclosure deterministic and never truncate instructions.** At orchestration time, fetch enabled package summaries and evaluate package-declared conditions against the latest user question using a bounded, deterministic matcher (for example normalized terms/keywords and explicit condition groups), not a model call. Always provide only one-line summaries as the catalog context. Sort matches by descending package priority, then stable key; load complete instructions while their declared costs fit `SKILL_INSTRUCTION_TOKEN_BUDGET`. Skip an instruction that does not fit rather than slicing it. Record candidate, matched, selected, disabled, and budget-skipped decisions with package and class-setting versions. Keep grounding and evidence policy outside skill control.

4. **Centralize the audit write path at operation orchestration boundaries.** Add SQLite audit operation and audit-hit rows. A parent operation stores an opaque ID, authenticated user/class, operation kind, timestamps, status, and skill-decision snapshot; child rows store material/chunk identifiers, source title snapshot, rank, retrieval modes/score, and citation index when applicable. Search operations, `/api/ask`, and SSE each create an operation. Assistant evidence retrieval is represented inside the same assistant operation rather than a second duplicate search audit. Commit an initial processing row before external provider calls, then finalize success/no-evidence/failure. Persist only identifiers, titles, scores, and decisions; never chunk text, response text, raw token, prompt or secrets. Alternative: append only application logs; rejected because they are hard to correlate reliably after restart and are not pageable audit records.

5. **Grant administrator through a local management command and dedicated authorization table.** Keep `users.role` unchanged to avoid rebuilding its SQLite CHECK constraint and to avoid conflating classroom roles with deployment-wide authority. Add a separate admin-principal table keyed by user ID; authorize through a small deployment-only CLI that requires local database access and explicit grant/revoke commands. No HTTP endpoint may create grants. This is safer and more migratable than accepting an `admin` field from login or client JSON, and does not require promoting seeded teachers. The query API checks the database grant on every request.

6. **Expose a read-only paginated audit endpoint with allowlisted filters.** Use bounded page size and explicit filters for audit ID, class/user ID, operation kind, time bounds, skill key, source material/chunk, and status. Return safe snapshots and hit/citation relationships, never content bodies. In the UI, add an admin-only audit view only if the existing project shell can expose it without giving teachers access; API security remains authoritative. Document routes and schemas in OpenAPI and test access with teacher/student fakes plus a CLI-granted administrator.

7. **Preserve old databases with transactional, idempotent migration.** Add tables/indexes using `CREATE TABLE IF NOT EXISTS`; synchronize built-in registry keys at initialization without resetting existing `solution-guidance.enabled`, assistant prompt versions, tokens, sessions, materials, chunks, or vectors. Package changes to an existing skill create a new package version; each turn snapshots both package version and class setting version so historical audit remains interpretable. Rollback removes route/UI exposure but leaves audit and registry data intact.

## Risks / Trade-offs

- [Declarative term matching may miss nuanced educational intent] → Keep matcher behavior explicit and testable; retain summaries, and allow later model-assisted classification only as a separately specified change.
- [A declared token cost may differ from a provider tokenizer] → Treat the configured budget and package cost as conservative accounting units, validate packages at startup, and never truncate full instructions.
- [Audit data can contain sensitive behavioral metadata] → Restrict reads to deployment-granted admins, minimize retained fields, paginate, and document database access/backup protections.
- [SQLite migration or reconciliation could reset an existing skill toggle] → Use additive schema and upserts that preserve existing enablement; verify against copied legacy DB fixtures before deployment.
- [Multiple writes across streaming and audit tables may leave partial records] → Commit processing state first, use transactions for hits and finalization, and make failure/interruption states queryable.

## Migration Plan

1. Add additive schema for registry sync metadata, admin grants, audit operations, and audit hits; initialize against an existing database copy and verify old records plus skill toggle values are unchanged.
2. Add package files and registry validation; confirm malformed/duplicate/path-escaping packages are rejected and scripts are never executed.
3. Reconcile per-class skill states while preserving solution-guidance and defaulting new skill rows off; verify each existing class after a second initialization.
4. Route search, `/api/ask`, and SSE through shared deterministic skill selection and audit persistence while preserving response compatibility apart from the additive `audit_id` field.
5. Add the local admin grant/revoke command, read-only audit query, OpenAPI documentation, teacher/student authorization tests, and a CLI-granted admin integration test.
6. Deploy without removing volumes or rebuilding knowledge indexes. Roll back route/UI exposure if needed; keep additive database tables and source records.

## Open Questions

None. The package format, built-in keys, matching policy, token-budget behavior, audit data minimization, and admin grant boundary are fixed above and in the specs.
