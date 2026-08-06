# Travel Insurance Multi-Agent RAG Chat — Backend

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=flat-square)](https://opensource.org/licenses/MIT)
[![Python Version](https://img.shields.io/badge/Python-3.13%2B-blue?style=flat-square&logo=python)](https://www.python.org/)
[![AWS ECS](https://img.shields.io/badge/AWS-ECS%20Fargate-orange?style=flat-square&logo=amazonaws)](https://aws.amazon.com/ecs/)
[![IaC](https://img.shields.io/badge/IaC-AWS%20CDK-blueviolet?style=flat-square)](https://aws.amazon.com/cdk/)

Enterprise-grade **multi-agent RAG system** for travel insurance — handles policy inquiries and automates claim filing using LangGraph agent orchestration, Pinecone vector search, and Google Gemini LLM. Deployed on **AWS ECS Fargate** with full Infrastructure as Code (CDK).

**Frontend Repo (Vercel):** https://github.com/vincent168e/travel-insurance-rag-chat-frontend

---

## Architecture

### AWS Infrastructure

```mermaid
graph TD
    subgraph "GitHub Actions CI/CD"
        GHA[GitHub Actions<br/>OIDC → AWS]
    end

    subgraph "AWS Cloud (us-east-1)"
        ECR[(ECR<br/>Container Registry)]
        SM[Secrets Manager<br/>API Keys]

        subgraph "VPC — Public Subnets"
            ECS[ECS Fargate Service<br/>0.25 vCPU / 0.5 GB<br/>Public IP — No ALB]
            SG[Security Group<br/>TCP :8000]
        end

        S3[(S3 Bucket<br/>Claim Images +<br/>Policy PDFs)]
        DDB[(DynamoDB<br/>Conversation State)]
        CW[CloudWatch Logs]

        ECS --> S3
        ECS --> DDB
        ECS --> SM
        ECS --> CW
    end

    subgraph "External Services"
        PC[(Pinecone<br/>Vector DB)]
        GEM[Google Gemini<br/>LLM + Embeddings]
    end

    subgraph "Frontend (Vercel)"
        FE[React SPA]
    end

    GHA -->|"docker push"| ECR
    GHA -->|"cdk deploy<br/>ecs update-service"| ECS
    FE -->|"HTTPS :8000"| SG
    ECS --> PC
    ECS --> GEM
```

### Agent Orchestration Workflow

```mermaid
graph TD
    START([User Message]) --> EE{emergency_escalation}
    EE -->|"timeout / emergency<br/>keyword + claim"| END_E([Session Closed])
    EE -->|"normal"| RO{router_orchestration}

    RO -->|"competitor detected"| END_F([Out-of-Scope])
    RO -->|"inquiry / mixed"| PI{policy_inquiry}
    RO -->|"claim"| CA{claim_action}

    PI -->|"RAG retrieval<br/>answer generated"| END_I([Response])
    PI -->|"pending claim<br/>transition"| END_T([Response + Claim Prompt])
    PI -->|"claim audit context"| CV{claim_validation}

    CA -->|"awaiting category"| END_C([Prompt: Claim Category])
    CA -->|"awaiting description"| END_D([Prompt: Description])
    CA -->|"awaiting images"| END_IMG([Prompt: Upload Proof])
    CA -->|"images provided<br/>OCR extracted"| PI

    CV -->|"unclear > 2x"| END_R([Reset Claim])
    CV -->|"unclear ≤ 2x"| END_CL([Clarification Request])
    CV -->|"validated"| END_A([Audit Report])

    style EE fill:#ff6b6b,color:#fff
    style RO fill:#ffd93d,color:#333
    style PI fill:#6bcb77,color:#fff
    style CA fill:#4d96ff,color:#fff
    style CV fill:#9b59b6,color:#fff
    style START fill:#2c3e50,color:#fff
```

**5 specialized agents** in a LangGraph state machine:

| Agent                  | Role                                                                 |
| ---------------------- | -------------------------------------------------------------------- |
| `emergency_escalation` | Keyword detection + 30-min session timeout → live-agent handoff      |
| `router_orchestration` | Intent classification (inquiry/claim/mixed), competitor guardrail    |
| `policy_inquiry`       | RAG retrieval from Pinecone → Gemini answer generation               |
| `claim_action`         | Multi-turn form filling: category → description → image upload → OCR |
| `claim_validation`     | Audit against policy clauses, clarification loop (max 2 retries)     |

---

## Tech Stack

| Layer                   | Technology                                     |
| ----------------------- | ---------------------------------------------- |
| **API**                 | FastAPI + Uvicorn                              |
| **Agent Orchestration** | LangGraph (StateGraph + conditional edges)     |
| **LLM**                 | Google Gemini (`gemini-3.1-flash-lite`)        |
| **Embeddings**          | Google Gemini (`gemini-embedding-001`, 1536-d) |
| **Vector DB**           | Pinecone (serverless, `us-east-1`)             |
| **Image Storage**       | AWS S3 (pre-signed URLs)                       |
| **Session State**       | AWS DynamoDB (LangGraph checkpointer)          |
| **Secrets**             | AWS Secrets Manager                            |
| **Container**           | Docker → ECR → ECS Fargate                     |
| **IaC**                 | AWS CDK (Python)                               |
| **CI/CD**               | GitHub Actions (OIDC)                          |
| **Logging**             | CloudWatch Logs                                |
| **Frontend**            | React (deployed on Vercel)                     |

---

## Repository Structure

```
.
├── .github/workflows/
│   └── deploy.yml                    # CI/CD: OIDC → build → CDK → ECS
├── infra/                            # AWS CDK (Infrastructure as Code)
│   ├── app.py                        # CDK entry point
│   ├── cdk.json
│   ├── requirements.txt
│   ├── travel_insurance_stack.py     # ECR, ECS, S3, DynamoDB, VPC, IAM
│   └── github-actions-policy.json    # Least-privilege IAM policy
├── scripts/
│   ├── deploy.sh                     # One-command AWS deployment
│   └── ingest.py                     # S3 → PDF → Chunk → Embed → Pinecone
├── src/
│   ├── agents/                       # Multi-agent node definitions
│   │   ├── claim_action.py
│   │   ├── claim_validation.py
│   │   ├── emergency_escalation.py
│   │   ├── policy_inquiry.py
│   │   └── router_orchestrator.py
│   ├── api/
│   │   └── index.py                  # FastAPI app (chat, upload, health)
│   ├── config.py                     # Env-driven settings
│   ├── database/
│   │   ├── dynamodb_checkpointer.py  # DynamoDB checkpointer factory
│   │   └── pinecone_client.py        # Vector query + embedding
│   ├── graph/
│   │   ├── state.py                  # AgentState TypedDict
│   │   ├── edges.py                  # Conditional routing logic
│   │   └── workflow.py               # LangGraph state machine
│   ├── services/
│   │   └── img_storage.py            # S3 upload + pre-signed URLs
│   ├── schemas.py                    # Pydantic request/response models
│   ├── messages.py                   # User-facing message templates
│   ├── constants.py                  # Emergency keywords, competitors
│   └── utils/
│       └── helpers.py                # Logging, JSON parsing, text utils
├── Dockerfile
├── pyproject.toml
└── .env.example
```

---

## Local Development

### Prerequisites

- Python 3.13+
- [uv](https://docs.astral.sh/uv/) package manager
- Pinecone API key + index
- Google Gemini API key

### Setup

```bash
# Clone and enter project
git clone <repo-url> && cd aws-travel-insurance-rag-chat-backend

# Create virtual environment
uv venv && source .venv/bin/activate

# Install dependencies
uv pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your GEMINI_API_KEY, PINECONE_API_KEY, PINECONE_INDEX_NAME
```

### Run Locally

```bash
# Start the API server
uvicorn src.api.index:app --reload --port 8000

# Health check
curl http://localhost:8000/api/health
```

Local development uses **in-memory `MemorySaver`** (no DynamoDB needed) and skips S3 when `S3_CLAIM_BUCKET` is unset.

---

## AWS Deployment

### Prerequisites

- AWS CLI installed and configured (`aws configure`)
- Docker installed and running
- AWS CDK available (`npm install -g aws-cdk` or auto-installed via `npx`)

### One-Command Deploy

```bash
./scripts/deploy.sh
```

This runs all 7 steps:

| Step | Action                                                   |
| ---- | -------------------------------------------------------- |
| 1    | Install CDK dependencies + bootstrap                     |
| 2    | Deploy infrastructure (ECR, ECS, S3, DynamoDB, VPC, IAM) |
| 3    | Guide to populate Secrets Manager                        |
| 4    | Build & push Docker image to ECR                         |
| 5    | Force ECS service redeployment                           |
| 6    | Wait for service to stabilize                            |
| 7    | Health check + print public IP                           |

**Options:**

```bash
./scripts/deploy.sh --env staging     # Deploy staging stack
./scripts/deploy.sh --with-alb        # Enable Application Load Balancer
./scripts/deploy.sh --skip-secrets    # Skip Secrets Manager prompt
./scripts/deploy.sh --tag v1.2.0      # Custom image tag
```

### Post-Deploy

```bash
# Upload policy PDFs to S3
aws s3 cp path/to/policy.pdf s3://dev-travel-insurance-claims-<account-id>/policies/

# Run ingestion to populate Pinecone
python scripts/ingest.py \
  --bucket dev-travel-insurance-claims-<account-id> \
  --prefix policies/ \
  --policy-tier "Single-trip solutions Canada package"
```

---

## API Endpoints

| Method | Path          | Description                                                          |
| ------ | ------------- | -------------------------------------------------------------------- |
| `POST` | `/api/chat`   | Main chat endpoint — accepts `ChatRequest`, returns `ChatResponse`   |
| `POST` | `/api/upload` | Upload claim evidence images → stored in S3, returns pre-signed URLs |
| `GET`  | `/api/health` | Health check for ECS load balancer / monitoring                      |

### Chat Request

```json
{
  "thread_id": "session-uuid",
  "message": "I need to file a baggage claim",
  "service_category": "claim",
  "claim_category": "baggage",
  "claim_description": "My luggage was lost on flight AC123",
  "claim_stage": "awaiting_description",
  "image_urls": ["https://pre-signed-s3-url..."]
}
```

### Chat Response

```json
{
  "thread_id": "session-uuid",
  "response": "Could you please provide a brief description of what happened?",
  "service_category": "claim",
  "claim_category": "baggage",
  "claim_description": "My luggage was lost on flight AC123",
  "session_closed": false,
  "claim_stage": "awaiting_images",
  "audit_report": null
}
```

---

## CI/CD (GitHub Actions)

Every push to `main` triggers auto-deploy via OIDC (no AWS credentials stored):

1. Checkout → OIDC auth → Docker build → push to ECR
2. CDK deploy (infrastructure as code)
3. ECS service force-redeploy → wait for stable → health check

**To enable:** add `AWS_ROLE_ARN` to GitHub repo secrets and follow the OIDC setup in `infra/github-actions-policy.json`.
