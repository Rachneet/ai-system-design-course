from prometheus_client import Counter

tickets = Counter("helpdesk_tickets_total", "Tickets opened", ["tenant"])
outcomes = Counter("helpdesk_ticket_outcomes_total", "Agent replies by outcome", ["tenant", "agent", "outcome"])
model_calls = Counter("helpdesk_model_calls_total", "Model calls through Switchboard", ["agent"])
tool_calls = Counter("helpdesk_tool_calls_total", "Tool calls through Checkpoint by outcome", ["agent", "outcome"])
handoffs = Counter("helpdesk_handoffs_total", "Handoffs between agents", ["source", "target"])
escalations = Counter("helpdesk_escalations_total", "Tickets passed to people", ["tenant", "reason"])
