# Prerequisites

## Table of Contents

- [Overview](#overview)
- [Required for All Modes](#required-for-all-modes)
- [Managed Gateway](#managed-gateway)
- [Self-Hosted and Free Gateway](#self-hosted-and-free-gateway)
- [Optional — Web Search](#optional--web-search)
- [Summary Table](#summary-table)
- [Related Documents](#related-documents)

---

## Overview

LCLG routes every LLM call through the [Axemere gateway](glossary.md#gateway) — no provider API keys (OpenAI, Anthropic, etc.) are needed in your local environment. The gateway manages provider credentials on your behalf.

What you *do* need depends on which [gateway](glossary.md#gateway) variant you run against.

---

## Required for All Modes

**Python 3.11+** — check with `python3 --version`.

**A copy of this repo** — `git clone https://github.com/axemere/lclg`.

---

## Managed Gateway

The Axemere Managed Gateway runs at `us.gw.axemere.ai`. Axemere stores your provider credentials; you supply none locally.

**What you need:**

1. **Axemere account** — sign up at [axemere.ai](https://axemere.ai).

2. **Gateway token** — generate one in the Axemere console under Settings → API Keys. Set it as `AXEMERE_GATEWAY_TOKEN` in your `.env`.

3. **Project ID** (`prj_...`) — create a project in the console under Configure → Projects. Set it as `AXEMERE_PROJECT_ID` in your `.env`.

4. **Provider credentials** — LCLG calls four providers. Add credentials for each in the Axemere console under Configure → Providers:

   | Provider | Models used | Console credential |
   |----------|------------|-------------------|
   | OpenAI | `gpt-4o-mini` (Planner), `gpt-4o` (Comparator) | OpenAI API key |
   | Anthropic | `claude-haiku-4-5` (Researcher), `claude-sonnet-4-6` (Reporter, Comparator) | Anthropic API key |
   | Mistral | `mistral-large-latest` (Analyst) | Mistral API key |
   | Google | `gemini-2.5-flash` (Comparator) | Google AI Studio API key |

   You only need the providers you plan to use. The Comparator always calls all three (OpenAI + Anthropic + Google) so all four providers are needed for a full pipeline run.

   > **Google / Gemini — billing required.** The API key must come from a Google Cloud project with billing enabled. Free-tier (unlinked) keys have zero quota for models available on the `generativelanguage.googleapis.com` v1beta endpoint and will return persistent `503 UNAVAILABLE` errors on any prompt longer than a few tokens. To create a billing-enabled key:
   > 1. Go to [Google AI Studio](https://aistudio.google.com/apikey) and click **Create API key**.
   > 2. When prompted, select **Create API key in new project** — this creates a Cloud project with billing hooks.
   > 3. Visit [console.cloud.google.com/billing](https://console.cloud.google.com/billing) and link a billing account to the new project. (Gemini 2.5 Flash costs ~$0.15/million input tokens — a full pipeline run costs under $0.001 for the Gemini call.)
   > 4. Add the key to your Axemere console credential for Google.

   Docs: [Configure Providers](https://axemere.ai/docs/guides/configuration/providers)

5. **Workloads** — the five workloads used by LCLG must exist in your org. Create them in the console under Configure → Workloads:

   | Workload ID | Agent |
   |-------------|-------|
   | `wl_lclg_planner` | PlannerAgent |
   | `wl_lclg_researcher` | ResearchAgent |
   | `wl_lclg_analyst` | AnalysisAgent |
   | `wl_lclg_comparator` | ComparatorAgent |
   | `wl_lclg_reporter` | ReportAgent |

   Docs: [Configure Workloads](https://axemere.ai/docs/guides/configuration/workloads)

Modes enabled: `explicit-managed`, `proxy-managed`.

Docs: [Managed Gateway setup](https://axemere.ai/docs/guides/managed-gateway) · [API Keys](https://axemere.ai/docs/guides/api-keys)

---

## Self-Hosted and Free Gateway

Both variants run locally via Docker. Neither requires an Axemere account.

**Docker Desktop** (or Docker Engine + Compose on Linux) — [install Docker](https://www.docker.com/products/docker-desktop/).

### Free Gateway

No account. No expiry. You supply your own provider API keys to the gateway config — they never leave your machine.

```bash
curl -fsSL https://github.com/Axemere-LLC/mvgc-releases/releases/latest/download/docker-compose.free.yaml \
  -o docker-compose.free.yaml
curl -fsSL https://github.com/Axemere-LLC/mvgc-releases/releases/latest/download/default.env.example \
  -o .env
# Edit .env: set MVGC_ADMIN_TOKEN (gateway admin token) + at least one provider key (OPENAI_API_KEY, etc.)
docker compose -f docker-compose.free.yaml up -d
```

Full setup guide: [axemere.ai/docs/guides/it-setup/docker](https://axemere.ai/docs/guides/it-setup/docker)

### Self-Hosted Gateway (CP-connected)

Runs the full gateway locally, connected to the Axemere control plane for credential storage and policy management. Requires an Axemere account.

Full setup guide: [axemere.ai/docs/guides/it-setup/docker](https://axemere.ai/docs/guides/it-setup/docker)

### LCLG configuration for either

Set in your `.env`:

```bash
AXEMERE_GATEWAY_URL=http://localhost:7080
# No AXEMERE_GATEWAY_TOKEN needed for normal requests
```

Modes enabled: `explicit-selfhosted`, `proxy-selfhosted`.

---

## Optional — Web Search

The [ResearchAgent](agents.md) uses [Tavily](https://tavily.com) web search to ground its findings in current information. Without a Tavily key the agent falls back to the model's training knowledge, and the report labels each finding accordingly.

**To enable web search:**

1. Create a free Tavily account at [app.tavily.com](https://app.tavily.com) (free tier: 1,000 searches/month).
2. Copy your API key and set it in `.env`:

```bash
TAVILY_API_KEY=tvly-...
```

The research findings in the report are annotated with a source badge — **Web Search** or **Model Knowledge** — so you can see the effect of enabling or disabling web search.

---

## Summary Table

| What | When needed | Where to get it |
|------|------------|-----------------|
| Axemere account | Managed Gateway or CP-connected Self-Hosted | [axemere.ai](https://axemere.ai) |
| `AXEMERE_GATEWAY_TOKEN` | Managed modes only | Axemere console → Settings → API Keys |
| `AXEMERE_PROJECT_ID` (`prj_...`) | Managed modes | Axemere console → Configure → Projects |
| Provider credentials (OpenAI, Anthropic, Mistral, Google) | Managed modes — configured *in the console*, not in LCLG | Axemere console → Configure → Providers |
| Workloads (`wl_lclg_*`) | Managed modes | Axemere console → Configure → Workloads |
| Docker Desktop | Self-Hosted or Free Gateway | [docker.com](https://www.docker.com/products/docker-desktop/) |
| Provider API keys | Free Gateway only — configured *in the gateway config*, not in LCLG | Provider dashboards |
| `TAVILY_API_KEY` | Optional — enables web search in ResearchAgent | [app.tavily.com](https://app.tavily.com) |
| Python 3.11+ | All modes | [python.org](https://www.python.org/downloads/) |

---

## Related Documents

- [docs/gateway-integration.md](gateway-integration.md) — integration mode details and environment variables
- [docs/agents.md](agents.md) — what each agent does and which provider it calls
- [docs/glossary.md](glossary.md) — term definitions
