# Proposal

## Why

CampusClaw already exposes protected retrieval and `/api/ask` endpoints, but the default answer provider is extractive, the optional HTTP provider expects a project-specific request format, and the workspace combines retrieval with automatic answering instead of offering two independent user actions. The change should make model-backed Q&A configurable and give a classroom demo distinct, easy-to-understand knowledge retrieval and knowledge Q&A workflows.

## What Changes

- Add a configurable OpenAI-compatible Chat Completions answer provider for the existing `/api/ask` flow.
- Present knowledge retrieval and knowledge Q&A as separate workspace panels with independent inputs, actions, results, and status feedback.
- Make retrieval submit only a retrieval request; make Q&A submit independently to `/api/ask` and show its answer and citations.
- Keep retrieval, class isolation, citation normalization, the offline extractive default, and the existing generic HTTP provider behavior intact.
- Document server-side model, endpoint, timeout, and API-key configuration without exposing secrets to browsers or clients.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `traceable-vector-retrieval`: define the configurable OpenAI-compatible answer-provider behavior and require separate workspace interactions for retrieval and cited Q&A while retaining existing evidence and class-isolation guarantees.

## Impact

Affected areas include `app/answer.py`, application configuration in `app/__init__.py`, `app/templates/materials.html`, `app/static/workspace.js`, workspace styles, provider and frontend tests, environment configuration, and setup documentation. No new dependency or change to the public `/api/ask` response shape is intended.
