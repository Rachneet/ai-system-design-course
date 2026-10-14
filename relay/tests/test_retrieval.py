from app.retrieval import or_query, principals_for, rrf
from app.tools import search_kb


def test_rrf_rewards_agreement():
    assert rrf(["a", "b", "c"], ["c", "a", "d"])[:2] == ["a", "c"]


def test_or_query_drops_stopwords():
    assert or_query("How do I return a used tent?") == "return | used | tent"
    assert or_query("the a an") is None


async def test_customers_never_retrieve_internal_documents(retriever):
    for mode in ("vector", "lexical", "hybrid"):
        hits = await retriever.search("refund fraud signals review", principals_for("c_77"), mode=mode)
        assert all(not h.doc_id.startswith("INT-") for h in hits), mode
    staff_hits = await retriever.search("refund fraud signals review", principals_for("s_1", staff=True))
    assert "INT-REFUND-FRAUD" in {h.doc_id for h in staff_hits}


async def test_exact_identifiers_are_found_lexically(retriever):
    hits = await retriever.search("BOOT-GRN sizing", principals_for("c_77"), mode="lexical")
    assert hits[0].doc_id in {"PROD-GRANITE-BOOTS", "FAQ-BOOT-SIZING"}


async def test_search_tool_records_retrieved_ids(ctx):
    out = await search_kb(ctx, "return window used tent")
    assert 'id="POL-RETURNS-2026"' in out and "POL-RETURNS-2026" in ctx.retrieved
