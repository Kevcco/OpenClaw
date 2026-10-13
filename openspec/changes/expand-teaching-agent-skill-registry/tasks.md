# Tasks

## 1. Skill package format and registry

- [x] 1.1 Define and document the validated `skill.yaml`/`instructions.md` package contract, declarative applicability fields, version, priority, cost, and optional inert scripts; verify valid, missing-field, duplicate-key, and path-traversal package fixtures
- [x] 1.2 Implement a server-owned skill directory loader and registry that rejects invalid packages without importing or executing package code; verify malformed packages are excluded and no script process is invoked
- [x] 1.3 Add the `solution-guidance`, `error-explanation`, and `homework-review` package directories with Chinese metadata/instructions and optional empty script directories; verify all three load with unique keys and declared instruction costs

## 2. Database migration and teacher settings

- [x] 2.1 Add idempotent per-class registry state/version schema and migrate built-in skills; verify legacy databases preserve prompts, sessions, materials, chunks, tokens, vectors, and each existing solution-guidance enabled flag
- [x] 2.2 Reconcile the two new skills as disabled for each existing class without resetting prior state; run initialization twice and verify no duplicate rows or version churn
- [x] 2.3 Add authenticated teacher skill-list and enablement APIs plus the workspace controls; verify all skills appear for teachers, toggles persist by class, and students receive 403
- [x] 2.4 Preserve the `/api/assistant/skills/solution-guidance` compatibility endpoint over the generalized registry; verify existing clients and API tests still read/update only the same class toggle
- [x] 2.5 Reject instruction/metadata/script writes and client-supplied class scope; verify database package content remains unchanged after forged requests

## 3. Progressive disclosure and assistant integration

- [x] 3.1 Implement deterministic package-condition matching over only the latest question and enabled class skills; verify candidates, matches, disabled, and unmatched results using table-driven tests
- [x] 3.2 Add stable priority/key ordering and configurable instruction-token budget handling that skips whole instructions rather than truncating; verify loaded cost never exceeds budget
- [x] 3.3 Integrate one-line skill summaries and selected full instructions into `/api/ask` and session SSE while retaining evidence/grounding constraints; verify provider stubs receive only selected instructions and existing citation/no-evidence tests pass
- [x] 3.4 Snapshot selected package versions and class setting versions per operation/message; verify changing packages or settings does not rewrite prior message/audit snapshots

## 4. Audit persistence and access

- [x] 4.1 Add additive SQLite audit-operation and audit-hit tables/indexes with status, decision snapshots, source metadata, score/rank, and citation linkage; verify no chunk text, answer text, prompt, token, or secret columns are stored
- [x] 4.2 Add audit lifecycle helpers and persist search, `/api/ask`, and SSE outcomes including empty evidence and provider failures; verify identifiers and hit/citation mappings with temporary SQLite tests
- [x] 4.3 Include additive `audit_id` fields in successful search/ask responses and SSE start or done events; verify old response fields and stream ordering remain compatible
- [x] 4.4 Implement local-only admin grant/revoke CLI and separate admin authorization records; verify only a CLI-granted identity can pass authorization and no HTTP request can grant itself access
- [x] 4.5 Add bounded, filtered, read-only administrator audit APIs and optional admin-only workspace view; verify teacher/student 403, opaque unauthorized responses, pagination bounds, and safe response fields

## 5. Documentation and end-to-end verification

- [x] 5.1 Document package authoring, matching/budget configuration, admin grant/revoke operations, audit retention fields, and the non-execution policy in README/OpenAPI; verify documented routes and request/response schemas match registered endpoints
- [x] 5.2 Add pytest and `apitest/` coverage for legacy migration, three skill packages, toggles, selection/budget behavior, audit persistence, citation mapping, and admin authorization; run all tests and confirm reports contain no secrets
- [ ] 5.3 Run the Compose verification and restart without deleting volumes; verify legacy class isolation, existing tokens/sessions, registry state, audit queryability, and knowledge indexes persist
