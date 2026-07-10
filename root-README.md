# 🤖 AI Agents & MCP — From Scratch to Production

A hands-on journey from *"what is an AI agent?"* to two complete, production-grade **agentic AI** applications built on the **Model Context Protocol (MCP)**.

This repository documents the whole path — starting with a bare LLM-in-a-loop, adding tools, memory, MCP servers, a client, orchestration with LangGraph, observability, evaluation, RAG, and guardrails — and culminating in two real, portfolio-grade projects.

---

## 🚀 The projects

### 📊 [Riso Analyst](phase-07-AI-Data-Analyst-Agent/) — an agentic data analyst
Chat with any CSV in plain English and get SQL-powered answers and **interactive charts**. A single LangGraph agent orchestrates three custom MCP servers (SQL over DuckDB, charting, and a RAG glossary), streams its work live, shows the SQL behind every answer, and is fully guarded (read-only, off-topic refusal). Swappable between a local model and a free cloud API.

> **Stack:** LangGraph · MCP · DuckDB · Vega-Altair · FastAPI · Chroma · Langfuse · Ragas

### 🕸️ [RepoGraph](phase-08-codebase-graph/) — an agentic codebase visualizer
Paste a GitHub URL and get an **interactive graph** of the codebase (files, functions, classes as nodes; imports as edges), with god-node detection and a Detailed/Architecture toggle. Then **ask the repo questions** or click any node to have the AI explain it — answers are grounded in the real code with file citations.

> **Stack:** Python `ast` · NetworkX · Pyvis · FAISS · FastAPI · sentence-transformers

---

## 🧭 The learning journey (how it was built)

Each phase is a working milestone that builds on the last:

1. **First agent** — an LLM in a loop with a single tool (the core of every agent).
2. **Multi-tool + memory** — several tools and SQLite-backed conversation memory.
3. **MCP fundamentals** — building the first MCP server (tools, resources, prompts).
4. **Custom MCP client** — wiring an agent to MCP servers over the protocol.
5. **Orchestration** — graduating to **LangGraph** for stateful, multi-tool agents.
6. **Production quality** — observability (Langfuse), evaluation (custom harness + Ragas), RAG, and guardrails.
7. **Capstone I — Riso Analyst** — the data-analyst application.
8. **Capstone II — RepoGraph** — the codebase-visualizer application.

---

## 🛠️ Core skills demonstrated

- **Agentic AI** — tool-calling agents, the reason→act loop, LangGraph orchestration
- **Model Context Protocol** — building and consuming MCP servers; multi-server clients
- **RAG** — chunking, embeddings, vector search (Chroma / FAISS) with cited answers
- **Production concerns** — tracing, evaluation, guardrails, streaming UIs
- **Full-stack delivery** — FastAPI backends with SSE streaming + custom web frontends
- **Model flexibility** — swappable local (Ollama) / cloud (NVIDIA) via config

---

## 📂 Repository layout

```
ai-agents-mcp-lab/
├── README.md                          ← you are here
├── phase-07-AI-Data-Analyst-Agent/    → Riso Analyst  (see its README)
└── phase-08-codebase-graph/           → RepoGraph      (see its README)
    (earlier phases document the learning steps that led here)
```

---

*Two agentic systems, built from first principles — turning "what's an agent?" into shipped, working software.*
