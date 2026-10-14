---
id: w4-cloud
week: 4
kind: lesson
title: Managing containerized AI apps on the cloud
short: Containers on the cloud
minutes: 50
summary: Choose a runtime for your containers, size and autoscale it for I/O-bound LLM traffic, wire up networking, secrets, and managed data services, and keep the bill predictable.
---

## Choosing a runtime

Your Relay image can run on many platforms. The choice is mostly about how much infrastructure you want to operate.

| Platform | Model | Good for | Trade-offs |
|---|---|---|---|
| Google Cloud Run, Azure Container Apps | Serverless containers, scale to zero, per-request billing | Most API-calling AI apps, small teams, spiky traffic | Request timeouts (Cloud Run up to 60 min), cold starts, less control |
| AWS ECS on Fargate | Managed containers, no servers | AWS shops, steady services | More configuration (task defs, load balancers); [ECS Express Mode](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/express-service-overview.html) sets up the load balancer and autoscaling for you |
| Fly.io, Render, Railway | Developer platforms | Fast setup, free or cheap small apps | Fewer enterprise features |
| Kubernetes (GKE, EKS, AKS) | Full orchestration | Many services, GPUs, custom networking, platform teams | Significant operational cost |
| VMs | You manage everything | Special hardware or licensing | You manage everything |

AWS App Runner, once the obvious AWS answer here, is [no longer open to new customers](https://docs.aws.amazon.com/apprunner/latest/dg/what-is-apprunner.html); AWS points new users to ECS Express Mode.

> [!rule] If your app calls hosted model APIs and you do not already run Kubernetes, start on a serverless container platform. Move only when you hit a concrete limit.

**When you self-host models** (open-weights models such as Llama, Qwen, DeepSeek or Mistral on GPUs), the picture changes: GPU scheduling, model loading time, and batching make Kubernetes (GKE, EKS, AKS) with an inference server such as vLLM, or a managed inference platform, the usual choice. Serverless GPUs exist too: [Cloud Run](https://docs.cloud.google.com/run/docs/configuring/services/gpu) offers NVIDIA L4 and RTX PRO 6000 Blackwell GPUs. This course focuses on API-calling apps; the same deployment principles apply to the API layer in front of self-hosted models.

**Each cloud also resells models**, which can matter more than the container runtime: billing, data residency and private networking stay inside one account. [Amazon Bedrock](https://docs.aws.amazon.com/bedrock/latest/userguide/model-cards.html) lists Anthropic, Meta, Mistral, DeepSeek, Qwen and OpenAI open-weights models among others; [Vertex AI Model Garden](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/model-garden/explore-models) offers Gemini, partner models such as Claude, and open models; [Microsoft Foundry](https://learn.microsoft.com/en-us/azure/foundry/foundry-models/concepts/models-sold-directly-by-azure) sells OpenAI's models and others directly. A router or gateway (OpenRouter, LiteLLM) gives a similar single bill across vendors outside any one cloud.

## LLM apps are I/O bound

A request to Relay spends perhaps 95% of its time waiting: for the model API, the database, the reranker. CPU and memory use per request are small. This shapes sizing and scaling:

- **Use async servers** (FastAPI on uvicorn with async handlers and async clients). One process can hold hundreds of concurrent waiting requests.
- **Scale on concurrency, not CPU.** CPU-based autoscaling sees idle CPUs and never scales out, while requests queue. Cloud Run's [concurrency setting](https://docs.cloud.google.com/run/docs/about-concurrency), Azure Container Apps' [HTTP scale rule](https://learn.microsoft.com/en-us/azure/container-apps/scale-app) (concurrent requests per replica), and Kubernetes HPA on custom metrics (in-flight requests) fit better.
- **Long requests limit throughput per instance.** If streams last 20 seconds, each instance can only complete a bounded number per minute even when idle.

> [!numbers] Peak: 40 new chats/sec, each holding a streaming connection for 12 s on average. By Little's law, concurrent requests = arrival rate × duration = 40 × 12 = **480**. With async instances configured for 80 concurrent requests each, you need 6 instances at peak, 8 with headroom. Memory per in-flight request is small (tens of KB of conversation), so 1 vCPU / 1 GB instances are plenty. Your real bottleneck will be the model provider's rate limits, not compute.

```viz
caption: Size by concurrency. 480 requests in flight at 80 per instance is 6 instances, while each one's CPU sits nearly idle.
<div class="vz-row"><span class="ch sk">40 chats/s</span>x<span class="ch sk">12 s each</span>=<span class="ch sk c">480 in flight</span></div>
<div class="vz-row"><span class="ch sk c">80</span><span class="ch sk c">80</span><span class="ch sk c">80</span><span class="ch sk c">80</span><span class="ch sk c">80</span><span class="ch sk c">80</span><span class="ch sk ghost g">spare</span><span class="ch sk ghost g">spare</span></div>
<p>6 instances at 80 each, plus 2 for headroom</p>
<div class="vz-bars"><span>concurrency used</span><span class="bar sk"><i class="sk c" style="--w:100%"></i></span><b>80 of 80</b><span>CPU used</span><span class="bar sk"><i class="sk g" style="--w:8%"></i></span><b>low</b></div>
<div class="vz-src">Little's law with the worked example's traffic. Cloud Run's default is 80 concurrent requests per vCPU, settable up to 1,000: <a href="https://docs.cloud.google.com/run/docs/about-concurrency">Cloud Run docs</a>.</div>
```

## Cold starts and minimum instances

Scale-to-zero platforms start containers on demand. A Python app that imports heavy libraries can take several seconds to start, which a user experiences as a slow first response.

- Keep images small and imports lean (do not import a local reranker model in the API container if it is only used by workers).
- Set **minimum instances** to 1 or 2 for user-facing services. The cost is small compared with the experience.
- Lazy-load rarely used heavy components.

## Networking and data services

A minimal production layout on Google Cloud (the table after the diagram maps it to AWS and Azure):

```mermaid
flowchart TB
  U[Users] --> LB[HTTPS load balancer<br/>+ Cloud Armor WAF]
  LB --> API[Cloud Run: relay-api<br/>min 1, max 20]
  API --> SQL[(Cloud SQL Postgres<br/>+ pgvector, private IP)]
  API --> R[(Memorystore Redis)]
  API --> PUB[Pub/Sub or<br/>Postgres queue]
  PUB --> WRK[Cloud Run: relay-worker<br/>scaled on backlog]
  WRK --> SQL
  WRK --> GCS[(Cloud Storage)]
  API & WRK --> SM[Secret Manager]
  API & WRK --> LLM[Model provider API]
  API & WRK --> OBS[Logging, tracing, metrics]
```

| Piece | Google Cloud | AWS | Azure |
|---|---|---|---|
| Serverless containers | Cloud Run | ECS on Fargate | Container Apps |
| Managed Postgres + pgvector | Cloud SQL, AlloyDB | RDS, Aurora | Azure Database for PostgreSQL |
| Redis-compatible cache | Memorystore | ElastiCache | Azure Managed Redis |
| Queue | Pub/Sub, Cloud Tasks | SQS | Service Bus |
| Object storage | Cloud Storage | S3 | Blob Storage |
| Secrets | Secret Manager | Secrets Manager | Key Vault |
| WAF | Cloud Armor | AWS WAF | Azure WAF (Front Door, Application Gateway) |
| Model APIs in-account | Vertex AI | Bedrock | Foundry |

Principles:

- **Private networking for data.** Databases and caches have no public IP. Services reach them through a VPC connector or private service access.
- **Managed databases.** Use a managed Postgres (Cloud SQL, RDS, Azure Database for PostgreSQL, Neon, Supabase). Backups, point-in-time recovery, and failover are not things you want to build. Check the provider supports pgvector.
- **Secrets from a secret manager**, mounted as environment variables, with each service's identity granted access only to its own secrets.
- **Service identities.** Each service runs as its own service account with least-privilege IAM. The worker can write to the bucket; the API cannot.
- **Egress control.** If tools make outbound requests, consider routing through a proxy with an allow-list, which also helps against injection-driven exfiltration.

## Configuration per environment

Same image, different configuration:

| Setting | Staging | Production |
|---|---|---|
| Database | `relay-staging` | `relay-prod` |
| Model API key | Staging key, $50/day cap | Prod key, monitored |
| Models | Same as prod (test what you ship) | Pinned IDs |
| Min instances | 0 | 2 |
| Refund tool | Writes to sandbox payment provider | Live |
| Log level | Debug | Info |

## Infrastructure as code

Click-ops does not survive the second environment. Describe infrastructure in code (Terraform/OpenTofu, Pulumi, or the platform's own config files) and apply it from CI. Then staging and production differ only in variables, and every change is reviewed. For a course project, a short shell script with `gcloud run deploy` flags checked into the repo is an acceptable start. Treat servers and containers as **immutable**: replace them with new versions rather than patching them in place.

## Cost management

For API-calling apps, the cloud bill is usually small compared with the model bill. Still:

- Set **budgets and alerts** on the cloud account and on every model provider account, from day one. If you self-host models, the GPU bill replaces the token bill: a GPU billed by the hour costs the same at 3 a.m. with no traffic, so scale GPU pools down or to zero when idle.
- Scale to zero for staging and preview environments.
- Right-size the database: it is often the largest fixed cost.
- Watch egress charges if you move large files.
- Track **cost per conversation** as a product metric, combining model tokens, infrastructure, and third-party APIs.

Free tiers are enough for this course: Cloud Run, [Google Cloud free tier](https://cloud.google.com/free), [AWS free tier](https://aws.amazon.com/free/), [Render free instances](https://render.com/docs/free), [Neon](https://neon.com/) and [Supabase](https://supabase.com/docs/guides/ai) free Postgres with pgvector.

## Reliability basics

- **Run at least two instances** for anything users depend on, across zones if the platform allows.
- **Graceful shutdown**: when an instance is told to stop (SIGTERM), stop accepting new requests and let in-flight streams finish within the grace period. Configure the platform's termination grace period longer than your typical stream.
- **Timeouts everywhere**: platform request timeout > your agent's overall timeout > per-tool timeouts > model call timeout. Mismatched timeouts cause confusing failures (the platform kills the request while your code thinks it has time).

```viz
caption: Nest timeouts so the inner one always fires first. Then your code, not the platform, decides what the user sees.
<div class="vz-bars"><span>platform request</span><span class="bar sk"><i class="sk w" style="--w:100%"></i></span><b>300 s</b><span>agent turn</span><span class="bar sk"><i class="sk c" style="--w:80%"></i></span><b>240 s</b><span>one model call</span><span class="bar sk"><i class="sk c" style="--w:30%"></i></span><b>90 s</b><span>one tool call</span><span class="bar sk"><i class="sk c" style="--w:10%"></i></span><b>30 s</b></div>
<p>example values; keep each inner limit well below the one outside it</p>
<div class="vz-src">300 s is Cloud Run's default request timeout, which can be raised to 60 minutes: <a href="https://docs.cloud.google.com/run/docs/configuring/request-timeout">Cloud Run docs</a>. Other values are illustrative.</div>
```
- **Backups tested by restoring them.**

## Design review questions

> [!interview] How many instances do you need at peak, and how did you calculate it?

> [!interview] What happens to in-flight streaming responses during a deploy?

> [!interview] Which service can read which secret? Show me the IAM bindings.

> [!interview] What is the monthly cost at today's traffic and at 10x, split into model, compute, database, and other?

## Further reading

- [Cloud Run documentation](https://cloud.google.com/run/docs) and its [concurrency guide](https://cloud.google.com/run/docs/configuring/concurrency).
- [Fly.io docs](https://fly.io/docs/), a simple alternative with a generous developer experience.
- [Kubernetes autoscaling concepts](https://kubernetes.io/docs/concepts/workloads/autoscaling/), when you outgrow serverless.
- [AWS Well-Architected Generative AI Lens](https://docs.aws.amazon.com/wellarchitected/latest/generative-ai-lens/generative-ai-lens.html), a checklist-style review of AI workloads.
- [Azure AI architecture guidance](https://learn.microsoft.com/en-us/azure/architecture/ai-ml/) and [Google Cloud AI/ML architecture](https://cloud.google.com/architecture/ai-ml).

```quiz
[
  {"q": "Your CPU-based autoscaler never adds instances, yet users see queueing. Why?", "options": ["The autoscaler is broken", "LLM requests are I/O-bound; CPU stays low while concurrency is saturated", "Too many instances", "The model is slow"], "answer": 1, "why": "Waiting on remote APIs uses little CPU. Scale on concurrent requests or queue depth instead."},
  {"q": "40 chats per second each hold a connection for 10 seconds. How many concurrent requests is that?", "options": ["4", "40", "400", "4,000"], "answer": 2, "why": "Little's law: concurrency = arrival rate × duration = 40 × 10 = 400."},
  {"q": "Why set minimum instances to 1 or 2 on a user-facing serverless service?", "options": ["Required by the platform", "To avoid cold-start delays and keep at least one warm, available instance", "To reduce cost", "For logging"], "answer": 1, "why": "Cold starts add seconds to the first request. A small always-on floor is cheap insurance."},
  {"q": "What should the relationship between timeouts be?", "options": ["All equal", "Platform request timeout greater than agent timeout greater than tool and model call timeouts", "Model timeout largest", "No timeouts on streaming"], "answer": 1, "why": "Inner operations must time out before outer ones, so your code handles the failure instead of being killed mid-flight."}
]
```
