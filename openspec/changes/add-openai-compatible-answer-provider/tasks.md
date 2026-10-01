# Tasks

## 1. Provider implementation

- [x] 1.1 Add server-side configuration and explicit provider selection for `openai-compatible`, preserving the extractive default and existing generic HTTP mode; verify provider-factory tests cover each mode and incomplete configuration.
- [x] 1.2 Implement non-streaming Chat Completions request/response handling with endpoint path-prefix support, model, Bearer key, timeout, grounding prompt, accepted history, and labeled contexts; verify unit tests cover URL construction, request contents, success parsing, and invalid/network responses.
- [x] 1.3 Extend `/api/ask` tests to verify evidence-gated provider calls, current-class-only maximum-four context, client system-message filtering, citation mapping, HTTP 503 on provider failure without extractive fallback, and unchanged generic/extractive behavior; verify `pytest tests/test_answer_api.py` passes.

## 2. Workspace experience

- [x] 2.1 Update the materials template to show distinct knowledge retrieval and knowledge Q&A forms with separate results/status areas; verify both panels and their independent controls are present in the rendered workspace.
- [x] 2.2 Update workspace behavior so retrieval submits only to `/api/knowledge/search` and Q&A independently submits to `/api/ask`, rendering answers, citations, no-evidence, loading, and error states with safe text; verify neither action triggers the other.
- [x] 2.3 Add responsive styling and frontend regression assertions for the separate forms, distinct endpoint handlers, citation display, and independent status areas; verify `pytest tests/test_frontend.py` passes.

## 3. Operator configuration and regression verification

- [x] 3.1 Document the OpenAI-compatible server settings and a DeepSeek-style base URL example in `.env.example` and README, including that the model name is account-specific and the key must remain secret; verify names match application settings and the sample contains no real key.
- [x] 3.2 Run the full test suite and fix regressions caused by the provider and workspace changes; verify `pytest` passes with the default offline configuration.
