---
name: development-skill
description: Prepares and guides backend GenAI service development in Python with structured planning, architecture defaults, quality gates, and starter templates. Use when users ask to build/create/develop/setup/implement a backend, service, or API with AI/LLM/generative capabilities.
---

# Development Skill

## Metadata
- Name: `development-skill`
- Category: `Development`
- Target Audience: `Backend developers, AI engineers`
- Context: `Python, Gen AI, Backend Services`
- Trigger Keywords: `build`, `create`, `develop`, `setup`, `implement` + backend context (`backend`, `service`, `api`)

## Trigger Heuristics
Apply this skill when both conditions are true:
1. The user asks for implementation (for example: "build me", "create", "develop", "setup", "implement").
2. The request includes backend context (`API`, `service`, `backend`, `microservice`, `endpoint`) and likely GenAI/LLM needs.

Do not auto-apply for:
- Pure frontend/UI requests.
- Minor bug fixes unrelated to backend architecture.
- Non-Python stacks unless the user explicitly asks for Python conversion.

## Execution Contract
When this skill activates, follow exactly this sequence:
1. Ask clarifying questions.
2. Generate a structured development plan.
3. Inject implementation instructions for the agent.
4. Provide starter code skeletons.

Keep guidance opinionated by default, but offer alternatives with clear trade-offs.

## Step 1 - Clarifying Questions
Ask these questions before coding:

1. Use case: chatbot, content generation, extraction, classification, agentic workflow, or other?
2. Scale and latency target: expected RPS/concurrency and p95 response time?
3. Data requirements: no database, SQL, NoSQL, vector store, or hybrid?
4. Deployment target: AWS/GCP/Azure/Render/Fly.io/Kubernetes/on-prem?
5. Model/provider constraints: OpenAI/Anthropic/local models, cost ceiling, data residency?
6. Security/auth: public API, internal service, or tenant-isolated SaaS?

If answers are incomplete, continue with defaults:
- Framework: FastAPI
- Python: 3.11
- Dependency manager: uv (or poetry/pip-tools if team requires)
- LLM provider abstraction: provider-agnostic wrapper
- Auth: OAuth2/JWT for public APIs, service tokens for internal APIs

## Step 2 - Structured Development Plan Generation
Output a plan with the sections below.

### A) Project Structure Template
Use this default layout:

```text
backend-genai-service/
  pyproject.toml
  README.md
  .env.example
  Dockerfile
  Makefile
  app/
    main.py
    api/
      v1/
        routes/
          health.py
          generation.py
    core/
      config.py
      logging.py
      security.py
      exceptions.py
    services/
      genai_service.py
    repositories/
      # db access adapters
    schemas/
      generation.py
      common.py
    models/
      # ORM models if needed
  tests/
    unit/
    integration/
    e2e/
```

### B) Architecture Design
- API pattern:
  - Prefer REST for most product APIs.
  - Consider gRPC for low-latency internal service-to-service communication.
- Layer boundaries:
  - Route layer: validation + transport concerns only.
  - Service layer: business logic and GenAI orchestration.
  - Repository layer: persistence abstractions.
- GenAI integration points:
  - Prompt construction module.
  - Provider client wrapper with retries/rate limits.
  - Optional cache for deterministic prompts/responses.
  - Token/cost telemetry pipeline.

### C) Implementation Phases
- Phase 1: Setup and dependencies (complexity: Low)
  - Create project, env management, lint/test tooling, baseline config.
- Phase 2: Core scaffolding (complexity: Medium)
  - Build app skeleton, routing, schemas, configuration, error middleware.
- Phase 3: GenAI integration (complexity: High)
  - Implement provider wrapper, prompts, retries, rate limits, observability.
- Phase 4: Testing and validation (complexity: Medium-High)
  - Unit tests, integration tests, contract tests, cost/latency checks.
- Phase 5: Deployment readiness (complexity: Medium)
  - Containerization, health probes, CI, runtime config, runbook.

### D) Technology Stack Recommendations
Choose with rationale:
- Framework:
  - FastAPI (default): async-first, typed, OpenAPI out of the box.
  - Django: best when admin panel, ORM-heavy monolith needs, batteries included.
  - Flask: minimal footprint for small/simple services.
- Data:
  - PostgreSQL for transactional data.
  - Redis for caching/rate-limit counters.
  - Vector DB only when semantic retrieval is required.
- GenAI libraries:
  - Native SDK-first for simpler systems (`openai`, `anthropic`).
  - LangChain for complex chaining/tool patterns.
  - LlamaIndex when retrieval/indexing is core.
- Supporting tools:
  - Validation/settings: `pydantic`, `pydantic-settings`
  - HTTP client: `httpx`
  - Retry: `tenacity`
  - Rate limit: `slowapi` or gateway-level limits
  - Logging: `structlog` or stdlib JSON logging
  - Metrics/tracing: OpenTelemetry + Prometheus

### E) Quality Standards
- Code quality:
  - Full type hints for public/internal function interfaces.
  - Docstrings on modules, classes, and non-trivial functions.
  - Formatting via Black, linting via Ruff, type-checking via mypy.
- Testing:
  - Unit tests for business logic.
  - Integration tests for provider/database boundaries.
  - E2E/API tests for critical flows.
- Documentation:
  - Setup instructions, env vars, architecture notes, operational runbook.
- Performance:
  - Define baseline p95 latency and throughput targets.
  - Track token usage and provider call duration.
- Security checklist:
  - Secret handling, authN/authZ, input validation, rate limiting, audit logs.

## Step 3 - Instruction Injection For Agent Execution
Inject and enforce these instructions while implementing:

### A) Code Standards
- Use type hints for all functions and method returns.
- Include clear docstrings (Google or NumPy style, one style only).
- Follow PEP 8, enforce with Black + Ruff.
- Use async/await for I/O-bound paths.
- Raise custom exceptions and map to consistent API error responses.

### B) GenAI Integration Best Practices
- Use prompt templates with explicit variable names and guardrails.
- Track request tokens, response tokens, and per-call estimated cost.
- Add retry with exponential backoff for transient provider failures.
- Add rate limiting at route and/or API gateway layer.
- Add structured monitoring for provider errors, latency, token spikes.
- Cache safe/idempotent responses with TTL where value is high.

### C) Development Workflow
- Prefer test-first or test-alongside implementation.
- Use dependency injection for providers/repositories.
- Use structured logging with request IDs and correlation IDs.
- Centralize config in a typed settings module.
- Keep OpenAPI docs current with models/examples.
- Include `/health/live`, `/health/ready`, and `/metrics` endpoints.

### D) Security Guidelines
- Never hardcode API keys; read from environment or a secret manager.
- Validate and sanitize all user inputs.
- Configure CORS intentionally; avoid wildcard in production.
- Enforce authentication and authorization by endpoint sensitivity.
- Add audit logs for security-sensitive operations.
- Enforce HTTPS at ingress/load balancer and app assumptions.

## Step 4 - Starter Code Skeletons
Use the following templates as first scaffolding pass.

### 1) Application Entry Point (`app/main.py`)
```python
from contextlib import asynccontextmanager
from fastapi import FastAPI

from app.api.v1.routes.generation import router as generation_router
from app.api.v1.routes.health import router as health_router
from app.core.config import settings
from app.core.logging import configure_logging


@asynccontextmanager
async def lifespan(_: FastAPI):
    configure_logging(settings.log_level)
    # Initialize shared clients/resources here.
    yield
    # Close resources here.


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
)
app.include_router(health_router, prefix="/api/v1")
app.include_router(generation_router, prefix="/api/v1")
```

### 2) Configuration Management (`app/core/config.py`)
```python
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    app_name: str = "backend-genai-service"
    app_version: str = "0.1.0"
    environment: str = Field(default="dev")
    log_level: str = Field(default="INFO")

    openai_api_key: str | None = None
    anthropic_api_key: str | None = None
    default_model: str = "gpt-4.1-mini"
    request_timeout_seconds: float = 30.0
    max_retries: int = 3


settings = Settings()
```

### 3) GenAI Service Wrapper (`app/services/genai_service.py`)
```python
from dataclasses import dataclass
from time import perf_counter

from tenacity import retry, stop_after_attempt, wait_exponential


@dataclass
class GenAIResult:
    text: str
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    latency_ms: float
    estimated_cost_usd: float


class GenAIService:
    def __init__(self, provider_client: object, model: str, max_retries: int = 3):
        self.provider_client = provider_client
        self.model = model
        self.max_retries = max_retries

    @retry(
        wait=wait_exponential(multiplier=0.5, min=0.5, max=8),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    async def generate(self, prompt: str) -> GenAIResult:
        started = perf_counter()
        # Replace with provider SDK call.
        text = f"stubbed response for: {prompt[:60]}"
        latency_ms = (perf_counter() - started) * 1000
        return GenAIResult(
            text=text,
            provider="stub",
            model=self.model,
            input_tokens=max(1, len(prompt) // 4),
            output_tokens=max(1, len(text) // 4),
            latency_ms=latency_ms,
            estimated_cost_usd=0.0,
        )
```

### 4) API Endpoint Template (`app/api/v1/routes/generation.py`)
```python
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.services.genai_service import GenAIService

router = APIRouter(tags=["generation"])


class GenerateRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=8000)


class GenerateResponse(BaseModel):
    text: str
    model: str
    latency_ms: float


def get_genai_service() -> GenAIService:
    return GenAIService(provider_client=object(), model="gpt-4.1-mini")


@router.post("/generate", response_model=GenerateResponse)
async def generate_text(
    payload: GenerateRequest,
    service: GenAIService = Depends(get_genai_service),
) -> GenerateResponse:
    try:
        result = await service.generate(payload.prompt)
        return GenerateResponse(text=result.text, model=result.model, latency_ms=result.latency_ms)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Upstream GenAI provider failure",
        ) from exc
```

### 5) Error Utilities (`app/core/exceptions.py`)
```python
from dataclasses import dataclass


@dataclass
class AppError(Exception):
    code: str
    message: str
    http_status: int = 400


class ConfigurationError(AppError):
    pass


class ProviderRateLimitError(AppError):
    pass


class ProviderTimeoutError(AppError):
    pass
```

## Required Output Format When Skill Runs
Use this response structure each time:

1. **Clarifying Questions** (if missing data)
2. **Proposed Stack + Rationale**
3. **Project Structure**
4. **Phase Plan** (with complexity per phase)
5. **Agent Instruction Injection Summary**
6. **Starter Skeleton Snippets**
7. **Immediate Next Actions** (first 3 implementation tasks)

## Framework Selection Rules
- Choose **FastAPI** when:
  - Async I/O, typed APIs, and fast iteration are priorities.
- Choose **Django** when:
  - Admin workflows, mature ORM ecosystem, and monolith velocity dominate.
- Choose **Flask** when:
  - Minimal service, highly custom wiring, or migration from legacy Flask exists.

If uncertain, default to FastAPI and explain why.

## Minimal Dependency Baseline (suggested)
```text
fastapi
uvicorn[standard]
pydantic
pydantic-settings
httpx
tenacity
python-dotenv
ruff
black
mypy
pytest
pytest-asyncio
```

## Example Trigger Matches
- "Build me a Python backend API for customer support chat using OpenAI."
- "Create a service with FastAPI that summarizes documents with Anthropic."
- "Develop a backend microservice for content generation with retries and caching."

## Non-Trigger Examples
- "Fix CSS in the dashboard."
- "Refactor this React hook."
- "Create a static HTML landing page."
