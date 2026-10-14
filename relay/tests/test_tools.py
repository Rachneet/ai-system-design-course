import pytest

from app.tools import REGISTRY, ToolError, get_order, issue_refund, request_refund_approval, search_kb, specs


async def test_order_lookup_is_scoped_to_the_customer(ctx):
    assert "Order 1042: delivered" in await get_order(ctx, 1042)
    with pytest.raises(ToolError, match="No order 2210"):
        await get_order(ctx, 2210)  # belongs to c_91


async def test_refund_within_window_and_limit(ctx, store):
    assert "Refunded $45.00" in await issue_refund(ctx, 1042, 45.0, "torn fly")
    assert (await store.refund_for(1042))["amount"] == 45


async def test_refund_is_idempotent(ctx, store):
    await issue_refund(ctx, 1042, 45.0, "torn fly")
    assert "already refunded" in await issue_refund(ctx, 1042, 45.0, "torn fly")


async def test_used_tent_outside_30_days_is_refused(ctx):
    with pytest.raises(ToolError, match="return window is 30 days"):
        await issue_refund(ctx, 5520, 189.0, "leaks")


async def test_unused_item_has_60_day_window(ctx):
    assert "Refunded" in await issue_refund(ctx, 5521, 120.0, "wrong size")


@pytest.mark.parametrize("amount", [0, -5, 46.0])
async def test_refund_amount_must_be_within_order_total(ctx, amount):
    with pytest.raises(ToolError):
        await issue_refund(ctx, 1042, amount, "x")


async def test_refund_above_limit_needs_approval(ctx, store):
    with pytest.raises(ToolError, match="request_refund_approval"):
        await issue_refund(ctx, 3001, 640.0, "defective")
    assert "Approval request #" in await request_refund_approval(ctx, 3001, 640.0, "defective")
    assert await store.refund_for(3001) is None


async def test_shipped_order_cannot_be_refunded(ctx):
    with pytest.raises(ToolError, match="only delivered orders"):
        await issue_refund(ctx, 7001, 10.0, "changed mind")


async def test_search_kb_returns_cited_documents(ctx):
    out = await search_kb(ctx, "return window used tent")
    assert 'id="POL-RETURNS-2026"' in out


def test_tool_specs_are_sorted_and_strict():
    names = [s["name"] for s in specs()]
    assert names == sorted(names) and all(s["strict"] for s in specs())
    assert {t.tier for t in REGISTRY.values()} >= {"read", "write_bounded", "write_approval"}
