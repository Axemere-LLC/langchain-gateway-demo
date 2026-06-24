# Glossary

Terms used across the LCLG documentation. Each entry links back to the
document where the term is used in context.

## Table of Contents

- [Attribution](#attribution)
- [Attribution Labels](#attribution-labels)
- [ChatAiGateway](#chataigateway)
- [Explicit Mode](#explicit-mode)
- [Gateway](#gateway)
- [LCEL](#lcel)
- [Managed Gateway](#managed-gateway)
- [AiGatewayConfig](#aigatewayconfig)
- [Project ID](#project-id)
- [Proxy Mode](#proxy-mode)
- [RunnableParallel](#runnableparallel)
- [Self-Hosted Gateway](#self-hosted-gateway)
- [Workload](#workload)

---

## Attribution

The mechanism by which every gateway request is associated with an
organization, workload, and project for cost tracking and audit purposes. The
Axemere gateway records `workload_id`, `project_id`, and `attribution.labels`
with every execution record.

Used in: [agents.md](agents.md), [gateway-integration.md](gateway-integration.md)

---

## Attribution Labels

Arbitrary key-value metadata attached to individual gateway requests via
`attribution.labels`. Intended for per-call metadata (agent name, pipeline run
ID, etc.) that is not already a first-class attribution field. `project_id` is
not a label.

Used in: [agents.md](agents.md#attribution-labels), [gateway-integration.md](gateway-integration.md#attribution)

---

## ChatAiGateway

A LangChain `BaseChatModel` subclass from the `axemere-gateway-langchain` SDK.
Implements [explicit mode](#explicit-mode) — every `invoke()` call becomes a
`POST /v1/actions:execute` request to the [gateway](#gateway). Drop-in
replacement for `ChatOpenAI` or `ChatAnthropic` in LangChain chains.

Used in: [agents.md](agents.md), [gateway-integration.md](gateway-integration.md#sdk-reference)

---

## Explicit Mode

An integration pattern where the calling application sends a fully-formed
`mvgc.action_request.v2` JSON document to `POST /v1/actions:execute`. Attribution
fields are first-class in the request body. Implemented via
[`ChatAiGateway`](#chataigateway). Contrast with [proxy mode](#proxy-mode).

Used in: [architecture.md](architecture.md#integration-modes), [gateway-integration.md](gateway-integration.md#explicit--managed-default)

---

## Gateway

The Axemere managed proxy that sits between LangChain agents and AI providers.
Enforces policy, manages provider credentials, meters usage, and records every
request. Available as a [managed service](#managed-gateway) or as a
[self-hosted](#self-hosted-gateway) Docker container.

Used in: [architecture.md](architecture.md), [gateway-integration.md](gateway-integration.md)

---

## LCEL

LangChain Expression Language — the composable chain syntax used throughout
this project (`prompt | llm | parser`). Enables readable pipeline construction
and supports `.invoke()`, `.batch()`, `.stream()`, and `.astream()`.

Used in: [agents.md](agents.md)

---

## Managed Gateway

The Axemere-operated gateway service at `us.gw.axemere.ai`. Requires a Bearer
gateway token (`axemere_k_...`). Axemere manages infrastructure, certificates,
and provider credential storage. The `us.` prefix is regional; additional
regions follow the `{region}.gw.axemere.ai` pattern.

Used in: [architecture.md](architecture.md#integration-modes), [gateway-integration.md](gateway-integration.md#authentication)

---

## AiGatewayConfig

A Python dataclass (`axemere.gateway.AiGatewayConfig`) that holds gateway
connection and attribution settings. Populated via `AiGatewayConfig.from_env()`
which reads `AXEMERE_*` environment variables. Passed to `ChatAiGateway` and
proxy helper functions.

Used in: [gateway-integration.md](gateway-integration.md#sdk-reference)

---

## Project ID

A first-class attribution field (`project_id`) that groups requests for billing
and chargeback. Set once via `AXEMERE_PROJECT_ID` and flows through
`AiGatewayConfig.from_env()` to every agent call. Not a label.

Used in: [agents.md](agents.md#attribution-labels), [gateway-integration.md](gateway-integration.md#attribution)

---

## Proxy Mode

An integration pattern where standard LangChain provider classes (`ChatOpenAI`,
`ChatAnthropic`) are pointed at the gateway's proxy path prefix (e.g.
`/proxy/openai`). The gateway intercepts and governs the call transparently.
Attribution is injected as HTTP headers by helper functions
(`ai_gateway_openai_client()`). Contrast with [explicit mode](#explicit-mode).

Used in: [architecture.md](architecture.md#integration-modes), [gateway-integration.md](gateway-integration.md#proxy--managed)

---

## RunnableParallel

A LangChain construct that executes multiple chains concurrently and returns a
dict of results. Used by the `ComparatorAgent` to fan the same prompt to
OpenAI, Anthropic, and Gemini simultaneously, all governed under the same
workload attribution.

Used in: [architecture.md](architecture.md), [agents.md](agents.md)

---

## Self-Hosted Gateway

The Axemere gateway run locally via `docker compose up`. Available at
`http://localhost:7080` by default. No authentication is required for normal
requests (`POST /v1/actions:execute`). Admin routes (`/v1/dashboard/*`,
`/v1/records/*`) require an `MVGC-Admin-Token` header. Provider credentials
are configured in the gateway's local configuration.

Used in: [architecture.md](architecture.md#integration-modes), [gateway-integration.md](gateway-integration.md#explicit--self-hosted)

---

## Workload

An identifier (`workload_id`) that represents a specific application or agent
within an organization. Used by the gateway as a policy boundary, rate-limit
window key, and attribution dimension. Workload IDs in this project use the
`wl_` prefix and follow the pattern `wl_lclg_<agent>`.

Used in: [agents.md](agents.md#workload-registration), [gateway-integration.md](gateway-integration.md#attribution)
