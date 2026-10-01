# Design

## Context

See proposal.md for motivation. The protected `/api/ask` route already performs class-scoped hybrid retrieval, limits evidence to four chunks, filters client `system` messages from history, and validates citation indices. `app/answer.py` currently offers an extractive provider and a generic HTTP provider with a project-specific JSON contract. `ANSWER_MODE` defaults to `extractive`; Compose loads `.env` into the app container, and the implementation currently uses Python's standard-library HTTP client. The materials workspace currently has one retrieval form; in hybrid mode its submit handler also calls `/api/ask`, so retrieval and Q&A are not independently available to the user.

## Goals / Non-Goals

**Goals:**

- Add an opt-in OpenAI-compatible Chat Completions provider for the existing answer flow.
- Make retrieval and Q&A separate, independently actionable features in the signed-in materials workspace.
- Preserve the answer/citations API response, class boundary, current citation normalization, generic HTTP mode, and offline default.
- Keep model credentials and provider requests exclusively on the server.

**Non-Goals:**

- Creating a second question endpoint or changing the existing `/api/ask` request/response contract.
- Changing retrieval or embedding algorithms, removing the existing retrieval modes, or allowing the browser to access model/vector services directly.
- Making an external model mandatory or changing the default from extractive mode.
- Adding streaming responses, a database migration, or a provider-specific SDK.

## Decisions

1. **Add an explicit `openai-compatible` mode.** Use `ANSWER_MODE=openai-compatible`, `ANSWER_API_BASE_URL`, `ANSWER_MODEL`, and `ANSWER_API_KEY`; reuse `ANSWER_TIMEOUT`. Resolve the request URL by appending `/chat/completions` to the configured base while preserving a path prefix such as `/v1`. Keep `ANSWER_API_URL` semantics for the existing generic `http` provider. This avoids overloading the old custom payload contract and leaves existing deployments unchanged. A separate mode-specific provider is preferred over changing `HttpAnswerProvider` because that provider accepts and returns a different wire format.

2. **Translate the existing provider inputs into Chat Completions messages.** The server creates a fixed grounding instruction, appends only accepted user/assistant history as conversational context, and sends the latest question together with labeled evidence chunks in the final user message. The instruction makes the retrieved chunks the only factual evidence and requests concise answers with `[1]`, `[2]` references matching their order. The provider receives no more than the already-retrieved four chunks; the route remains responsible for selecting the authenticated user's class and for citation-to-source mapping.

3. **Parse the standard non-streaming response and reuse current citation handling.** Send the configured `model` and `messages`, then extract `choices[0].message.content`. Pass its text through the existing citation normalizer and preserve the current public response shape. A malformed or empty response is a provider failure, not a reason to fabricate a new response shape.

4. **Fail closed and keep the default offline.** An incomplete OpenAI-compatible configuration, network/provider error, or invalid response results in the existing HTTP 503 provider-unavailable behavior. Do not silently fall back to extractive output after a model call fails, since that would conceal configuration failures. With `ANSWER_MODE=extractive` (the default), no external request is made. The legacy generic HTTP mode remains supported.

5. **Use the existing standard-library transport.** Build the JSON request with Python's existing `urllib` pattern, bearer-authenticate using the server-side key, apply the configured timeout, and avoid adding a runtime dependency. Keep provider error responses and credentials out of client-facing errors.

6. **Split the workspace interaction, not the backend API.** Keep the retrieval form bound only to `GET /api/knowledge/search`, and add a separate Q&A form bound only to `POST /api/ask`. Remove the current automatic answer call after a hybrid search. Keep separate loading/status/result areas so a search failure or empty result cannot masquerade as an answer failure (or vice versa). Render answer and citation text through safe text nodes and link citations to the existing protected source routes. This uses the existing APIs and avoids duplicating class-scope or retrieval logic in the browser.

## Risks / Trade-offs

- **A model may still produce unsupported claims or malformed citations** → Ground the prompt only in retrieved chunks, retain server-side citation normalization, and keep the no-evidence path from calling any provider; tests must cover citation mapping and invalid responses.
- **Provider-compatible services differ in accepted model identifiers or endpoint prefixes** → Keep the model and API base configurable, document the required base URL shape, and use a configurable timeout; do not hardcode a provider-specific model name.
- **External calls add latency and depend on network/service availability** → Preserve the deterministic extractive default and return an explicit 503 on provider failure rather than masking it.
- **API credentials could be exposed by configuration mistakes** → Read them only in the app process from server configuration, never from request data, HTML, or API responses; deployments should use HTTPS and protect `.env`.
- **Separating the panels may create stale or confusing output** → Keep the two submissions and status/results independent, clear only the relevant panel when its own query changes, and verify both no-hit and error states separately.

## Migration Plan

No data migration is needed. Existing installations continue in extractive or generic HTTP mode without configuration changes. To opt in to model-backed answers, set `ANSWER_MODE=openai-compatible`, configure the service's API base URL, model identifier, API key, and optional timeout in server-side `.env`, then restart/rebuild the app as appropriate. To roll back, restore `ANSWER_MODE=extractive` or the prior `http` mode and its `ANSWER_API_URL`; no stored data is affected. The separated workspace forms require no backend migration and continue to call the existing endpoints.

## Open Questions

None. The actual model identifier remains a deployment setting because available names depend on the selected API account.
