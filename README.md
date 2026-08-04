# Travel Insurance Inquiry & Claim Chat App (Backend)

[![Vercel Deployment](https://img.shields.io/badge/Deployed%20on-Vercel-black?style=flat-square&logo=vercel)](https://vercel.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=flat-square)](https://opensource.org/licenses/MIT)
[![Python Version](https://img.shields.io/badge/Python-3.10%2B-blue?style=flat-square&logo=python)](https://www.python.org/)
[![API Spec](https://img.shields.io/badge/API-REST%20%2F%20Streaming-orange?style=flat-square)](https://fastapi.tiangolo.com/)

This repository contains the backend service for the **Travel Insurance Inquiry & Claim Chat Application**. Built as an enterprise-grade Retrieval-Augmented Generation (RAG) system, it handles complex customer queries regarding policy coverage, terms, exclusions, and automates initial claim filing and status tracking using LLM function/tool calling capabilities.

The service is fully optimized for serverless environments and is deployed via **Vercel Serverless Functions**, interacting seamlessly with a React/Next.js frontend.

**Frontend Repo:** https://github.com/vincent168e/travel-insurance-rag-chat-frontend

---

## 🚀 Core Features

- **Hub-and-Spoke Agent Orchestration:** Utilizes a centralized coordinator (the hub) to analyze incoming user queries and intelligently route execution tasks to specialized sub-agents or distinct tool sets (the spokes)—such as policy validation, database verification, or claim processing modules.
- **Retrieval-Augmented Generation (RAG):** Context-aware question answering backed by vector search across complex insurance policy PDFs, terms of service, and coverage boundaries.
- **Automated Claims Handling:** Leverages tool calling (function execution) to guide users through the structured data collection required to file or check a travel insurance claim.
- **Conversational Memory:** Manages session-based chat histories to ensure multi-turn dialog consistency over stateless serverless environments.
- **Guardrails & Compliance:** Validates responses to ensure the AI agent operates strictly within policy boundaries without fabricating coverage details (hallucination mitigation).
- **Streaming Responses:** Supports Server-Sent Events (SSE) to stream real-time tokens back to the frontend UI for lower perceived latency.

---

## 🛠️ Tech Stack & Architecture

- **Orchestration Framework:** LangGraph
- **API Engine:** FastAPI
- **Vector Database:** Pinecone (Vector storage for policy embeddings)
- **Embeddings & LLM:** Gemini (gemini-embedding-001 / gemini-3.1-flash-lite)
- **Deployment & Hosting:** Vercel Serverless Functions

### System Data Flow

1. **Inquiry Pipeline:** `User Query` ➡️ `Frontend App` ➡️ `Vercel Backend` ➡️ `Vector Embeddings Search` ➡️ `Context Enrichment` ➡️ `LLM Inference` ➡️ `Streamed Response`
2. **Claim Pipeline:** `User Claim Intent` ➡️ `Agent Detects Function Trigger` ➡️ `Structured Extraction (Fields: Policy ID, Flight Delay Duration, Loss Amount)` ➡️ `Mock/Core Database Write` ➡️ `Confirmation to User`

---

## 📁 Repository Structure

```text
src/
├── agents/           # Mutli-agent node definitions & system prompts
├── api/              # Main application gateway
├── database/         # DB clients (vector / traditional)
├── graph/            # LangGraph Workflow & Orchestration
├── services/         # Tool definitions (e.g., OCR)
└── utils/            # Helpers
```

---

## 🛠️ Local Development & Execution (via `uv`)

This project supports **[uv](https://github.com/astral-sh/uv)**, an enterprise-grade, extremely fast Python package installer and resolver written in Rust. Using `uv` drastically reduces environment setup times and simplifies dependency management.

### 1. Install `uv`

If you do not have `uv` installed globally, run the installation script appropriate for your operating system:

```bash
# macOS / Linux
curl -LsSf [https://astral.sh/uv/install.sh](https://astral.sh/uv/install.sh) | sh
# Windows (PowerShell)
powershell -c "irm [https://astral.sh/uv/install.ps1](https://astral.sh/uv/install.ps1) | iex"
# Alternative via Homebrew (macOS)
brew install uv
# Alternative via pip
pip install uv
```

### 2. Set Up Environment

```bash
# Create a virtual environment using uv
uv venv

# Activate the environment
# On macOS/Linux:
source .venv/bin/activate
# On Windows (Command Prompt):
.venv\Scripts\activate.bat
# On Windows (PowerShell):
.venv\Scripts\Activate.ps1

# Install dependencies using uv's high-speed pip resolver
uv pip install -r requirements.txt
```

### 3. Execution

```bash
# Populate vector database embeddings
python src/database/ingest_policies.py

# Boot up the local development gateway
uvicorn api.index:app --reload --port 8000
```
