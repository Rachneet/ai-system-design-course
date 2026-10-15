// Checkpoint policies (Cedar). Default deny: a tool is unreachable until a permit names it.
// Principal: Agent::"<agent id>"  Resource: Tool::"<server>__<tool>"  Actions: list, call
// Context: { args: <tool arguments>, user: { id, roles }, server: "<MCP server name>" }

// Every agent may see and call read-only weather tools.
@id("weather-read")
permit(principal, action, resource == Tool::"weather__get_forecast");

// The refunds agent may see the refund tool, and call it for support staff up to 200.
@id("refunds-see-refund")
permit(principal == Agent::"refunds", action == Action::"list", resource == Tool::"payments__refund");

@id("refunds-small")
permit(principal == Agent::"refunds", action == Action::"call", resource == Tool::"payments__refund")
when { context.user.roles.contains("support") && context.args.amount <= 200 };

// Larger refunds are allowed only after a person approves that exact call.
@id("refunds-large-need-approval")
@approval("required")
permit(principal == Agent::"refunds", action == Action::"call", resource == Tool::"payments__refund")
when { context.user.roles.contains("support") && context.args.amount > 200 && context.args.amount <= 2000 };

// Nobody refunds their own account, whatever else allows it.
@id("no-self-refund")
forbid(principal, action == Action::"call", resource == Tool::"payments__refund")
when { context.args has customer_id && context.args.customer_id == context.user.id };
