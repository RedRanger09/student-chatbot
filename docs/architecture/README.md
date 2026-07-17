# Architecture

This folder documents the system design of the Student Support Services AI Chatbot.

## Contents

| File | Description |
|------|-------------|
| [`system-architecture.md`](./system-architecture.md) | End-to-end ASCII architecture diagram (UI → API → RAG → LLM) |

## High-level flow

1. **Next.js UI** sends chat, upload, and settings requests to FastAPI.
2. **ChatService** orchestrates each turn: memory → intent → safety → retrieval → generation.
3. **ProviderFactory** selects LM Studio (configured endpoint) or Gemini (user browser key, then optional server fallback).
4. **Institutional KB** (persistent FAISS) answers campus FAQ / policy questions.
5. **Session KB** (in-memory FAISS) answers questions about uploaded student notes.
6. **Hybrid knowledge mode** chooses grounded RAG, general educational AI, or a clear “no official info” reply.
7. **LLM providers** generate the final answer with citations when grounded.

See the root README **AI Providers** section for Auto / remote LM Studio / user Gemini key security details.

For installation and API details, see the root [`README.md`](../../README.md).
