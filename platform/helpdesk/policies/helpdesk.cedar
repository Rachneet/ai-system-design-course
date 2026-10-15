// Helpdesk OS policies for Checkpoint. Default deny: a tool is unreachable until a permit names it.
// Principal: Agent::"<agent id>"  Resource: Tool::"<system>__<tool>"  Actions: list, call
// Context: { args, user: { id, roles, tenant }, agent: { tenant }, server: "<MCP server name>" }
// Checkpoint already refuses a tenant-bound agent acting for another tenant's user; the forbids below are a second,
// independent wall around each tenant's systems. Triage agents have no tools: they route, specialists act.

// ---------- Tenant walls ----------

@id("idp-is-employee-only")
forbid(principal, action, resource)
when { context.server == "io.helpdesk/idp" && context.user.tenant != "employee" };

@id("orders-is-customer-only")
forbid(principal, action, resource)
when { context.server == "io.helpdesk/orders" && context.user.tenant != "customer" };

// ---------- Shared systems: knowledge base and ticketing ----------

@id("specialists-read-kb")
permit(principal, action, resource == Tool::"kb__search_articles")
when { [Agent::"it-access", Agent::"hr-policy", Agent::"billing", Agent::"returns"].contains(principal) };

@id("specialists-read-tickets")
permit(principal, action, resource == Tool::"ticketing__get_ticket")
when { [Agent::"it-access", Agent::"hr-policy", Agent::"billing", Agent::"returns"].contains(principal) };

// Writes to tickets: the specialists that change things record what they did. The HR agent is read-only.
@id("acting-specialists-write-tickets")
permit(principal, action, resource)
when {
  [Agent::"it-access", Agent::"billing", Agent::"returns"].contains(principal) &&
  [Tool::"ticketing__add_note", Tool::"ticketing__resolve_ticket"].contains(resource)
};

// ---------- Employee desk: IT access ----------

@id("it-sees-idp")
permit(principal == Agent::"it-access", action == Action::"list", resource)
when { context.server == "io.helpdesk/idp" };

// The caller's own account only: unlocking someone else's account is the classic social-engineering request.
@id("it-own-account")
permit(principal == Agent::"it-access", action == Action::"call", resource)
when {
  [Tool::"idp__get_account", Tool::"idp__unlock_account"].contains(resource) &&
  context.args has user_id && context.args.user_id == context.user.id
};

@id("it-standard-groups")
permit(principal == Agent::"it-access", action == Action::"call", resource == Tool::"idp__request_group_access")
when {
  context.args has user_id && context.args.user_id == context.user.id && context.args has group &&
  ["vpn-users", "design-tools", "analytics-readers", "wiki-editors"].contains(context.args.group)
};

@id("it-sensitive-groups-need-approval")
@approval("required")
permit(principal == Agent::"it-access", action == Action::"call", resource == Tool::"idp__request_group_access")
when {
  context.args has user_id && context.args.user_id == context.user.id && context.args has group &&
  ["finance-admins", "prod-admins", "hr-records"].contains(context.args.group)
};

// ---------- Customer desk: billing and returns ----------

@id("billing-sees-orders")
permit(principal == Agent::"billing", action == Action::"list", resource)
when { context.server == "io.helpdesk/orders" && resource != Tool::"orders__create_return" };

@id("billing-reads-orders")
permit(principal == Agent::"billing", action == Action::"call", resource)
when { [Tool::"orders__list_orders", Tool::"orders__get_order"].contains(resource) };

@id("refunds-up-to-50")
permit(principal == Agent::"billing", action == Action::"call", resource == Tool::"orders__refund")
when { context.args has amount_cents && context.args.amount_cents <= 5000 };

@id("refunds-up-to-500-need-approval")
@approval("required")
permit(principal == Agent::"billing", action == Action::"call", resource == Tool::"orders__refund")
when { context.args has amount_cents && context.args.amount_cents > 5000 && context.args.amount_cents <= 50000 };

@id("refunds-above-500-are-for-people")
forbid(principal, action == Action::"call", resource == Tool::"orders__refund")
when { context.args has amount_cents && context.args.amount_cents > 50000 };

@id("returns-sees-orders")
permit(principal == Agent::"returns", action == Action::"list", resource)
when { context.server == "io.helpdesk/orders" && resource != Tool::"orders__refund" };

@id("returns-calls")
permit(principal == Agent::"returns", action == Action::"call", resource)
when { [Tool::"orders__list_orders", Tool::"orders__get_order", Tool::"orders__create_return"].contains(resource) };
