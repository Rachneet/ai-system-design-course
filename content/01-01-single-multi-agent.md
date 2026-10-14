---
id: w1-agents
week: 1
kind: lesson
title: Single-agent and multi-agent systems
short: Single vs multi-agent
minutes: 45
summary: When you need an agent at all, the workflow patterns that cover most products, and the specific conditions under which splitting work across several agents pays for its cost.
---

## Start with the least autonomy that works

"Agent" is used loosely. For design purposes, separate two things:

- A **workflow** is a fixed path through LLM calls and code that you wrote. The model fills in steps, but your code decides the order.
- An **agent** is a loop where the model decides the next step: which tool to call, whether to call another, when it is done.

Autonomy is a cost. Every decision you hand to the model adds latency, spend, and a new way to fail. So the first design question is never "which agent framework?" It is "how much of this path can I fix in code?"

```mermaid
flowchart LR
  A[Single LLM call] --> B[Workflow:<br/>fixed steps] --> C[Single agent:<br/>model picks tools] --> D[Multi-agent:<br/>models delegate to models]
  style A fill:transparent
```

Move right only when the step to the left cannot do the job. A good test from practice: if you can draw the flowchart of the task before you see the input, write a workflow. If the path depends on what the model discovers along the way (debugging, research, open-ended support conversations), you need an agent.

> [!rule] Pick the simplest tier that meets the requirement, then earn each step up with an eval result that shows the simpler tier failing.

## The five workflow patterns

Most production "agents" are really one of these patterns, sometimes nested. Anthropic's [Building effective agents](https://www.anthropic.com/engineering/building-effective-agents) named them, and the names have stuck.

| Pattern | Shape | Use when | Relay example |
|---|---|---|---|
| Prompt chaining | A → B → C, with code checks between steps | The task splits into fixed subtasks and each step is easier than the whole | Draft reply → check tone and policy → send |
| Routing | Classify, then send to a specialised handler | Inputs fall into distinct categories that need different prompts, tools, or models | Order status → cheap model with order tools; legal complaint → human queue |
| Parallelization | Run N calls at once, then combine | Independent subtasks, or you want several opinions (voting) | Check a reply for PII, policy, and tone simultaneously |
| Orchestrator–workers | One model plans subtasks, workers execute, orchestrator merges | Subtasks are not known in advance | "Compare return policies across our five brands" |
| Evaluator–optimizer | Generate, critique, revise in a loop | Clear quality criteria and iterating measurably helps | Rewrite a refund denial until it passes the policy rubric |

Routing deserves special attention because it is the cheapest big win. A classifier on a small model costs a fraction of a cent and lets you send 70% of traffic (order status, store hours) to a small model with two tools, and only the hard 30% to a large model with the full toolset.

> [!numbers] Relay gets 50,000 conversations a day, averaging 4 model calls of 8,000 input and 400 output tokens. All on Opus 5.5 ($4 / $20 per million): 50,000 × 4 × (8,000 × 4 + 400 × 20) / 1e6 = **$8,000/day**. Route 70% to Haiku 5.5 ($0.10 / $0.50) with a smaller 3,000-token prompt: 35,000 × 4 × (3,000 × 0.10 + 400 × 0.50) / 1e6 = $70, plus 15,000 × 4 × 40,000 / 1e6 = $2,400 for the rest. About **$2,470/day**, a 69% saving, before caching.

## The single-agent loop

When you do need an agent, start with one. A single agent is a model, a system prompt, a set of tools, and a loop:

```python
def run_agent(messages: list, tools: list, max_steps: int = 10) -> list:
    for step in range(max_steps):
        resp = client.messages.create(
            model=MODEL, max_tokens=4096, system=SYSTEM, tools=tools, messages=messages
        )
        messages.append({"role": "assistant", "content": resp.content})
        if resp.stop_reason == "end_turn":
            return messages  # model produced a final answer
        if resp.stop_reason in ("max_tokens", "refusal"):
            raise AgentStopped(resp.stop_reason, messages)  # truncated or declined: do not run tools
        if resp.stop_reason != "tool_use":
            return messages  # e.g. stop_sequence
        results = []
        for block in resp.content:
            if block.type == "tool_use":
                results.append(execute_tool(block))  # returns a tool_result dict
        messages.append({"role": "user", "content": results})  # all results in ONE message
    raise StepLimitExceeded(messages)
```

Everything else in this course hangs off this loop: what goes into `SYSTEM` and `messages` (context engineering), what persists between runs (memory), what `execute_tool` is allowed to do (security), how you know it worked (evals), and how you watch it run (tracing).

Design decisions inside the loop that matter in production:

- **Check why the model stopped.** `end_turn` means done and `tool_use` means run tools. `max_tokens` means the reply was cut off, and any tool call in it may be incomplete. `refusal` means the model declined. Handle each explicitly rather than treating everything that is not a tool call as a final answer.
- **Step limit.** Always cap steps. An agent that loops forever is a billing incident. Return a graceful message, log the trace, and alert if the rate of hitting the cap rises.
- **Parallel tool calls.** Models can request several tools at once. Run them concurrently and return all results in one message. Splitting results across messages quietly teaches the model to stop parallelising.
- **Tool errors are data.** If a tool fails, return a `tool_result` with `is_error: true` and a message the model can act on ("order 1042 not found; ask the customer to confirm the number"). Do not crash the loop and do not hide the error.
- **Timeouts per tool and per run.** A slow inventory API should not hold a user for 90 seconds.

## Designing tools is designing the agent

The tool set is the agent's interface to the world, and it shapes behaviour more than the prompt does. Good tools:

- **Match how a person would do the task**, not how your microservices are split. `get_order_summary(order_id)` beats making the model call `get_order`, `get_shipment`, and `get_payment` and join them.
- **Return what the model needs, compactly.** A 4,000-token JSON blob with 80 fields wastes context and attention. Return the ten fields that matter, as readable text or small JSON.
- **Have unambiguous names and descriptions.** Descriptions are prompts. Say when to use the tool, when not to, and what the arguments mean, with an example.
- **Fail helpfully.** Error strings tell the model what to try next.
- **Separate read tools from write tools.** This makes permission tiers, approvals, and evals easier (Week 3).

Anthropic's [Writing effective tools for agents](https://www.anthropic.com/engineering/writing-tools-for-agents) is the best free reference on this.

## When multiple agents pay off

A multi-agent system has several model contexts that communicate: an orchestrator that spawns sub-agents, a pipeline of specialists, or peers handing off a conversation. It sounds more capable. Often it is just more expensive and harder to debug.

Multiple agents help in three situations:

1. **Context isolation.** A sub-agent can read 200,000 tokens of search results and return a 1,000-token summary. The orchestrator's context stays clean. This is the main reason research agents use sub-agents.
2. **Breadth-first parallel work.** When a task splits into independent threads (search five sources, analyse ten files), parallel sub-agents finish in the wall-clock time of the slowest one.
3. **Different permissions or models per role.** A sub-agent that reads untrusted web content can run with no write tools at all. That is a security boundary, not just an organisational one.

They hurt when:

- **Subtasks share a lot of state.** Agents each make decisions with partial context, and their outputs conflict. Cognition's [Don't build multi-agents](https://cognition.ai/blog/dont-build-multi-agents) makes this argument well: for tightly coupled work like coding, one agent with full context beats several with fragments.
- **Latency matters.** Each hop adds a full model round trip.
- **Cost matters.** Anthropic's [multi-agent research system](https://www.anthropic.com/engineering/multi-agent-research-system) write-up reports that single agents use about 4 times the tokens of a chat interaction, and multi-agent systems about 15 times. It was worth it for open-ended research. It would not be worth it for order status.

> [!rule] Split into multiple agents along boundaries where little information needs to cross: independent subtasks, different trust levels, or a context that would otherwise overflow.

### Common multi-agent topologies

```mermaid
flowchart TB
  subgraph OW[Orchestrator-workers]
    O[Orchestrator] --> W1[Worker: search KB]
    O --> W2[Worker: search tickets]
    O --> W3[Worker: read order history]
    W1 & W2 & W3 --> O
  end
  subgraph HO[Handoff]
    T[Triage agent] -->|transfer| S[Billing agent]
    T -->|transfer| R[Returns agent]
  end
```

- **Orchestrator–workers (supervisor).** The orchestrator plans, spawns workers with narrow instructions, and synthesises. Workers return condensed results, not raw transcripts. Most robust general shape.
- **Handoff (swarm).** One agent owns the conversation at a time and transfers control to another, passing a summary. Good for support flows with clear departments. The risk is lost context at each transfer.
- **Pipeline.** Fixed sequence of specialised agents. This is really a workflow with agentic steps, and it is often the right answer.

### Writing the delegation

Most multi-agent failures are bad delegation, not bad models. When the orchestrator spawns a worker, the task description must include: the objective, the output format, which tools to use, what is out of scope, and how much effort to spend. "Research return policies" produces sprawling duplicate work. "Find the return window and restocking fee for tents in the 2026 returns policy; return a two-line answer with the document ID; do not search order data" does not.

## Choosing a framework (or not)

You can build everything in this course with the raw SDK and about 300 lines of Python. Frameworks such as LangGraph, Pydantic AI, the OpenAI Agents SDK, Google ADK, and the Claude Agent SDK add state graphs, checkpointing, built-in tools, and integrations. They are worth it when you need durable execution or complex branching. They cost you an abstraction layer between you and the actual prompts.

The labs use the raw SDK so that you see every token. After the course, pick a framework knowingly. The [12-factor agents](https://github.com/humanlayer/12-factor-agents) essay makes a strong case for owning your prompts, context, and control flow regardless of what you choose.

## Design review questions

> [!interview] Why is this an agent rather than a workflow? Show me an input where a fixed path would fail.

> [!interview] What stops the loop? What happens when it hits the step limit, and who finds out?

> [!interview] If you use several agents, what information crosses between them, and what is lost at each boundary?

> [!interview] What does one conversation cost at p50 and p95, and what is the plan if traffic triples?

## Further reading

- [Building effective agents](https://www.anthropic.com/engineering/building-effective-agents), Anthropic. The workflow patterns in one page.
- [How we built our multi-agent research system](https://www.anthropic.com/engineering/multi-agent-research-system), Anthropic. Real numbers on when multi-agent works.
- [Don't build multi-agents](https://cognition.ai/blog/dont-build-multi-agents), Cognition. The counter-argument.
- [LLM Powered Autonomous Agents](https://lilianweng.github.io/posts/2023-06-23-agent/), Lilian Weng. Planning, memory, and tool use in one survey.
- [ReAct: Synergizing Reasoning and Acting](https://arxiv.org/abs/2210.03629), the paper behind the think-act-observe loop.
- [AI Agents for Beginners](https://github.com/microsoft/ai-agents-for-beginners), Microsoft. Free lessons with code.

```quiz
[
  {"q": "A product team wants an \"agent\" that takes an uploaded invoice, extracts fields, validates totals, and writes a row to the database. What should you build first?", "options": ["A multi-agent system with an extractor and a validator agent", "A single agent with database tools", "A workflow: extraction call with a schema, code validation, then a write", "A fine-tuned model"], "answer": 2, "why": "The path is known before seeing the input. A fixed workflow is cheaper, faster, and easier to test. Add autonomy only where the evals show the workflow failing."},
  {"q": "Which situation most justifies splitting work across sub-agents?", "options": ["Each step needs the full conversation history", "A task needs reading hundreds of thousands of tokens of search results, of which only a summary matters", "You want lower latency on a simple FAQ", "You want to reduce token spend"], "answer": 1, "why": "Context isolation is the strongest reason. Sub-agents absorb large, noisy inputs and pass back condensed results so the orchestrator's context stays focused."},
  {"q": "The model requests three tools in one turn. How should you return the results?", "options": ["Three separate user messages, one per result", "One user message containing all three tool_result blocks", "Only the first result; the model will ask again", "Concatenate them into a text block"], "answer": 1, "why": "Return all results together in one message. Splitting them works but gradually teaches the model to stop calling tools in parallel."},
  {"q": "A tool call fails because the order ID does not exist. What is the best behaviour?", "options": ["Raise an exception and end the run", "Return a tool_result with is_error true and a message the model can act on", "Silently return an empty object", "Retry the same call five times"], "answer": 1, "why": "Errors are information. A clear error result lets the model recover, for example by asking the customer to confirm the order number."},
  {"q": "In the routing example, what produced most of the cost saving?", "options": ["Shorter answers", "Sending the easy majority of traffic to a much cheaper model with a smaller prompt", "Removing tools", "Streaming"], "answer": 1, "why": "70% of traffic moved from $4/$20 to $0.10/$0.50 per million tokens with a smaller prompt. Routing is usually the largest single cost lever in a product with mixed difficulty."}
]
```
