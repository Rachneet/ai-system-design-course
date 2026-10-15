"""Each model does what its lesson claims."""

import numpy as np

from uth import bpe, kv_cache, lora, sampling, test_time


def test_bpe_round_trips_and_charges_unseen_languages_more():
    tok = bpe.BPE.train(bpe.CORPUS, 512)
    for text in [*bpe.SAMPLES.values(), "emoji 🙂 and digits 1042"]:
        assert tok.decode(tok.encode(text)) == text  # bytes underneath: nothing is ever unknown
    per_char = {lang: len(tok.encode(t)) / len(t) for lang, t in bpe.SAMPLES.items()}
    assert per_char["English"] < per_char["German"] < per_char["Hindi"]
    assert len(tok.encode(bpe.SAMPLES["English"])) < len(bpe.SAMPLES["English"].encode()) / 2


def test_kv_cache_gives_identical_tokens_with_far_less_attention_work():
    m = kv_cache.TinyDecoder()
    prompt = list(range(1, 21))
    m.attn_dot_products = 0
    slow = m.generate(prompt, 40, use_cache=False)
    naive_work = m.attn_dot_products
    m.attn_dot_products = 0
    fast = m.generate(prompt, 40, use_cache=True)
    assert slow == fast and m.attn_dot_products * 10 < naive_work


def test_a_cached_prefix_gives_the_same_logits_as_computing_everything():
    m = kv_cache.TinyDecoder()
    system, user = list(range(1, 17)), [30, 31, 32]
    prefix = kv_cache.Cache()
    m.forward(system, 0, prefix)
    reused = m.forward(user, len(system), prefix.copy())
    fresh = m.forward(system + user, 0, kv_cache.Cache())
    assert np.allclose(reused, fresh)


def test_kv_bytes_match_the_inference_lesson():
    assert kv_cache.kv_bytes_per_token(80, 8, 128) == 327_680  # Llama 3 70B, BF16
    assert kv_cache.kv_bytes_per_token(32, 8, 128) == 131_072


def test_temperature_and_top_p():
    logits = sampling.LOGITS
    assert sampling.probabilities(logits, 0)[0] == 1.0
    hot, cold = sampling.probabilities(logits, 1.5), sampling.probabilities(logits, 0.7)
    assert hot[0] < cold[0] and np.isclose(hot.sum(), 1)
    kept = sampling.top_p(sampling.probabilities(logits, 1.0), 0.9)
    assert np.count_nonzero(kept) == 3 and np.isclose(kept.sum(), 1)
    assert round(sampling.pass_hat_k(0.9, 8), 2) == 0.43 and sampling.pass_at_k(0.9, 8) > 0.99


def test_lora_starts_as_a_no_op_learns_the_tenant_and_merges_exactly():
    rng = np.random.default_rng(1)
    w = rng.normal(0, 1 / 8, (64, 64))
    layer = lora.LoRALinear(w, r=4, alpha=8, rng=rng)
    x = rng.normal(0, 1, (5, 64))
    assert np.allclose(layer(x), x @ w)  # B is zero
    tx, ty = lora.task(rng, w, rank=2)
    losses = layer.train(tx, ty)
    assert losses[-1] < losses[0] / 100 and np.array_equal(layer.w, w)
    assert np.allclose(layer(x), x @ layer.merged()) and layer.trainable() == 2 * 64 * 4


def test_voting_helps_only_when_wrong_answers_disagree():
    assert test_time.vote_accuracy(0.6, 9, 4, trials=4000) > 0.85
    assert test_time.vote_accuracy(0.4, 9, 1, trials=4000) < 0.4
    models = {"s": {"acc": {"e": 1.0, "h": 0.0}, "cost": 1.0}, "b": {"acc": {"e": 1.0, "h": 1.0}, "cost": 10.0}}
    acc, cost = test_time.route({"e": 0.5, "h": 0.5}, {"e": "s", "h": "b"}, models)
    assert (acc, cost) == (1.0, 5.5)
