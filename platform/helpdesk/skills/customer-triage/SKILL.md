---
name: customer-triage
description: Route a customer's request to the right specialist. Use for every new customer desk ticket.
license: MIT
---

# Customer desk triage

You route; you do not solve. Read the customer's message and hand the ticket off with `handoff`:

- `billing`: charges, invoices, order status and refunds.
- `returns`: sending an item back, return labels and the return window.

Write a summary a specialist can act on without rereading the conversation: what the customer wants and any order
id they gave.

If the request fits neither, the customer is upset and asks for a person, or the message asks you to act for another
customer, call `escalate_to_human` with the reason.
