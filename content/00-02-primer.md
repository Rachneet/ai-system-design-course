---
id: primer
week: 0
kind: lesson
title: LLM application primer
short: LLM app primer
minutes: 45
summary: The minimum mental model of LLM APIs you need before Week 1, tokens, context windows, tool calling, embeddings, and where latency and cost come from.
---

Skip this lesson if you can already explain what happens, byte by byte, when your app sends a tool-calling request. Everyone else: this is the vocabulary the rest of the course assumes.

## A model call is a pure function over text

An LLM API call takes a list of messages and returns a new message. The model has no memory between calls. Anything it should "know" about this conversation must be in the request: the system prompt, the earlier turns, the tool definitions, retrieved documents. This is the single most important fact in AI system design, because it means **you own the state**. The model is stateless compute; your system decides what goes into each call.

```viz
caption: The model keeps nothing between calls. Turn 2 works only because your code sends turn 1 again.
<div class="vz-cols">
  <div class="vz-panel sk c"><h5>Call 1</h5>
    <div class="vz-row"><span class="ch sk">system prompt</span><span class="ch sk">tools</span><span class="ch sk c">question 1</span></div>
    <span class="arr d sk c"></span>
    <div class="vz-row"><span class="ch sk m">answer 1</span></div>
  </div>
  <div class="vz-panel sk c"><h5>Call 2</h5>
    <div class="vz-row"><span class="ch sk">system prompt</span><span class="ch sk">tools</span><span class="ch sk m">question 1</span><span class="ch sk m">answer 1</span><span class="ch sk c">question 2</span></div>
    <span class="arr d sk c"></span>
    <div class="vz-row"><span class="ch sk m">answer 2</span></div>
  </div>
</div>
<p>everything the model should know rides in the request; your store keeps it between calls</p>
```

Every provider works this way. The request shapes differ a little, so here is the same call twice: once with Anthropic's Messages API, once with the OpenAI-style Chat Completions format that OpenAI, Google Gemini, local servers and routers all accept.

```python
import os
import anthropic

client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY
MODEL = os.environ.get("RELAY_MODEL", "claude-opus-5-5")

resp = client.messages.create(
    model=MODEL,
    max_tokens=1024,
    system="You are Relay, the support assistant for Northwind Outfitters.",
    messages=[{"role": "user", "content": "What is your return window for tents?"}],
)
print(resp.content[0].text)
print(resp.usage)  # input_tokens, output_tokens, cache_creation_input_tokens, cache_read_input_tokens
```

```python
import os
from openai import OpenAI

# One client, many providers: change base_url and the key. This one points at Google Gemini.
chat_client = OpenAI(
    base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
    api_key=os.environ["GEMINI_API_KEY"],
)
CHAT_MODEL = "gemini-2.5-flash"

resp = chat_client.chat.completions.create(
    model=CHAT_MODEL,
    messages=[
        {"role": "system", "content": "You are Relay, the support assistant for Northwind Outfitters."},
        {"role": "user", "content": "What is your return window for tents?"},
    ],
)
print(resp.choices[0].message.content)
print(resp.usage)  # prompt_tokens, completion_tokens, prompt_tokens_details.cached_tokens
```

| Provider or server | OpenAI-compatible `base_url` | Key |
|---|---|---|
| OpenAI | default (`https://api.openai.com/v1`) | `OPENAI_API_KEY` |
| Google Gemini | [`https://generativelanguage.googleapis.com/v1beta/openai/`](https://ai.google.dev/gemini-api/docs/openai) | `GEMINI_API_KEY` |
| Ollama, on your machine | [`http://localhost:11434/v1/`](https://docs.ollama.com/api/openai-compatibility) | any placeholder; Ollama ignores it |
| vLLM, your own server | [`http://localhost:8000/v1`](https://docs.vllm.ai/en/latest/serving/online_serving/openai_compatible_server/) in the docs example | whatever you configured |
| OpenRouter | [`https://openrouter.ai/api/v1`](https://openrouter.ai/docs/quickstart) | `OPENROUTER_API_KEY` |
| Hugging Face Inference Providers | [`https://router.huggingface.co/v1`](https://huggingface.co/docs/inference-providers/index) | `HF_TOKEN` |

Two differences to notice. Anthropic takes the system prompt as its own parameter and returns a list of typed content blocks; Chat Completions puts the system prompt in the message list and returns `choices[0].message`. And the usage fields have different names, which matters when you build cost dashboards in Week 5. Gateways such as [LiteLLM](https://docs.litellm.ai/docs/) translate between formats for you; the course's reference code does the same in about 150 lines, so you can see how.

## Tokens are the unit of everything

Models read and write tokens, which are word pieces. In English, one token is roughly four characters or three quarters of a word. Tokens matter for three reasons:

- **Cost.** You pay per input token and per output token. Output costs 4 to 8 times more per token than input on current APIs (figure below).
- **Latency.** Input tokens are processed in parallel and are fast. Output tokens are generated one at a time, so latency is dominated by how many tokens the model writes.
- **Limits.** The context window is the maximum number of tokens in one request plus response. Current frontier models accept up to 1 million tokens, but more context is slower, costlier, and can reduce accuracy.

> [!numbers] A request with 20,000 input tokens and 400 output tokens. Prefill (reading input) on a hosted model runs at thousands of tokens per second, so roughly 0.3 to 1 s before the first output token. Generation at 60 to 120 tokens per second takes 3 to 7 s for 400 tokens. **Output length, not input length, usually dominates latency.** Ask for shorter answers and you get faster ones.

```viz
caption: On every major API an output token costs 4 to 8 times an input token. Long answers are where both the money and the waiting go.
<div class="vz-bars"><span>Gemini 2.5 Flash-Lite</span><span class="bar sk"><i class="sk w" style="--w:48%"></i></span><b>4x</b><span>Claude Haiku, Sonnet, Opus 5.5</span><span class="bar sk"><i class="sk w" style="--w:60%"></i></span><b>5x</b><span>GPT-5, GPT-5 mini</span><span class="bar sk"><i class="sk w" style="--w:96%"></i></span><b>8x</b><span>Gemini 2.5 Flash</span><span class="bar sk"><i class="sk w" style="--w:100%"></i></span><b>8.3x</b></div>
<p>output price divided by input price, per token</p>
<div class="vz-src">List prices per million tokens, October 2026: <a href="https://ai.google.dev/gemini-api/docs/pricing">Google</a> (2.5 Flash-Lite $0.10 / $0.40, 2.5 Flash $0.30 / $2.50); <a href="https://platform.claude.com/docs/en/about-claude/pricing">Anthropic</a> (Haiku 5.5 $0.10 / $0.50, Sonnet 5.5 $2 / $10, Opus 5.5 $4 / $20); <a href="https://developers.openai.com/api/docs/pricing">OpenAI</a> (gpt-5 $1.25 / $10, gpt-5-mini $0.25 / $2).</div>
```

Two latency numbers you will see everywhere:

- **TTFT** (time to first token): how long the user waits before anything appears. Streaming hides generation time behind TTFT.
- **TPOT** (time per output token) or its inverse, output tokens per second.

## Tool calling

Tool calling lets the model ask your code to do something. You describe tools with a name, a description, and a JSON Schema for the input. The model replies either with text or with one or more tool calls. Your code runs the tool and sends back a tool result. The model never executes anything itself. Every major API works this way; only the field names differ:

| | Anthropic Messages | OpenAI-style Chat Completions (OpenAI, Gemini, Ollama, vLLM, routers) |
|---|---|---|
| Tool schema field | `input_schema` | `function.parameters`, inside `{"type": "function", ...}` |
| Model asks for a tool | `tool_use` content blocks, `stop_reason: "tool_use"` | `message.tool_calls`, `finish_reason: "tool_calls"` |
| You send the result | `tool_result` blocks in the next user message | one `role: "tool"` message per call, with its `tool_call_id` |

Sources: Anthropic [tool use](https://platform.claude.com/docs/en/agents-and-tools/tool-use/overview); OpenAI [Chat Completions reference](https://developers.openai.com/api/docs/api-reference/chat).

```mermaid
sequenceDiagram
  participant U as User
  participant A as Your app
  participant M as Model API
  participant T as Tool (orders DB)
  U->>A: "Where is order 1042?"
  A->>M: messages + tool definitions
  M-->>A: tool_use get_order(order_id=1042)
  A->>T: SELECT ... WHERE id=1042
  T-->>A: {status: "shipped", eta: "Oct 18"}
  A->>M: messages + tool_result
  M-->>A: "Order 1042 shipped and should arrive Oct 18."
  A-->>U: answer
```

```python
tools = [{
    "name": "get_order",
    "description": "Look up one order by its numeric ID. Returns status, items, and ETA.",
    "input_schema": {
        "type": "object",
        "properties": {"order_id": {"type": "integer"}},
        "required": ["order_id"],
        "additionalProperties": False,
    },
    "strict": True,  # the model's input is guaranteed to match the schema
}]

# The same tool for an OpenAI-style API: the schema moves under "function" and is called "parameters".
chat_tools = [{"type": "function", "function": {
    "name": t["name"], "description": t["description"],
    "parameters": t["input_schema"], "strict": True,
}} for t in tools]
```

Strict mode is not universal. OpenAI's [strict mode](https://developers.openai.com/api/docs/guides/function-calling) requires `"additionalProperties": false` and every property listed as required, which this schema already does. Open-weights models served by vLLM need tool calling switched on at launch (`--enable-auto-tool-choice` plus a `--tool-call-parser` for the model family, such as `hermes` for Qwen or `llama3_json` for Llama 3.1, per the [vLLM docs](https://docs.vllm.ai/en/latest/features/tool_calling.html)). Validate tool inputs in your own code either way.

That loop, call the model, run requested tools, append results, call again, is an **agent loop**. Week 1 builds one properly.

## Embeddings and vector search

An embedding model turns text into a fixed-length vector (for example 1,024 floats) so that texts with similar meaning land close together. Retrieval-augmented generation (RAG) embeds your documents once, stores the vectors in an index, then at question time embeds the query, finds the nearest chunks, and puts them in the prompt.

```mermaid
flowchart LR
  D[Documents] --> C[Chunk] --> E[Embed] --> I[(Vector index)]
  Q[User question] --> QE[Embed query] --> S{Nearest neighbours}
  I --> S --> P[Prompt with top chunks] --> M[LLM] --> A[Answer with citations]
```

Vector search finds meaning but misses exact terms like SKUs and error codes. Keyword search (BM25) finds exact terms but misses paraphrases. Production systems usually run both. Week 2 covers this in depth.

## Where the money goes

A rough model of LLM application cost:

`cost per request = (input tokens × input price) + (output tokens × output price) + retrieval + compute`

Agents multiply this, because each loop iteration resends the whole conversation. A 6-step agent run with a 5,000-token prompt that grows by 800 tokens per step sends 5,000 + 5,800 + 6,600 + 7,400 + 8,200 + 9,000 = **42,000** input tokens, not 5,000. Prompt caching (Week 5) is how you stop paying full price for the repeated prefix.

```viz
caption: Each step of an agent resends everything before it. Six steps of a 5,000-token prompt bill 42,000 input tokens, more than 8 times the prompt.
<div class="vz-bars"><span>step 1</span><span class="bar sk"><i class="sk w" style="--w:56%"></i></span><b>5,000</b><span>step 2</span><span class="bar sk"><i class="sk w" style="--w:64%"></i></span><b>5,800</b><span>step 3</span><span class="bar sk"><i class="sk w" style="--w:73%"></i></span><b>6,600</b><span>step 4</span><span class="bar sk"><i class="sk w" style="--w:82%"></i></span><b>7,400</b><span>step 5</span><span class="bar sk"><i class="sk w" style="--w:91%"></i></span><b>8,200</b><span>step 6</span><span class="bar sk"><i class="sk w" style="--w:100%"></i></span><b>9,000</b></div>
<div class="vz-row"><span class="ch sk">one call: 5,000</span><span class="ch wide sk w">six-step run: 42,000 input tokens</span></div>
<div class="vz-src">Worked example from the text: a 5,000-token prompt that grows by 800 tokens per step.</div>
```

## Structured output

When code needs to read the model's answer, ask for JSON that matches a schema. Modern APIs can constrain output to a schema, so you do not parse free text with regexes. Use this for classifiers, extractors, routers, and LLM judges.

```python
from pydantic import BaseModel

class Intent(BaseModel):
    intent: str  # "order_status" | "return" | "product_question" | "other"
    confidence: float

# Anthropic: the SDK's parse helper takes the Pydantic model directly.
parsed = client.messages.parse(
    model=MODEL,
    max_tokens=256,
    messages=[{"role": "user", "content": "my tent arrived with a broken pole"}],
    output_format=Intent,
)
print(parsed.parsed_output)

# OpenAI-style APIs (OpenAI, Gemini, Ollama, vLLM): send the JSON Schema as response_format.
resp = chat_client.chat.completions.create(
    model=CHAT_MODEL,
    messages=[{"role": "user", "content": "my tent arrived with a broken pole"}],
    response_format={"type": "json_schema",
                     "json_schema": {"name": "Intent", "schema": Intent.model_json_schema()}},
)
intent = Intent.model_validate_json(resp.choices[0].message.content)
```

Sources: Anthropic [structured outputs](https://platform.claude.com/docs/en/build-with-claude/structured-outputs); OpenAI [structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs); Ollama [structured outputs](https://docs.ollama.com/capabilities/structured-outputs), which also work through its OpenAI-compatible `response_format`. Always validate the result: a small local model can still return something your schema rejects.

## What to build before Week 1

If any of this is new, spend an evening on a tiny project: a command-line script that answers questions about three Markdown files using embeddings, then add one tool (for example a calculator). It will make Week 1 far easier.

## Further reading

- [Intro to Large Language Models](https://www.youtube.com/watch?v=zjkBMFhNj_g), Andrej Karpathy's one-hour talk. The clearest overview of what a model is.
- Tool calling docs from [OpenAI](https://developers.openai.com/api/docs/guides/function-calling), [Anthropic](https://platform.claude.com/docs/en/agents-and-tools/tool-use/overview) and [Ollama](https://docs.ollama.com/api/openai-compatibility). Read two: the differences teach you what is the pattern and what is the vendor.
- [Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks](https://arxiv.org/abs/2005.11401), the original RAG paper.
- [Hugging Face Agents Course](https://huggingface.co/learn/agents-course), free and hands-on.
- [LLM Course](https://github.com/mlabonne/llm-course) by Maxime Labonne, a free roadmap if you want ML depth.

```quiz
[
  {"q": "A user says the agent \"forgot\" what they said three messages ago. Where is the bug most likely to be?", "options": ["The model's weights", "Your code did not include those earlier turns in the request", "The embedding model", "The API rate limit"], "answer": 1, "why": "Models are stateless. If earlier turns are missing from the request, the model cannot see them. Your system owns conversation state."},
  {"q": "Which change most reduces end-to-end latency for a typical chat answer?", "options": ["Shortening the system prompt by 10%", "Asking for answers half as long", "Using a bigger context window", "Adding more tools"], "answer": 1, "why": "Generation is sequential, so output length dominates latency. Input is processed in parallel and is comparatively cheap in time."},
  {"q": "Why do agent loops cost more than a single call with the same prompt?", "options": ["Tool calls are billed separately at a premium", "Each iteration resends the whole growing conversation as input", "Agents always use larger models", "Streaming doubles the price"], "answer": 1, "why": "Every step resends system prompt, tools, history, and tool results. Input tokens grow roughly quadratically with the number of steps unless you cache or compact."},
  {"q": "Why combine keyword (BM25) search with vector search?", "options": ["Vectors cannot be stored in Postgres", "Keyword search finds exact identifiers that embeddings blur; vectors find paraphrases that keywords miss", "BM25 is always more accurate", "It halves storage"], "answer": 1, "why": "Each method fails differently. Hybrid retrieval covers both exact-match and semantic queries."}
]
```
