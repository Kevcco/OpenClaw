# Spec Delta

## ADDED Requirements

### Requirement: OpenAI-compatible answer provider configuration

The service MUST allow the protected `/api/ask` flow to use an OpenAI-compatible Chat Completions provider selected by server-side configuration. When this mode is enabled, the service MUST send a Chat Completions request containing the configured model and messages to `ANSWER_API_BASE_URL` with `/chat/completions` appended (preserving any configured API path prefix), and authenticate using `ANSWER_API_KEY` in a Bearer authorization header. The model MUST be selected through server-side `ANSWER_MODEL` configuration. The client-facing `/api/ask` response MUST retain its existing answer-and-citations shape. The extractive default and existing generic HTTP provider MUST remain available and MUST NOT be silently replaced when OpenAI-compatible configuration is absent or fails.

The Chat Completions messages MUST be constructed by the server from its grounding instructions, the current request's accepted user/assistant history, the latest question, and no more than the four evidence chunks retrieved for the authenticated user's class. The grounding instructions MUST designate those retrieved chunks as the only factual evidence and the history as conversational context only. Client-supplied system messages, client-supplied class identifiers, vector scores, raw vector-store records, and retrieved content from other classes MUST NOT be sent to the provider. The API key MUST remain server-side and MUST NOT be returned to clients.

#### Scenario: Configured Chat Completions provider generates a grounded answer
- **WHEN** `/api/ask` finds one or more evidence chunks and OpenAI-compatible mode is configured with an API base URL, model, and API key
- **THEN** the service sends the configured model and server-constructed messages to the Chat Completions endpoint using Bearer authentication
- **AND** the service extracts the answer text from a valid Chat Completions response and returns it with citations in the existing response shape

#### Scenario: Provider receives only permitted context
- **WHEN** the service sends a Chat Completions request for an authenticated user
- **THEN** the request contains only accepted user/assistant history, the latest question, server grounding instructions, and at most four retrieved chunks from that user's class
- **AND** it contains no client system message, client-selected class identifier, vector score, raw vector-store record, or retrieved content from another class

#### Scenario: Missing evidence skips every answer provider
- **WHEN** `/api/ask` finds no evidence chunks
- **THEN** the service returns the existing fixed not-found answer with an empty citations list
- **AND** it does not call the configured Chat Completions provider or any other answer provider

#### Scenario: Provider configuration or response is invalid
- **WHEN** OpenAI-compatible mode is selected but its required configuration is incomplete, the provider is unavailable, or the provider returns an invalid or empty answer
- **THEN** `/api/ask` returns HTTP 503 with a user-understandable error
- **AND** it does not expose the API key or raw provider credentials in the response
- **AND** it does not silently return an extractive answer as if generation succeeded

#### Scenario: Existing provider modes remain compatible
- **WHEN** the service is configured for its default extractive mode or existing generic HTTP mode
- **THEN** `/api/ask` continues to use that selected provider without requiring OpenAI-compatible settings
- **AND** the public response shape and citation validation remain unchanged

### Requirement: Workspace separates knowledge retrieval and Q&A

The signed-in materials workspace MUST present distinct, clearly labeled knowledge retrieval and knowledge Q&A interactions. Each interaction MUST have its own question/query input, submit action, result area, and status feedback. Submitting retrieval MUST call only the protected retrieval endpoint and MUST NOT automatically submit the same text to `/api/ask`, including when hybrid mode is selected. Submitting a Q&A question MUST independently call the protected `/api/ask` endpoint and MUST NOT depend on a prior retrieval action. Q&A results MUST display the answer and its numbered source citations; retrieval results MUST continue to display traceable chunks and source links. Both interactions MUST use the authenticated user's server-side class scope, show loading, empty/no-evidence, and error states, safely render material text, and avoid direct browser calls to the model or vector services.

#### Scenario: Retrieval searches without starting Q&A
- **WHEN** an authenticated user submits a query from the knowledge retrieval interaction in any supported retrieval mode
- **THEN** the workspace calls the protected knowledge search endpoint and displays its hits, sources, or no-hit state
- **AND** it does not call `/api/ask` as a side effect

#### Scenario: Q&A works independently of the retrieval interaction
- **WHEN** an authenticated user submits a question from the separate knowledge Q&A interaction without first running a retrieval search
- **THEN** the workspace calls `/api/ask` and displays the returned answer and numbered citations
- **AND** each displayed citation identifies a source that the user can open through the protected materials interface

#### Scenario: No-evidence Q&A displays the not-found state
- **WHEN** `/api/ask` returns its fixed not-found answer with no citations
- **THEN** the workspace displays the not-found answer in the Q&A result area
- **AND** it does not display fabricated citation cards or retrieval hits as Q&A evidence

#### Scenario: Workspace isolates pending and failure states
- **WHEN** either interaction is loading, receives no evidence, or encounters an API error
- **THEN** its own result area displays the matching status without misreporting the other interaction's state
- **AND** all answer and source text is rendered as plain text
