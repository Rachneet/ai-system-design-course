---
id: w5-inference
week: 5
kind: lesson
title: LLM inference for system designers
short: Inference, drawn
minutes: 75
summary: Twenty ideas that explain what happens inside a model server, each with a drawing and checked numbers, so you can say why a chatbot is slow, size a self-hosted deployment, and judge KV caching, batching, quantization, speculative decoding, parallelism and the cost of a million tokens.
---

## Why a system designer needs this

You can build everything in this course on hosted APIs and never touch a GPU. Two questions still come up in every design review and interview:

1. **"Why is the chatbot so slow?"** The answer is rarely "the model is slow". It is usually something you control.
2. **"Should we self-host an open model?"** You cannot answer without knowing what limits a GPU and what one conversation costs in memory.

The lesson has five parts: the two phases and how to measure them, memory, scheduling, cheaper tokens, and scaling out. Every idea gets one drawing. Three calculators let you change the numbers yourself. Every figure is checked against the paper or engineering post it comes from, linked under the drawing.

## Part 1. Two phases, three numbers

### 1. Prefill and decode

A model answers in two phases. **Prefill** reads the whole prompt in one parallel pass. **Decode** then writes the reply one token at a time, running the whole model again for every token.

```viz
caption: Prefill is one wide pass that keeps the GPU's maths units busy. Decode is many narrow passes that mostly wait on memory.
<div class="vz-cols">
  <div class="vz-panel sk c"><h5>Prefill</h5>
    <div class="vz-row"><span class="ch sk">t1</span><span class="ch sk">t2</span><span class="ch sk">t3</span><span class="ch sk">t4</span><span class="ch sk">t5</span><span class="ch sk">t6</span></div>
    <span class="arr d sk c"></span>
    <div class="vz-row"><span class="ch wide sk c">one parallel pass over the prompt</span></div>
    <div class="vz-bars"><span>GPU maths busy</span><span class="bar sk"><i class="sk c" style="--w:92%"></i></span><b>high</b></div>
  </div>
  <div class="vz-panel sk m"><h5>Decode</h5>
    <div class="vz-row"><span class="ch sk m">pass 1</span><span class="arr sk m"></span><span class="ch sk m">pass 2</span><span class="arr sk m"></span><span class="ch sk m">pass 3</span><span>...</span></div>
    <div class="vz-row"><span class="ch sk">w1</span><span class="arr"></span><span class="ch sk">w2</span><span class="arr"></span><span class="ch sk">w3</span></div>
    <div class="vz-bars"><span>GPU maths busy</span><span class="bar sk"><i class="sk m" style="--w:18%"></i></span><b>low</b></div>
    <p>each token needs a full pass</p>
  </div>
</div>
```

### 2. TTFT, TPOT and end-to-end latency

Users judge speed by two numbers. **Time to first token** (TTFT) is the blank screen while prefill runs, plus any queueing. **Time per output token** (TPOT, also called inter-token latency) is the steady gap between words while decode streams. For a reply of N tokens:

**end-to-end latency ≈ TTFT + TPOT × (N − 1)**

```viz
caption: What a user sees. Prefill sets the blank screen; decode sets the reading pace; the output length sets the total.
<div class="vz-row"><span class="ch wide sk ghost">blank screen: queue + prefill</span><span class="ch sk m">w1</span><span class="ch sk m">w2</span><span class="ch sk m">w3</span><span class="ch sk m">w4</span><span class="ch sk m">w5</span><span class="ch sk m">w6</span><span class="ch sk m">w7</span></div>
<div class="vz-cols" style="--k:3">
  <div class="vz-panel sk"><h5>TTFT</h5><p>Chat: users hate a blank screen. Watch p95 TTFT.</p></div>
  <div class="vz-panel sk"><h5>TPOT</h5><p>Streaming: below about 15 to 20 tokens per second, reading feels slow.</p></div>
  <div class="vz-panel sk"><h5>Total time</h5><p>Batch jobs and agents: nobody watches live, so total time and cost matter.</p></div>
</div>
```

> [!numbers] A 600-token answer with a 0.4 s TTFT and a 25 ms TPOT takes 0.4 + 0.025 × 599 ≈ **15.4 s** end to end, even though the user saw text after 0.4 s. Halving the output length saves 7.5 s; halving TTFT saves 0.2 s. For long answers, output length dominates.

### 3. Throughput, latency and goodput

**Throughput** is how many tokens the whole server makes per second. **Latency** is how long one user waits. Packing more users into each decode step raises throughput but slows every user, because each step has more work. **Goodput** counts only the requests that met their latency targets. The [DistServe paper](https://www.usenix.org/conference/osdi24/presentation/zhong-yinmin) defines it as the highest request rate a system can serve while meeting both its TTFT and TPOT targets.

```viz
caption: Two systems. A makes more tokens, but half its requests miss the target, so B serves more users well.
<div class="vz-cols">
  <div class="vz-panel sk"><h5>System A: 10,000 tokens/s</h5>
    <div class="vz-bars"><span>met target</span><span class="bar sk"><i class="sk g" style="--w:50%"></i></span><b>5,000</b><span>timed out</span><span class="bar sk"><i class="sk b" style="--w:50%"></i></span><b>5,000</b></div>
  </div>
  <div class="vz-panel sk g"><h5>System B: 7,000 tokens/s</h5>
    <div class="vz-bars"><span>met target</span><span class="bar sk"><i class="sk g" style="--w:70%"></i></span><b>7,000</b><span>timed out</span><span class="bar sk"><i class="sk b" style="--w:1%"></i></span><b>0</b></div>
    <p>higher goodput: the better system</p>
  </div>
</div>
```

```widget
{"type": "batch"}
```

> [!rule] Set latency targets first (TTFT and TPOT at p95), then maximise goodput under them. A benchmark that reports only peak throughput tells you nothing about your users.

### 4. Memory-bound or compute-bound

A GPU is limited either by how fast it does maths or by how fast it moves data from memory. The ratio that decides it is **arithmetic intensity**: floating-point operations per byte read.

```viz
caption: Prefill reuses each loaded weight for many tokens. Decode loads every weight to make one token per user.
<div class="vz-cols">
  <div class="vz-panel sk c"><h5>Prefill: compute-bound</h5>
    <div class="vz-row"><span class="ch sk">weights</span><span class="arr sk c"></span><div class="cells" style="--n:6"><i class="sk fill c"></i><i class="sk fill c"></i><i class="sk fill c"></i><i class="sk fill c"></i><i class="sk fill c"></i><i class="sk fill c"></i><i class="sk fill c"></i><i class="sk fill c"></i><i class="sk fill c"></i><i class="sk fill c"></i><i class="sk fill c"></i><i class="sk fill c"></i></div></div>
    <p>all cores busy, maths per byte: plenty</p>
  </div>
  <div class="vz-panel sk m"><h5>Decode: memory-bound</h5>
    <div class="vz-row"><span class="ch sk">weights</span><span class="arr sk m"></span><div class="cells" style="--n:6"><i class="sk fill m"></i><i class="sk"></i><i class="sk"></i><i class="sk"></i><i class="sk"></i><i class="sk"></i><i class="sk"></i><i class="sk"></i><i class="sk"></i><i class="sk"></i><i class="sk"></i><i class="sk"></i></div></div>
    <p>most cores idle, maths per byte: very little</p>
  </div>
</div>
<div class="vz-cols" style="--k:3">
  <div class="vz-panel sk"><h5>Load fewer bytes</h5><p>quantization (idea 12)</p></div>
  <div class="vz-panel sk"><h5>Reuse each load</h5><p>batching (ideas 3, 9)</p></div>
  <div class="vz-panel sk"><h5>More tokens per load</h5><p>speculative decoding (idea 13)</p></div>
</div>
```

> [!numbers] An NVIDIA H100 SXM does about **989 TFLOPS** of dense BF16 maths and reads memory at **3.35 TB/s** ([datasheet](https://www.nvidia.com/en-us/data-center/h100/)). It only runs out of maths above about 989 ÷ 3.35 ≈ **295 FLOPs per byte**. Decode for one user does about 2 FLOPs per parameter and reads 2 bytes per parameter: **1 FLOP per byte**, so over 99% of the maths units wait. An 8B BF16 model is 16 GB of weights, so one step takes at least 16 ÷ 3,350 s ≈ **4.8 ms**, a ceiling of about 200 tokens per second for one user. Batching 64 users does 64 times the maths for nearly the same memory traffic.

## Part 2. Memory

### 5. The KV cache

To write each new token, attention looks back at the keys and values of every earlier token. Recomputing them every step would repeat all past work, so the server keeps them: that saved state is the **KV cache**. It turns decode from quadratic into linear work, and it is the largest consumer of GPU memory under load.

```viz
caption: Without a cache, token 101 recomputes 100 past tokens. With it, only the new token is computed, but the cache grows with every token of every conversation.
<div class="vz-cols">
  <div class="vz-panel sk"><h5>Writing token 101</h5>
    <div class="vz-row"><span class="ch wide sk x">redo tokens 1 to 100</span><span class="ch sk b">101</span><b>101 computed</b></div>
    <div class="vz-row"><span class="ch wide sk g">tokens 1 to 100: read from cache</span><span class="ch sk g">101</span><b>1 computed</b></div>
  </div>
  <div class="vz-panel sk w"><h5>Llama 3 70B, BF16, per token</h5>
    <div class="vz-row"><span class="ch sk">80 layers</span>x<span class="ch sk">8 KV heads</span>x<span class="ch sk">128 dims</span>x<span class="ch sk">2: K and V</span>x<span class="ch sk">2 bytes</span></div>
    <div class="vz-row"><span class="big w">= 320 KB</span></div>
    <div class="vz-bars"><span>1K tokens</span><span class="bar sk"><i class="sk w" style="--w:1%"></i></span><b>0.3 GB</b><span>8K</span><span class="bar sk"><i class="sk w" style="--w:6%"></i></span><b>2.7 GB</b><span>32K</span><span class="bar sk"><i class="sk w" style="--w:25%"></i></span><b>10.7 GB</b><span>128K</span><span class="bar sk"><i class="sk w" style="--w:100%"></i></span><b>43 GB</b></div>
  </div>
</div>
<div class="vz-src">Shape from the <a href="https://github.com/meta-llama/llama-models/blob/main/models/llama3_1/MODEL_CARD.md">Llama 3 model card</a>; 2 x 80 x 8 x 128 x 2 = 327,680 bytes.</div>
```

Try it with your own model and GPU. The weights stay fixed; every extra conversation, and every extra token in it, takes memory from the others.

```widget
{"type": "kv"}
```

This is why long contexts are expensive even when a provider accepts a million tokens: a long conversation holds memory for its whole life and limits how many others can run beside it.

### 6. PagedAttention

Early servers reserved one contiguous slab of memory per request, sized for the longest possible answer. Most of it sat empty. [PagedAttention](https://arxiv.org/abs/2309.06180), the idea behind vLLM, borrows virtual memory from operating systems: the cache is cut into small fixed-size blocks handed out as tokens arrive, with a block table mapping each request to its blocks.

```viz
caption: The vLLM paper measured existing systems using only 20 to 38% of KV memory for real tokens; paging cut waste to under 4% and raised throughput 2 to 4 times at the same latency.
<div class="vz-cols">
  <div class="vz-panel sk b"><h5>Old way: 3 requests, memory full</h5>
    <div class="cells" style="--n:8"><i class="sk c">A</i><i class="sk c">A</i><i class="sk c">A</i><i class="sk x"></i><i class="sk x"></i><i class="sk x"></i><i class="sk x"></i><i class="sk x"></i><i class="sk m">B</i><i class="sk m">B</i><i class="sk x"></i><i class="sk x"></i><i class="sk x"></i><i class="sk x"></i><i class="sk x"></i><i class="sk x"></i><i class="sk w">C</i><i class="sk w">C</i><i class="sk w">C</i><i class="sk w">C</i><i class="sk x"></i><i class="sk x"></i><i class="sk x"></i><i class="sk x"></i></div>
    <p class="big b">60 to 80% wasted</p><p>request D: no room</p>
  </div>
  <div class="vz-panel sk g"><h5>Paged: 6 requests, room left</h5>
    <div class="cells" style="--n:8"><i class="sk c">A</i><i class="sk m">B</i><i class="sk w">C</i><i class="sk g">D</i><i class="sk c">A</i><i class="sk">E</i><i class="sk m">B</i><i class="sk">F</i><i class="sk w">C</i><i class="sk c">A</i><i class="sk g">D</i><i class="sk w">C</i><i class="sk">E</i><i class="sk">F</i><i class="sk w">C</i><i class="sk g">D</i><i class="sk"></i><i class="sk"></i><i class="sk"></i><i class="sk"></i><i class="sk"></i><i class="sk"></i><i class="sk"></i><i class="sk"></i></div>
    <p class="big g">under 4% wasted</p><p>block table: A to blocks 1, 5, 10</p>
  </div>
</div>
<div class="vz-src">Kwon et al., <a href="https://arxiv.org/abs/2309.06180">Efficient Memory Management for LLM Serving with PagedAttention</a>, SOSP 2023.</div>
```

### 7. Prefix caching

Many requests start with the same text: a long system prompt, tool definitions, the same documents, the conversation so far. **Prefix caching** keeps the KV cache for that shared start and reuses it, so prefill only processes the new part. Hosted APIs sell the same mechanism as prompt caching, at a discount on cached input.

```viz
caption: Order the prompt from most stable to most variable. Anything that changes near the top, such as a timestamp, breaks every cache hit after it.
<div class="vz-row"><b>Req 1</b><span class="ch wide sk g">system prompt + tools + docs: computed once</span><span class="ch sk c">question 1</span></div>
<div class="vz-row"><b>Req 2</b><span class="ch wide sk g">system prompt + tools + docs: reused</span><span class="ch sk c">question 2</span></div>
<div class="vz-row"><b>Req 3</b><span class="ch wide sk g">system prompt + tools + docs: reused</span><span class="ch sk c">question 3</span></div>
<div class="vz-cols">
  <div class="vz-panel sk"><h5>Reported hit rates</h5><p><b class="big g">95%</b> Character.AI, chat with inter-turn caching (2024)</p><p><b class="big g">56%</b> DeepSeek, input tokens served from its on-disk cache (2025)</p></div>
  <div class="vz-panel sk"><h5>Prompt order</h5><div class="vz-row"><span class="ch sk g">system</span><span class="ch sk g">tools</span><span class="ch sk g">docs</span><span class="ch sk">history</span><span class="ch sk c">new message</span></div><p>stable first, changing last</p></div>
</div>
<div class="vz-src">Character.AI's figure as reported from its <a href="https://buttondown.com/ainews/archive/ainews-shazeer-et-al-2024">June 2024 research post</a>; DeepSeek's from its <a href="https://github.com/deepseek-ai/open-infra-index/blob/main/202502OpenSourceWeek/day_6_one_more_thing_deepseekV3R1_inference_system_overview.md">inference system overview</a> (342B of 608B input tokens).</div>
```

Every major API offers it, with different mechanics: Anthropic caches marked prefixes, while OpenAI and Gemini cache long repeated prefixes automatically. Week 5's caching lesson covers the API side.

### 8. Smaller caches by design: MQA, GQA and MLA

Some models shrink the KV cache in their architecture. In standard multi-head attention (MHA) every head stores its own keys and values. **Multi-query attention** (MQA) shares one key-value pair across all heads. **Grouped-query attention** (GQA) shares one per group of heads. **Multi-head latent attention** (MLA) stores a small compressed latent and expands it when needed.

```viz
caption: The same 64 query heads, four ways to store their keys and values. Smaller caches mean more users per GPU.
<div class="vz-cols" style="--k:4">
  <div class="vz-panel sk b"><h5>MHA</h5><p>own K, V per head</p><div class="vz-bars"><span>cache</span><span class="bar sk"><i class="sk b" style="--w:100%"></i></span><b></b></div><p class="big b">baseline</p></div>
  <div class="vz-panel sk w"><h5>GQA</h5><p>groups share K, V</p><div class="vz-bars"><span>cache</span><span class="bar sk"><i class="sk w" style="--w:12.5%"></i></span><b></b></div><p class="big w">8x smaller</p><p>Llama 3 70B: 64 query heads, 8 KV heads</p></div>
  <div class="vz-panel sk m"><h5>MQA</h5><p>all share one K, V</p><div class="vz-bars"><span>cache</span><span class="bar sk"><i class="sk m" style="--w:2%"></i></span><b></b></div><p class="big m">smallest</p><p>some quality cost</p></div>
  <div class="vz-panel sk g"><h5>MLA</h5><p>compressed latent</p><div class="vz-bars"><span>cache</span><span class="bar sk"><i class="sk g" style="--w:7%"></i></span><b></b></div><p class="big g">-93.3%</p><p>DeepSeek-V2 against DeepSeek 67B; 5.76x max throughput</p></div>
</div>
<div class="vz-src"><a href="https://arxiv.org/abs/2305.13245">GQA</a> (Ainslie et al., 2023); <a href="https://arxiv.org/abs/2405.04434">DeepSeek-V2</a> (2024).</div>
```

You cannot switch these on at serving time; they are a reason to prefer one open model over another when memory is your limit.

## Part 3. Scheduling

### 9. Continuous batching

A GPU is most efficient when it serves many users in the same step. **Static batching** waits until every request in a batch finishes, so short requests leave idle slots behind. **Continuous batching**, introduced as iteration-level scheduling in [Orca](https://www.usenix.org/conference/osdi22/presentation/yu), lets a new request join the moment a slot frees up. Every modern serving engine does this.

```viz
caption: Five requests of different lengths. Static batching waits for the longest; continuous batching refills a slot at the next step.
<div class="vz-cols">
  <div class="vz-panel sk b"><h5>Static: many idle slots</h5>
    <div class="cells" style="--n:8"><i class="sk c">A</i><i class="sk c"></i><i class="sk c"></i><i class="sk c"></i><i class="sk c"></i><i class="sk c"></i><i class="sk c"></i><i class="sk c"></i><i class="sk c">B</i><i class="sk c"></i><i class="sk x"></i><i class="sk x"></i><i class="sk x"></i><i class="sk x"></i><i class="sk x"></i><i class="sk x"></i><i class="sk c">C</i><i class="sk c"></i><i class="sk c"></i><i class="sk c"></i><i class="sk x"></i><i class="sk x"></i><i class="sk x"></i><i class="sk x"></i><i class="sk c">D</i><i class="sk x"></i><i class="sk x"></i><i class="sk x"></i><i class="sk x"></i><i class="sk x"></i><i class="sk x"></i><i class="sk x"></i></div>
    <p>slots wait for the longest request</p>
  </div>
  <div class="vz-panel sk g"><h5>Continuous: always full</h5>
    <div class="cells" style="--n:8"><i class="sk c">A</i><i class="sk c"></i><i class="sk c"></i><i class="sk c"></i><i class="sk c"></i><i class="sk c"></i><i class="sk c"></i><i class="sk c"></i><i class="sk c">B</i><i class="sk c"></i><i class="sk g">F</i><i class="sk g"></i><i class="sk g"></i><i class="sk g"></i><i class="sk g"></i><i class="sk g">J</i><i class="sk c">C</i><i class="sk c"></i><i class="sk c"></i><i class="sk c"></i><i class="sk g">G</i><i class="sk g"></i><i class="sk g"></i><i class="sk g"></i><i class="sk c">D</i><i class="sk g">H</i><i class="sk g"></i><i class="sk g"></i><i class="sk g"></i><i class="sk g">K</i><i class="sk g"></i><i class="sk g"></i></div>
    <p>a freed slot is refilled at once (F to K join)</p>
  </div>
</div>
```

### 10. Chunked prefill

A very long prompt can hold the GPU through one giant prefill step, freezing every other user's stream: their TPOT spikes. **Chunked prefill**, from [Sarathi-Serve](https://www.usenix.org/conference/osdi24/presentation/agrawal), cuts the prompt into pieces of a few thousand tokens and runs each piece in the same step as everyone else's next decode token.

```viz
caption: The same 50,000-token prompt, scheduled two ways. Chunking trades a slightly longer TTFT for the long request against smooth streaming for everyone else.
<div class="vz-panel sk b"><h5>Without chunking</h5>
  <div class="vz-row"><span class="ch sk c">step</span><span class="ch sk c">step</span><span class="ch wide sk w">50,000-token prefill: other streams frozen</span><span class="ch sk c">step</span><span class="ch sk c">step</span></div>
  <div class="vz-row"><b>gap between tokens</b><span class="ch sk g">.</span><span class="ch sk g">.</span><span class="ch sk b">stall</span><span class="ch sk g">.</span><span class="ch sk g">.</span><b class="big b">TPOT spike</b></div>
</div>
<div class="vz-panel sk g"><h5>Chunked prefill</h5>
  <div class="vz-row"><span class="ch sk w">chunk + decode</span><span class="ch sk w">chunk + decode</span><span class="ch sk w">chunk + decode</span><span class="ch sk w">chunk + decode</span><span>...</span></div>
  <div class="vz-row"><b>gap between tokens</b><span class="ch sk g">.</span><span class="ch sk g">.</span><span class="ch sk g">.</span><span class="ch sk g">.</span><span class="ch sk g">.</span><b class="big g">smooth TPOT</b></div>
</div>
```

### 11. Disaggregating prefill and decode

Prefill and decode stress the GPU differently, and when they share a GPU they interfere. Disaggregated serving runs them on **separate pools**: the prefill pool reads the prompt and builds the KV cache, ships it over a fast interconnect (NVLink or RDMA networking), and the decode pool generates the answer. Each pool can be sized and tuned on its own.

```viz
caption: DistServe reported serving 7.4 times more requests, or meeting 12.6 times tighter latency targets, than co-located systems; the cost is moving the KV cache and running two pools.
<div class="vz-cols" style="--k:3">
  <div class="vz-panel sk c"><h5>Prefill pool</h5><div class="vz-row"><span class="ch sk">t1</span><span class="ch sk">t2</span><span class="ch sk">t3</span><span class="ch sk">t4</span></div><p>tuned for compute</p></div>
  <div class="vz-panel"><h5>KV cache</h5><div class="vz-row"><span class="arr long sk w"></span></div><p>NVLink or RDMA</p></div>
  <div class="vz-panel sk m"><h5>Decode pool</h5><div class="vz-row"><span class="ch sk m">w1</span><span class="ch sk m">w2</span><span class="ch sk m">w3</span></div><p>tuned for memory</p></div>
</div>
<div class="vz-cols"><div class="vz-panel sk g"><h5>Win</h5><p>long prompts cannot stall token streams; size each pool for its own bottleneck</p></div><div class="vz-panel sk b"><h5>Cost</h5><p>more moving parts, and the network must move the cache fast</p></div></div>
<div class="vz-src"><a href="https://www.usenix.org/conference/osdi24/presentation/zhong-yinmin">DistServe</a> (OSDI 2024); also <a href="https://arxiv.org/abs/2311.18677">Splitwise</a> and <a href="https://arxiv.org/abs/2407.00079">Mooncake</a>, which serves Moonshot's Kimi. Open-source stacks: <a href="https://github.com/ai-dynamo/dynamo">NVIDIA Dynamo</a>, <a href="https://github.com/llm-d/llm-d">llm-d</a>.</div>
```

## Part 4. Cheaper tokens

### 12. Quantization

Weights are numbers, usually stored in 16 bits. **Quantization** stores them in 8 or 4 bits. Because decode is limited by bytes loaded, fewer bits means faster tokens and more room for the KV cache.

```viz
caption: One weight, three precisions. The right format depends on your GPU generation, and on your own evals.
<div class="vz-cols">
  <div class="vz-panel sk"><h5>One weight, in bits</h5>
    <div class="vz-bars"><span>BF16</span><span class="bar sk"><i class="sk c" style="--w:100%"></i></span><b>2 bytes</b><span>FP8</span><span class="bar sk"><i class="sk c" style="--w:50%"></i></span><b>1 byte</b><span>FP4</span><span class="bar sk"><i class="sk c" style="--w:25%"></i></span><b>0.5 byte</b></div>
    <p>decode is memory-bound: fewer bytes, faster tokens</p>
  </div>
  <div class="vz-panel sk"><h5>Pick by GPU</h5>
    <div class="vz-row"><span class="ch sk c">Hopper: H100, H200</span><span class="arr sk"></span><b>FP8, the safe default</b></div>
    <div class="vz-row"><span class="ch sk m">Blackwell: B200, GB200</span><span class="arr sk"></span><b>NVFP4</b></div>
    <div class="vz-row"><span class="ch sk">smaller and local GPUs</span><span class="arr sk"></span><b>INT4 weights: AWQ, GPTQ</b></div>
  </div>
</div>
<div class="vz-row"><span class="ch sk g">task A passes</span><span class="ch sk g">task B passes</span><span class="ch sk b">task C breaks</span><b>averages hide the task that breaks: run your own evals</b></div>
<div class="vz-src">NVIDIA reports 1% or less accuracy loss moving DeepSeek-R1-0528 from FP8 to NVFP4 on its evaluations (<a href="https://developer.nvidia.com/blog/introducing-nvfp4-for-efficient-and-accurate-low-precision-inference">NVIDIA, 2025</a>). That is one model on one vendor's benchmark set, not a guarantee for yours.</div>
```

### 13. Speculative decoding

Decode leaves most of the maths units idle, so put them to work. A small **draft** model guesses the next few tokens; the large model checks all of them in **one** pass. Every accepted guess is a token almost for free, and the verification rule keeps the output distribution exactly the same as the large model alone.

```viz
caption: One pass of the big model accepts three drafted tokens and corrects the fourth: four tokens for one pass.
<div class="vz-row"><b>draft guesses</b><span class="ch sk ghost">sat</span><span class="ch sk ghost">on</span><span class="ch sk ghost">the</span><span class="ch sk ghost">rug</span><span class="ch sk ghost">today</span></div>
<div class="vz-row"><b>big model</b><span class="ch wide sk m">checks all five in one pass</span></div>
<div class="vz-row"><b>output</b><span class="ch sk g">sat</span><span class="ch sk g">on</span><span class="ch sk g">the</span><span class="ch sk b">mat (rug rejected)</span><b>4 tokens, 1 pass</b></div>
<div class="vz-cols" style="--k:3">
  <div class="vz-panel sk g"><h5>Same output</h5><p>identical distribution to the big model</p></div>
  <div class="vz-panel sk"><h5>2 to 3x typical, 6.5x peak</h5><p>single-request decoding; EAGLE-3's serving throughput gain was 1.38x at batch 64</p></div>
  <div class="vz-panel sk b"><h5>Bad guesses cost time</h5><p>and gains shrink as batches fill the GPU</p></div>
</div>
<div class="vz-src"><a href="https://arxiv.org/abs/2211.17192">Leviathan et al.</a> (2023): 2 to 3x with identical outputs. <a href="https://arxiv.org/abs/2503.01840">EAGLE-3</a> (NeurIPS 2025): up to 6.5x speedup, and 1.38x throughput at batch size 64 in SGLang.</div>
```

> [!warn] Speculative decoding helps most when the GPU is idle, which means low traffic or latency-critical routes. At high batch sizes the GPU is already busy and the gain falls toward nothing. Measure at your real load.

### 14. Distillation

Sometimes the best optimization is a smaller model. **Distillation** trains a small student to copy a large teacher's outputs, so on a narrow task it gives similar answers on a fraction of the hardware. DeepSeek distilled R1's reasoning traces into Qwen and Llama students from 1.5B to 70B parameters.

```viz
caption: A large teacher produces worked examples; small students learn from them. On a narrow task the student can match the teacher at a fraction of the cost.
<div class="vz-row"><span class="ch sk m">DeepSeek-R1 teacher</span><span class="arr long sk"></span><span class="ch sk">reasoning traces: step 1, step 2, step 3</span><span class="arr long sk"></span><span class="ch sk g">Qwen students</span><span class="ch sk g">Llama students</span></div>
<div class="vz-bars"><span>1.5B</span><span class="bar sk"><i class="sk g" style="--w:2%"></i></span><b></b><span>8B</span><span class="bar sk"><i class="sk g" style="--w:11%"></i></span><b></b><span>32B</span><span class="bar sk"><i class="sk g" style="--w:46%"></i></span><b></b><span>70B</span><span class="bar sk"><i class="sk g" style="--w:100%"></i></span><b></b></div>
<div class="vz-src"><a href="https://arxiv.org/abs/2501.12948">DeepSeek-R1</a> (2025), which released distilled Qwen 1.5B, 7B, 14B and 32B and Llama 8B and 70B models.</div>
```

For product teams the practical version is: once a hosted model handles a high-volume, narrow task well (ticket classification, extraction), log its outputs, fine-tune a small open model on them, and switch only when your eval suite says the small model is as good on that task.

### 15. FlashAttention

A GPU has huge but slow memory (HBM) and a tiny but very fast one on the chip (SRAM). Naive attention writes a giant score matrix out to HBM and reads it back. **FlashAttention** works in small tiles that stay on the chip and never writes the full matrix.

```viz
caption: Same maths, far less traffic to slow memory. It is the default in every modern serving stack.
<div class="vz-cols">
  <div class="vz-panel sk b"><h5>Naive</h5>
    <div class="vz-row"><span class="ch wide sk w">SRAM: tiny, fast, on chip</span></div>
    <div class="vz-row"><span class="arr d sk b"></span><span>write out, read back</span></div>
    <div class="vz-row"><span class="ch wide sk x">HBM: full score matrix</span></div>
    <p class="big b">heavy traffic</p>
  </div>
  <div class="vz-panel sk g"><h5>FlashAttention</h5>
    <div class="vz-row"><span class="ch wide sk w">SRAM: one tile at a time</span></div>
    <div class="vz-row"><span class="arr d sk g"></span><span>result only</span></div>
    <div class="vz-row"><span class="ch wide sk g">HBM: output, matrix never written</span></div>
    <p class="big g">light traffic</p>
  </div>
</div>
<div class="vz-src"><a href="https://arxiv.org/abs/2205.14135">FlashAttention</a> (2022). <a href="https://arxiv.org/abs/2603.05451">FlashAttention-4</a> (2026) reports about 1,613 TFLOPs/s in BF16 on a B200, 71% of peak.</div>
```

### 16. Kernel fusion and CUDA graphs

A forward pass runs hundreds of small GPU programs called kernels. Each one writes to slow memory, and each waits for the CPU to launch it. **Fusion** merges kernels so data stays on the chip. **CUDA graphs** record the whole sequence of launches once and replay it, so the GPU runs back to back. vLLM and SGLang capture graphs at startup, which is one reason servers take a while to become ready.

```viz
caption: Fusion removes memory round trips; graphs remove launch gaps.
<div class="vz-cols">
  <div class="vz-panel sk"><h5>Kernel fusion</h5>
    <div class="vz-row"><span class="ch sk b">norm</span><span class="ch sk b">mul</span><span class="ch sk b">add</span><span class="ch sk b">act</span><b>4 round trips</b></div>
    <span class="arr d sk"></span>
    <div class="vz-row"><span class="ch wide sk g">norm, mul, add, act: one fused kernel</span><b>read once, write once</b></div>
  </div>
  <div class="vz-panel sk"><h5>CUDA graphs</h5>
    <div class="vz-row"><b>before</b><span class="ch sk c">launch</span><span class="ch sk x">idle</span><span class="ch sk c">launch</span><span class="ch sk x">idle</span><span class="ch sk c">launch</span></div>
    <div class="vz-row"><b>after</b><span class="ch sk c">one replay</span><span class="ch wide sk g">kernels back to back</span></div>
  </div>
</div>
```

## Part 5. Scaling out

### 17. Tensor and pipeline parallelism

Big models do not fit on one GPU: a 405B-parameter model in FP8 is about 405 GB of weights, against 80 GB on an H100. **Tensor parallelism** slices every layer across GPUs that work on each token together, so they talk constantly and belong inside one fast NVLink node. **Pipeline parallelism** gives each GPU a block of layers, like an assembly line, so it talks little and can span nodes.

```viz
caption: Tensor parallelism inside a node, pipeline parallelism across nodes, is the usual layout for very large dense models.
<div class="vz-row"><b>405 GB of FP8 weights</b><span class="ch sk c">1 H100: 80 GB</span><span class="ch wide sk x">325 GB does not fit</span></div>
<div class="vz-cols">
  <div class="vz-panel sk c"><h5>Tensor: slice every layer</h5>
    <div class="vz-row"><span class="ch sk c">GPU 1</span><span class="ch sk c">GPU 2</span><span class="ch sk c">GPU 3</span><span class="ch sk c">GPU 4</span></div>
    <p class="big b">constant talk</p><p>sync every layer: keep inside one NVLink node</p>
  </div>
  <div class="vz-panel sk m"><h5>Pipeline: split by layers</h5>
    <div class="vz-row"><span class="ch sk m">GPU 1: layers 1 to 40</span><span class="arr sk"></span><span class="ch sk m">GPU 2: 41 to 80</span><span class="arr sk"></span><span class="ch sk m">...</span></div>
    <p class="big g">little talk</p><p>a request walks every stage in order</p>
  </div>
</div>
```

### 18. Mixture of experts and expert parallelism

A **mixture-of-experts** (MoE) model has many small expert networks per layer, and a router sends each token to only a few of them. You store every expert but compute only a handful, so an MoE model has the memory footprint of a huge model and the per-token compute of a small one. **Expert parallelism** spreads the experts across GPUs.

```viz
caption: DeepSeek-V3 routes each token to 8 of 256 experts plus one shared expert. In decode, DeepSeek spreads experts over 144 GPUs and copies hot experts to spare GPUs.
<div class="vz-cols">
  <div class="vz-panel sk"><h5>DeepSeek-V3: 8 of 256 experts per token</h5>
    <div class="vz-row"><span class="ch sk">token</span><span class="arr sk"></span><span class="ch sk c">router</span><span class="arr sk"></span><div class="cells" style="--n:8"><i class="sk"></i><i class="sk fill c"></i><i class="sk"></i><i class="sk"></i><i class="sk fill c"></i><i class="sk"></i><i class="sk"></i><i class="sk"></i><i class="sk"></i><i class="sk"></i><i class="sk fill c"></i><i class="sk"></i><i class="sk fill c"></i><i class="sk"></i><i class="sk"></i><i class="sk fill c"></i></div></div>
    <div class="vz-bars"><span>memory</span><span class="bar sk"><i class="sk w" style="--w:100%"></i></span><b>671B params</b><span>compute</span><span class="bar sk"><i class="sk g" style="--w:5.5%"></i></span><b>37B per token</b></div>
  </div>
  <div class="vz-panel sk"><h5>Decode: 18 nodes, 144 GPUs</h5>
    <div class="vz-row"><span class="ch wide sk m">network shuffles tokens to their experts</span></div>
    <div class="vz-row"><span class="ch sk">GPU: 2 routed + 1 shared</span><span class="ch sk">GPU: 2 routed + 1 shared</span><span>...</span></div>
    <div class="vz-row"><span class="ch sk b">hot expert E7: overloaded</span><span class="arr sk"></span><span class="ch sk g">copy E7 to a spare GPU</span></div>
  </div>
</div>
<div class="vz-src"><a href="https://arxiv.org/abs/2412.19437">DeepSeek-V3 technical report</a>; deployment from DeepSeek's <a href="https://github.com/deepseek-ai/open-infra-index/blob/main/202502OpenSourceWeek/day_6_one_more_thing_deepseekV3R1_inference_system_overview.md">inference system overview</a> (decode: EP144 over 18 nodes, 2 routed and 1 shared expert per GPU).</div>
```

Most frontier open-weights models now use MoE. For capacity planning, the rule is: **memory follows total parameters, speed follows active parameters**.

### 19. KV-aware routing and autoscaling

Once you run many copies of a model, you decide where each request goes and how many copies to keep. A round-robin load balancer sends turn 12 of a chat to a replica that has never seen turns 1 to 11, which redoes the whole prefill. A **KV-aware router** sends it to the replica that already has the longest matching prefix cached. **Autoscaling** grows and shrinks the fleet with traffic, but GPU servers take minutes to start, so it scales on queue depth and keeps a warm buffer.

```viz
caption: Route by cache, scale by queue. DeepSeek ran 278 nodes at peak and 226.75 on average in one day, lending the spares to research at night.
<div class="vz-cols">
  <div class="vz-panel sk"><h5>KV-aware routing</h5>
    <div class="vz-row"><span class="ch sk">turn 12</span><span class="arr sk"></span><span class="ch sk g">KV router</span></div>
    <div class="vz-row"><span class="ch sk">replica A: other chat</span><span class="ch sk g">replica B: turns 1 to 11</span><span class="ch sk ghost">replica C: empty</span></div>
    <div class="vz-row"><span class="ch sk b">miss</span><span>round robin: redo the whole prefill</span></div>
    <div class="vz-row"><span class="ch sk g">hit</span><span>longest prefix match: compute only turn 12</span></div>
  </div>
  <div class="vz-panel sk"><h5>Autoscaling</h5>
    <div class="vz-bars"><span>day</span><span class="bar sk"><i class="sk m" style="--w:100%"></i></span><b>278 nodes</b><span>average</span><span class="bar sk"><i class="sk m" style="--w:82%"></i></span><b>226.75</b></div>
    <p>cold starts take minutes: scale on queue depth and KV cache use, keep a warm buffer</p>
  </div>
</div>
<div class="vz-src">Cache-aware routers: <a href="https://github.com/ai-dynamo/dynamo">NVIDIA Dynamo</a>, <a href="https://github.com/llm-d/llm-d">llm-d</a>, the SGLang router. Node counts from DeepSeek's inference system overview.</div>
```

### 20. Cost per million tokens

Every idea above ends in one number: the cost to produce a million tokens. Take what the GPUs cost per hour and divide by how many millions of tokens they produce in that hour. Faster serving means cheaper tokens; idle hours make every token dearer.

```viz
caption: DeepSeek's decode nodes, by its own numbers. The headline revenue is theoretical: much traffic is free or billed at lower V3 and night-time prices.
<div class="vz-row"><span class="ch sk">8 H800 GPUs x $2/h</span><b>= $16/h</b><span class="arr sk"></span><span class="ch sk c">14.8k output tokens/s = 53M/h</span><span class="arr sk"></span><span class="big g">about $0.30 per 1M output tokens</span></div>
<div class="vz-cols">
  <div class="vz-panel sk"><h5>Levers</h5><p><b>more tokens per hour:</b> batching, quantization, speculative decoding</p><p><b>skip tokens:</b> prefix caching (56.3% of input tokens hit the cache)</p><p><b>fewer idle hours:</b> autoscaling</p></div>
  <div class="vz-panel sk"><h5>One day at DeepSeek</h5><div class="vz-bars"><span>theoretical revenue</span><span class="bar sk"><i class="sk g" style="--w:100%"></i></span><b>$562K</b><span>GPU cost</span><span class="bar sk"><i class="sk b" style="--w:15.5%"></i></span><b>$87K</b></div></div>
</div>
<div class="vz-src">All figures from DeepSeek's <a href="https://github.com/deepseek-ai/open-infra-index/blob/main/202502OpenSourceWeek/day_6_one_more_thing_deepseekV3R1_inference_system_overview.md">inference system overview</a> (March 2025). The $0.30 counts decode GPUs only; prefill nodes, redundancy, staff and idle time are extra.</div>
```

```widget
{"type": "cost"}
```

## What this means when you only use an API

You may never run a GPU, but every idea above shows up in your bill and your latency:

| Idea | What you control through an API |
|---|---|
| Prefill and TTFT | Shorter and cached prompts; stream the answer |
| Decode and TPOT | Shorter outputs; lower reasoning effort where quality allows |
| Prefix caching | Stable prompt order; the provider's prompt caching; cache hit rate on your dashboard |
| Goodput | Choose providers and tiers on p95 TTFT and tokens per second at your load, not on averages |
| Quantization and distillation | Smaller model tiers and open models on narrow, high-volume routes, gated by evals |
| Cost per million tokens | The provider's price already includes their utilisation; self-hosting means paying for your idle hours |

## Serving engines you will meet

| Engine | Good for |
|---|---|
| [vLLM](https://docs.vllm.ai/en/latest/) | The most widely used open-source server: PagedAttention, continuous batching, prefix caching, many models and hardware types |
| [SGLang](https://docs.sglang.ai/) | High-throughput serving with RadixAttention prefix caching; used for large MoE deployments |
| [TensorRT-LLM](https://github.com/NVIDIA/TensorRT-LLM) | Maximum performance on NVIDIA GPUs, with more setup |
| [NVIDIA Dynamo](https://github.com/ai-dynamo/dynamo), [llm-d](https://github.com/llm-d/llm-d) | Fleet-level layers on top of engines: disaggregated serving, KV-aware routing, autoscaling |
| [llama.cpp](https://github.com/ggml-org/llama.cpp), [Ollama](https://ollama.com/) | Local and edge inference on CPUs, Macs and small GPUs, with quantized models |

All of them expose an OpenAI-compatible API, which is why Relay can switch to a self-hosted model by changing one setting.

## Why is the chatbot so slow? A diagnostic order

When users complain about speed, check these in order. Most are not about the model.

1. **No streaming.** Users stare at a spinner for the whole generation. Stream, and perceived latency drops to TTFT.
2. **Too many sequential model calls.** A router, a query rewrite, three agent steps and an output judge are six round trips in a row. Trace a slow request and count them. Parallelise or remove steps.
3. **Long outputs.** Decode time is proportional to output tokens (idea 2). Ask for shorter answers.
4. **Long prompts without caching.** TTFT grows with uncached prompt length. Check your cache hit rate (idea 7).
5. **Reasoning tokens.** Models that think before answering spend output tokens you do not see. Lower the effort setting on routes that do not need it.
6. **Slow tools.** A 3-second inventory API inside an agent loop is a 3-second delay per call. Add timeouts and caching.
7. **Queueing.** Hitting rate limits means waiting for capacity. Check 429 rates and client-side throttles.
8. **Model size.** Only now: a smaller model on easy routes.

> [!tip] Put TTFT and total turn time on the same dashboard, broken down by span: router, retrieval, each model call, each tool. The slow part is usually obvious within a minute of looking.

## API or self-host?

| Factor | Hosted API | Self-hosted open model |
|---|---|---|
| Quality | Frontier models | Strong open models, usually somewhat behind the frontier |
| Cost at low or spiky volume | Pay per token, scale to zero | Idle GPUs cost money around the clock |
| Cost at very high, steady volume | Can be expensive | Can be cheaper if GPUs stay busy |
| Data control | Provider terms, regions, zero-retention options | Full control |
| Latency control | Limited | Full (batch size, hardware, placement) |
| Operational burden | Low | High: GPUs, serving stack, upgrades, on-call |

A rough break-even test: estimate your monthly tokens and price them on the API, then use the cost calculator above with a realistic utilisation (often 30 to 60%, not 100%) and add the engineering time to run the fleet. For most product teams the API wins until volume is large and steady, or a data constraint forces the decision. Open-weights models through an inference provider (OpenRouter, Hugging Face Inference Providers, Together, Groq and others) are a useful middle step: open models, no GPUs to run.

## Design review questions

> [!interview] Walk me through where the time goes in your slowest p95 turn. How many sequential model calls are there?

> [!interview] What are your TTFT and TPOT targets, and what is your goodput at peak load against them?

> [!interview] How much KV cache does one of your longest conversations need, and how many fit on one GPU?

> [!interview] What would speculative decoding change for your users at your real batch size, and what would it not change?

> [!interview] At what monthly volume would self-hosting be cheaper than your API bill, including idle hours and people?

## Further reading

- [Optimizing your LLM in production](https://huggingface.co/blog/optimize-llm), Hugging Face. Quantization, FlashAttention, KV cache and GQA with worked numbers.
- [Efficient Memory Management for LLM Serving with PagedAttention](https://arxiv.org/abs/2309.06180), the vLLM paper.
- [DistServe](https://www.usenix.org/conference/osdi24/presentation/zhong-yinmin) and [Sarathi-Serve](https://www.usenix.org/conference/osdi24/presentation/agrawal), OSDI 2024: goodput, disaggregation and chunked prefill.
- [DeepSeek-V3/R1 inference system overview](https://github.com/deepseek-ai/open-infra-index/blob/main/202502OpenSourceWeek/day_6_one_more_thing_deepseekV3R1_inference_system_overview.md): a rare public account of a large production fleet, with real costs.
- [Fast Inference from Transformers via Speculative Decoding](https://arxiv.org/abs/2211.17192) and [EAGLE-3](https://arxiv.org/abs/2503.01840).
- Jam with AI's illustrated inference series on Instagram (2026), a good visual companion to this lesson.
- [Artificial Analysis](https://artificialanalysis.ai/), for measured TTFT and tokens per second across hosted models.

```quiz
[
  {"q": "Which phase of generation is limited mainly by memory bandwidth?", "options": ["Prefill", "Decode", "Tokenization", "Embedding lookup"], "answer": 1, "why": "Each decode step reads all weights and the KV cache to produce one token per user, so bandwidth, not compute, is the limit."},
  {"q": "A reply has a 0.5 s TTFT, a 20 ms TPOT and 501 tokens. Roughly how long does the whole reply take?", "options": ["0.5 s", "10.5 s", "20 s", "50 s"], "answer": 1, "why": "TTFT + TPOT x (N - 1) = 0.5 + 0.02 x 500 = 10.5 s."},
  {"q": "System A produces 10,000 tokens/s with half its requests missing the latency target. System B produces 7,000 tokens/s, all within target. Which has higher goodput?", "options": ["A", "B", "They are equal", "Goodput ignores latency"], "answer": 1, "why": "Goodput counts only work served within the targets: 7,000 for B against about 5,000 for A."},
  {"q": "A model has 32 layers, 8 KV heads, head dimension 128, 16-bit values. How much KV cache does a 4,000-token conversation need?", "options": ["About 50 MB", "About 500 MB", "About 5 GB", "About 50 GB"], "answer": 1, "why": "2 x 32 x 8 x 128 x 2 bytes = 128 KB per token; x 4,000 is about 512 MB."},
  {"q": "Your system prompt starts with today's date and time. What happens to prefix caching?", "options": ["Nothing", "Every request misses the cache, because the prefix changes", "Only decode slows down", "The KV cache gets smaller"], "answer": 1, "why": "Caching matches from the start of the prompt. Put stable content first and anything that changes last."},
  {"q": "Why does speculative decoding help less on a heavily loaded server?", "options": ["Its outputs get worse", "At high batch sizes the GPU's maths units are already busy, so drafting has little idle capacity to use", "The draft model stops working", "It disables the KV cache"], "answer": 1, "why": "It converts idle compute into tokens. Batching already fills that compute, as EAGLE-3's 1.38x gain at batch 64 against 6.5x single-request shows."},
  {"q": "An MoE model has 671B total and 37B active parameters. What sets its GPU memory needs and its per-token compute?", "options": ["37B for both", "671B for both", "Memory follows 671B; compute follows 37B", "Memory follows 37B; compute follows 671B"], "answer": 2, "why": "Every expert must be stored, but each token runs only through the experts the router picks."},
  {"q": "Users say the agent is slow. Traces show six sequential model calls per turn. What should you try first?", "options": ["A bigger GPU", "Remove or parallelise calls and stream the final answer", "Quantize the model", "Increase the context window"], "answer": 1, "why": "Sequential round trips dominate. Fix the pipeline before touching the model."}
]
```
