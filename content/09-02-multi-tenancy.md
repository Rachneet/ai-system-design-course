---
id: w9-tenancy
week: 9
kind: lesson
title: Multi-tenancy for AI systems
short: Multi-tenancy for AI
minutes: 55
summary: One AI platform serving many customers or teams without one ever seeing another's data, spending another's budget, or slowing another down. Isolation at every layer, the leak paths that are specific to AI (retrieval, memory, caches, adapters, traces), silo against pool, and the numbers behind the choice.
---

## Why AI systems leak across tenants in new ways

A **tenant** is a customer (or an internal team) whose data, configuration and spend must stay separate from everyone else's, on infrastructure you share for cost and speed. Ordinary SaaS has learned to isolate tenants in its databases and APIs. An AI system adds components that were never built with tenants in mind, and the model itself is a powerful leak amplifier: give it a chunk from the wrong tenant and it will summarise it fluently and confidently.

AWS's [SaaS tenant isolation whitepaper](https://docs.aws.amazon.com/whitepapers/latest/saas-tenant-isolation-strategies/saas-tenant-isolation-strategies.html) describes crossing a tenant boundary as "a significant and potentially un-recoverable event for a SaaS business". OWASP's [LLM08:2025 Vector and Embedding Weaknesses](https://genai.owasp.org/llmrisk/llm082025-vector-and-embedding-weaknesses/) names the AI form directly: in multi-tenant setups that share a vector database, one group's embeddings can be retrieved for another group's queries, and the mitigation is "permission-aware vector and embedding stores" with "strict logical and access partitioning".

[Week 2](#w2-ingestion) covered access control inside one tenant: ACLs on chunks, filtered in the query. This lesson is about the boundary between tenants, which is harder, because it must hold at every layer at once.

```viz
caption: Every layer of an AI system is a place where one tenant's data can reach another. Isolation is only as strong as the weakest layer.
<div class="vz-row"><span class="ch sk c">identity</span><span class="arr sk"></span><span class="ch sk b">tenant from request body</span><span class="arr sk"></span><span class="ch sk g">tenant from verified token</span></div>
<div class="vz-row"><span class="ch sk c">rows</span><span class="arr sk"></span><span class="ch sk b">one forgotten WHERE</span><span class="arr sk"></span><span class="ch sk g">RLS, non-owner role</span></div>
<div class="vz-row"><span class="ch sk c">vector index</span><span class="arr sk"></span><span class="ch sk b">filter after search</span><span class="arr sk"></span><span class="ch sk g">tenant filter in query</span></div>
<div class="vz-row"><span class="ch sk c">memory</span><span class="arr sk"></span><span class="ch sk b">keyed by user only</span><span class="arr sk"></span><span class="ch sk g">keyed by tenant and user</span></div>
<div class="vz-row"><span class="ch sk c">caches</span><span class="arr sk"></span><span class="ch sk b">key is the question</span><span class="arr sk"></span><span class="ch sk g">key has tenant, principals</span></div>
<div class="vz-row"><span class="ch sk c">models, adapters</span><span class="arr sk"></span><span class="ch sk b">trained on pooled data</span><span class="arr sk"></span><span class="ch sk g">adapter per tenant</span></div>
<div class="vz-row"><span class="ch sk c">logs, traces</span><span class="arr sk"></span><span class="ch sk b">anyone reads prompts</span><span class="arr sk"></span><span class="ch sk g">tenant tag, access, retention</span></div>
<div class="vz-row"><span class="ch sk c">keys, budgets</span><span class="arr sk"></span><span class="ch sk b">one shared key</span><span class="arr sk"></span><span class="ch sk g">gateway app per tenant</span></div>
```

> [!rule] The tenant comes from authentication and nowhere else: a verified token claim, resolved on the server. Never from a header, a body field, a URL the client chose, or the model. Every layer below receives it from the request context.

## Silo, pool and bridge

The AWS Well-Architected [SaaS Lens](https://docs.aws.amazon.com/wellarchitected/latest/saas-lens/silo-pool-and-bridge-models.html) names three deployment models, and the vocabulary is now standard:

- **Silo**: "tenants are provided dedicated resources", such as a separate database or a whole stack per tenant, still onboarded and operated through one shared control plane.
- **Pool**: "tenants share resources", for economies of scale, manageability and agility.
- **Bridge**: a mix, because "SaaS businesses aren't always exclusively silo or pool". The Lens notes that a service's regulatory profile and "noisy neighbor attributes" may steer it to silo, while cost and agility tip others to pool.

The choice is made **per layer**, not once for the whole system. A typical AI platform pools compute and the model gateway, pools the database with row-level security for most tenants, and silos the database, the vector index or the provider account only for the tenants whose contracts or regulators demand it.

### What silo costs

The model bill is the same in every model: you pay per token either way. What changes is the fixed cost of infrastructure that runs whether a tenant is busy or not. Here is a worked example for 200 tenants. The prices are assumptions for illustration; put your own cloud's numbers in.

| Assumption | Value |
|---|---|
| Tenants | 20 large (50,000 conversations a month), 180 small (2,000 a month) |
| Model cost per conversation, after caching | $0.05 |
| Smallest always-on silo (database, API, worker) | $150 a month per tenant |
| Shared pooled stack sized for the combined peak | $6,000 a month |

> [!numbers] Model spend is 20 × 50,000 × $0.05 + 180 × 2,000 × $0.05 = $50,000 + $18,000 = **$68,000** a month in every design. Infrastructure: **silo** 200 × $150 = **$30,000**; **pool** **$6,000**; **bridge** (silo only the 20 large tenants, pool the rest on a $5,500 stack) 20 × $150 + $5,500 = **$8,500**. For a small tenant, a silo costs $150 against $100 of model spend: the platform costs more than the AI. Pooled, the same tenant's share of $6,000 is about $30.

```viz
caption: With these assumptions, siloing every tenant multiplies infrastructure cost by five, almost all of it for the long tail of small tenants. Bridge pays for isolation only where it is demanded.
<div class="vz-bars"><span>silo: all 200</span><span class="bar sk"><i class="sk w" style="--w:100%"></i></span><b>$30,000</b><span>bridge: silo 20</span><span class="bar sk"><i class="sk w" style="--w:28%"></i></span><b>$8,500</b><span>pool: all 200</span><span class="bar sk"><i class="sk g" style="--w:20%"></i></span><b>$6,000</b></div>
<div class="vz-cols" style="--k:3">
  <div class="vz-panel sk"><h5>Silo</h5><p>strongest boundary, per-tenant upgrades and regions, no noisy neighbours</p></div>
  <div class="vz-panel sk"><h5>Bridge</h5><p>silo the regulated and the huge; pool the long tail</p></div>
  <div class="vz-panel sk g"><h5>Pool</h5><p>cheapest; isolation is your code and your database's policies</p></div>
</div>
<div class="vz-src">Infrastructure cost per month, computed from the assumptions in the table above (not vendor prices). Model terms from the AWS <a href="https://docs.aws.amazon.com/wellarchitected/latest/saas-lens/silo-pool-and-bridge-models.html">SaaS Lens</a>.</div>
```

Silo also costs operations: 200 databases to migrate, back up and monitor, and 200 places a schema change can fail. Pool costs engineering discipline: every layer below must enforce the boundary, because nothing physical does.

## Layer by layer

### Data: row-level security

In a pooled database, the cheapest strong control is Postgres **row-level security** (RLS): the database adds a tenant condition to every query on a table, so a query that forgets its `WHERE tenant_id = ...` returns nothing instead of everyone's rows.

```sql
ALTER TABLE orders ADD COLUMN tenant_id text NOT NULL REFERENCES tenants(id);
ALTER TABLE orders ENABLE ROW LEVEL SECURITY;
ALTER TABLE orders FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON orders
  USING (tenant_id = current_setting('app.tenant_id', true));

-- per request, inside a transaction:
SELECT set_config('app.tenant_id', 'summit', true);  -- this transaction only
```

A policy with only `USING` also applies the same condition as a check on inserted and updated rows, so a request for one tenant cannot write a row tagged with another. `current_setting(..., true)` returns NULL when the setting is missing, so a request that never set a tenant sees no rows at all: the failure is closed. The [Postgres RLS documentation](https://www.postgresql.org/docs/current/ddl-rowsecurity.html) and the [function reference](https://www.postgresql.org/docs/current/functions-admin.html) are short and worth reading whole. Five pitfalls catch almost every team:

1. **Superusers and owners bypass RLS.** "Superusers and roles with the BYPASSRLS attribute always bypass the row security system", and table owners do too unless you `FORCE ROW LEVEL SECURITY`. If your app connects as the role that ran the migrations, or as `postgres`, your policies do nothing. Run the app as a separate role with neither attribute, and check it at startup.
2. **`SET LOCAL` outside a transaction does nothing.** Postgres [documents](https://www.postgresql.org/docs/current/sql-set.html) that it "emits a warning and otherwise has no effect". Many pools run in autocommit mode, Relay's included, so set the tenant inside an explicit transaction with `set_config(..., true)`.
3. **Pooled connections remember session settings.** A session-level `SET app.tenant_id` survives when the connection goes back to the pool, and the next request, for another tenant, inherits it. Transaction-local settings avoid this; so does a pool reset hook ([psycopg's pool](https://www.psycopg.org/psycopg3/docs/advanced/pool.html) calls a `reset` callback before reuse).
4. **Unique keys and foreign keys bypass RLS.** The documentation warns that integrity checks "always bypass row security" and can become "covert channel" leaks. If order IDs are unique across all tenants, a tenant that tries to insert order 1042 learns that someone else has one. Make keys composite with `tenant_id`, or use random IDs.
5. **Views run as their owner.** By default a view applies the RLS policies of the view's owner, so a view created by the table owner shows every tenant. Create views `WITH (security_invoker = true)` ([CREATE VIEW](https://www.postgresql.org/docs/current/sql-createview.html)).

> [!warn] Test RLS as the application's role, not as a superuser. A test suite that connects as `postgres` passes whether or not your policies work, because superusers bypass them all.

### Retrieval: filtering a shared vector index

Week 2's rule still holds: filter inside the query, never after. Multi-tenancy adds a recall trap. Approximate indexes such as HNSW find the nearest candidates first and apply the filter afterwards. The [pgvector README](https://github.com/pgvector/pgvector) gives the arithmetic: "If a condition matches 10% of rows, with HNSW and the default `hnsw.ef_search` of 40, only 4 rows will match on average." A tenant filter, whether written in the query or added by an RLS policy, is such a condition, and it gets more selective with every tenant you add.

```viz
caption: A shared HNSW index returns about 40 candidates before filtering. With many equal tenants, the filter leaves almost nothing, and retrieval silently returns empty results for small tenants.
<div class="vz-cols">
  <div class="vz-panel sk"><h5>2 tenants: half survive</h5>
    <div class="cells" style="--n:10"><i class="sk g"></i><i class="sk x"></i><i class="sk g"></i><i class="sk g"></i><i class="sk x"></i><i class="sk x"></i><i class="sk g"></i><i class="sk x"></i><i class="sk g"></i><i class="sk x"></i><i class="sk x"></i><i class="sk g"></i><i class="sk g"></i><i class="sk x"></i><i class="sk g"></i><i class="sk x"></i><i class="sk g"></i><i class="sk x"></i><i class="sk g"></i><i class="sk x"></i></div>
    <p class="big g">about 20 of 40</p>
  </div>
  <div class="vz-panel sk b"><h5>100 tenants: almost none</h5>
    <div class="cells" style="--n:10"><i class="sk x"></i><i class="sk x"></i><i class="sk x"></i><i class="sk x"></i><i class="sk x"></i><i class="sk x"></i><i class="sk x"></i><i class="sk x"></i><i class="sk x"></i><i class="sk x"></i><i class="sk x"></i><i class="sk x"></i><i class="sk x"></i><i class="sk x"></i><i class="sk x"></i><i class="sk x"></i><i class="sk x"></i><i class="sk x"></i><i class="sk x"></i><i class="sk x"></i></div>
    <p class="big b">about 0.4 of 40</p>
  </div>
</div>
<div class="vz-src">Expected survivors = candidates x share of rows matching the filter, following the example in the <a href="https://github.com/pgvector/pgvector">pgvector README</a> (default <code>hnsw.ef_search</code> of 40).</div>
```

The leak is prevented either way; what breaks is quality, silently, for exactly the small tenants nobody watches. Fixes, from cheapest:

- **Iterative index scans** (pgvector 0.8.0 and later): `SET LOCAL hnsw.iterative_scan = relaxed_order` keeps scanning until enough rows pass the filter, up to `hnsw.max_scan_tuples` (20,000 by default).
- **Partial indexes or partitions.** pgvector suggests partial indexes for a few distinct filter values and partitioning for many; a list partition per large tenant gives each its own index.
- **A namespace or collection per tenant** in a dedicated vector database, which most of them support, at the cost of more objects to manage.

Whatever you pick, run your retrieval eval **per tenant**. An average across tenants hides the one that gets nothing back.

### Conversation memory

Memory is a database table with a model in front of it, and it leaks the same way: a memory lookup keyed only by user ID breaks if user IDs repeat across tenants, and any **learned** artefact built from many conversations (auto-generated FAQs, few-shot example banks, "lessons learned" stores) is pooled data in disguise. Key every memory by tenant and user, put it under the same RLS as everything else, and never build a shared learned store from more than one tenant's conversations unless every one of them has agreed to it.

### Caches

Two caches matter, and they are scoped very differently.

**Your response and retrieval caches** are yours to key. A semantic cache keyed on the question will answer tenant B with tenant A's answer, grounded in A's documents. The key must contain the tenant, the caller's principals (or a hash of them), and the version of the knowledge base, as [Week 5's caching lesson](#w5-scaling) set out for one tenant.

**Provider prompt caches** are scoped by the provider. Anthropic documents that caches "are isolated between organizations" and, on the Claude API, "per workspace within an organization", while on Bedrock and Google Cloud isolation is per organization ([prompt caching docs](https://platform.claude.com/docs/en/build-with-claude/prompt-caching)). OpenAI states that "caches are not shared across organizations" ([prompt caching guide](https://developers.openai.com/api/docs/guides/prompt-caching)). So if every tenant's traffic goes through your one provider account, every tenant shares your cache scope.

That is usually acceptable, for two reasons: a cache hit requires a byte-identical prefix, and the output is the same as without caching. The residual risk is timing. [Gu et al. (ICML 2025)](https://arxiv.org/abs/2502.07776) showed that cached prompts return measurably faster, which can reveal whether someone else recently sent the same prefix, and in 2025 they detected cache sharing across users at seven API providers. Put tenant-specific content (the tenant's own instructions, its documents) after the shared prefix and inside its own cache breakpoints, and for tenants whose contracts forbid shared infrastructure, use a separate provider workspace or project.

> [!numbers] Separate cache scopes cost money. With a 6,000-token shared prefix at Opus 5.5 list prices, a cache write costs 6,000 × $5 / 1M = **$0.03** and a read costs 6,000 × $0.20 / 1M = **$0.0012**: 25 times less. A small tenant in its own workspace, sending a request less often than the 5-minute cache lifetime, pays the write almost every time.

### Fine-tuned models and adapters

A model fine-tuned on several tenants' data can repeat that data: [Carlini et al.](https://arxiv.org/abs/2012.07805) extracted hundreds of verbatim training sequences, including personal information, from GPT-2, and found larger models more vulnerable. Fine-tune on one tenant's data for that tenant only. Serving engines make this affordable: vLLM serves many LoRA adapters on one base model, and a request picks its adapter "as if it were any other model via the `model` request parameter" ([vLLM LoRA docs](https://docs.vllm.ai/en/latest/features/lora.html)).

That convenience is the leak: if the client chooses the model name, a client can choose another tenant's adapter. Enforce the mapping from tenant to adapter in the gateway, never in the client. In Switchboard, that is the per-app `allowed_models` list, checked on every request and on fallbacks too. The same vLLM page warns that loading adapters at runtime "should not be used in production unless it is an isolated, fully trusted environment".

[Fine-tuning and LoRA](#uth-lora) trains an adapter per tenant from scratch and shows one tenant's adapter failing on the other's data: the adapter carries its tenant's behaviour. For LoRA in PyTorch, see appendix E of Raschka's [*Build a Large Language Model (From Scratch)*](https://github.com/rasbt/LLMs-from-scratch/tree/main/appendix-E).

### Logs and traces

Traces hold prompts, retrieved chunks and answers: everything the isolation above protects. Tag every span and log line with the tenant, restrict who can query each tenant's traces, and apply each tenant's retention and deletion rules to them. Relay records content in traces only when you opt in, and redacts it; Switchboard stores request bodies only when an app sets `log_bodies`, always redacted, with a per-app `retention_days`.

### Model keys, budgets and noisy neighbours

One provider key shared by all tenants means one rate limit shared by all tenants. When one tenant starts a bulk job, everyone else gets 429s. This is the **noisy neighbour** problem, and in AI systems it arrives in tokens per minute, not CPU.

Give each tenant its own gateway identity. In Switchboard, an **app** is the unit: each has its own keys, `allowed_models`, `rpm` and `tpm` limits, and an optional monthly budget, nested under a team and an organisation, each with their own budgets. A tenant that exhausts its budget gets a 429 with `x-switchboard-limit: budget:app`, and nobody else notices.

The tool gateway needs the same boundary. Checkpoint can bind an agent to one tenant: a bound agent that presents a user token from another tenant is refused before any policy runs, approvers bound to a tenant see only that tenant's queue, and the signed assertion each MCP server receives carries a `tenant` claim the server uses to scope its data. The check is built into the gateway rather than written as a policy, because policies are edited often and one typo would open every tenant.

> [!numbers] Say your provider allows your organisation 2,000,000 tokens per minute and you serve 50 tenants. One tenant's backfill takes 1,800,000 TPM; the other 49 share 200,000, about 4,100 each. Cap every tenant at 25% (500,000 TPM): the backfill slows down, and the other 49 share 1,500,000, about **30,600 each**, 7.5 times more.

Caps are the blunt tool. Fairer schemes give each tenant a guaranteed share and let it borrow unused capacity, and put bulk work on a separate, lower-priority queue (or a provider's batch API) so it never competes with live chats.

### Evals and red-team suites per tenant

Each tenant has its own prompt, knowledge base, tools and policies, so each needs its own eval suite and its own pass threshold, run on every change that touches it. Add a **cross-tenant red-team suite** to every tenant's gate, as a must-never category alongside the cross-customer cases from Week 3:

- prompt injections that ask for another tenant's records by ID, name or email;
- requests for another tenant's policies or documents ("what is Summit's return window?");
- direct API calls with another tenant's session or resource IDs;
- tokens with a missing, unknown or tampered tenant claim.

One failure in this category blocks the release, whatever the other scores are.

## Failure modes

| Failure | How it happens | What catches it |
|---|---|---|
| RLS silently off | The app connects as the table owner or a superuser | A startup check that the role has neither `rolsuper` nor `rolbypassrls`; isolation tests run as the app role |
| Tenant bleed between requests | A session-level `SET` survives on a pooled connection | Transaction-local `set_config`; a test that alternates tenants on one connection |
| Empty retrieval for small tenants | HNSW post-filtering with a selective tenant filter | Per-tenant retrieval evals; iterative scans or per-tenant partitions |
| Cross-tenant cache hit | Cache key without tenant or principals | Key review; a test that asks the same question as two tenants |
| Adapter swap | Client picks the model name | Gateway allow-list per tenant |
| Noisy neighbour | Shared key and limits | Per-tenant app keys, limits and budgets; bulk work on its own queue |
| Covert channel | Global unique IDs | Composite or random keys |

## Design review questions

> [!interview] Show me where the tenant ID enters a request, and every place it is read afterwards. Is there any path where it comes from the client?

> [!interview] Which database role does the application connect as? Prove that it cannot bypass row-level security.

> [!interview] What is retrieval recall for your smallest tenant, and how do you know?

> [!interview] List every cache in the system and its key. Which ones include the tenant?

> [!interview] One tenant starts a bulk job at 3 a.m. What happens to the others' latency and error rate, and which limit stops it?

> [!interview] Which layers are siloed for your largest regulated customer, and what would it cost to silo them for everyone?

## Further reading

- AWS Well-Architected [SaaS Lens: silo, pool and bridge](https://docs.aws.amazon.com/wellarchitected/latest/saas-lens/silo-pool-and-bridge-models.html), and the older but still useful [SaaS tenant isolation strategies](https://docs.aws.amazon.com/whitepapers/latest/saas-tenant-isolation-strategies/saas-tenant-isolation-strategies.html) whitepaper.
- [Postgres row security policies](https://www.postgresql.org/docs/current/ddl-rowsecurity.html), short and precise.
- [pgvector: filtering and iterative index scans](https://github.com/pgvector/pgvector).
- [OWASP LLM08:2025 Vector and Embedding Weaknesses](https://genai.owasp.org/llmrisk/llm082025-vector-and-embedding-weaknesses/).
- [Auditing Prompt Caching in Language Model APIs](https://arxiv.org/abs/2502.07776), Gu et al., ICML 2025.
- `platform/switchboard` in this course's repository: per-app keys, limits and budgets under teams and organisations.

```quiz
[
  {"q": "Your RLS policies are correct, but the isolation test shows tenant A reading tenant B's rows. What is the most likely cause?", "options": ["The policy uses USING instead of WITH CHECK", "The application connects as the table owner or a superuser, which bypass RLS", "pgvector disables RLS", "RLS only works on views"], "answer": 1, "why": "Superusers and BYPASSRLS roles always bypass row security, and owners do unless FORCE ROW LEVEL SECURITY is set. Run the app as a separate role and test as that role."},
  {"q": "Relay's connection pool runs in autocommit mode. Each request runs SET LOCAL app.tenant_id = 'summit' and then its queries. What happens?", "options": ["It works", "SET LOCAL outside a transaction has no effect, so the queries run with no tenant set", "Postgres raises an error and the request fails", "The setting applies to the whole session"], "answer": 1, "why": "Postgres emits a warning and ignores it. Open a transaction and use set_config('app.tenant_id', ..., true) inside it."},
  {"q": "A shared HNSW index returns about 40 candidates, and you have 100 tenants of equal size. On average, how many candidates survive the tenant filter?", "options": ["40", "20", "4", "Fewer than 1"], "answer": 3, "why": "40 x 1% = 0.4. Retrieval quietly returns nothing. Use iterative scans, partitions or per-tenant collections, and measure recall per tenant."},
  {"q": "Which cache key is safe for a semantic response cache on a multi-tenant support bot?", "options": ["The normalised question", "Question plus model name", "Tenant, caller's principals and knowledge-base version, plus the question", "The user's email"], "answer": 2, "why": "Without the tenant and principals, one tenant's answer, grounded in its documents, is served to another. The KB version stops stale answers after an update."},
  {"q": "A vLLM server hosts one LoRA adapter per tenant, selected by the model name in the request. What stops tenant A using tenant B's adapter?", "options": ["Nothing is needed; adapter names are secret", "The gateway maps each tenant's key to its allowed models and rejects others", "The model refuses", "Rate limits"], "answer": 1, "why": "The client controls the model field, so the mapping must be enforced server-side, for example with Switchboard's per-app allowed_models."},
  {"q": "With assumed costs of $150 a month per silo and a $6,000 pooled stack, what does siloing all 200 tenants cost in infrastructure, compared with pooling?", "options": ["The same", "$30,000 against $6,000", "$6,000 against $30,000", "$1,200 against $6,000"], "answer": 1, "why": "200 x $150 = $30,000. The model bill is the same either way; the fixed cost per silo is what multiplies, mostly for small tenants."},
  {"q": "One tenant's batch job uses 90% of your organisation's tokens per minute. What is the most direct fix?", "options": ["A bigger model", "Per-tenant gateway keys with TPM limits and budgets, and bulk work on its own lower-priority queue", "Turn off prompt caching", "Ask the tenant to stop"], "answer": 1, "why": "Noisy neighbours are a shared-limit problem. Per-tenant limits contain them; a separate queue keeps bulk work away from live traffic."}
]
```
