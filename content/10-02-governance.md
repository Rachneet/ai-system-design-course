---
id: w10-governance
week: 10
kind: lesson
title: Governance and regulation for AI systems
short: Governance and regulation
minutes: 55
summary: The EU AI Act as it stands after the 2026 Digital Omnibus, the NIST AI RMF and its Generative AI Profile, and ISO/IEC 42001, translated into the artifacts engineers must produce (inventories, risk assessments, logs, human oversight, incident reporting, change control, retention) and the platform records that supply the evidence.
---

## Why it matters

Governance arrives in an engineering team as questions you have to answer with evidence: which AI systems do we run, what can each one do, who approved that, what did it do last Tuesday for this customer, and how fast can we tell a regulator about an incident? If the answers live in a spreadsheet someone updates before audits, they will be wrong. If they come from the systems that run the agents, they will be right by construction.

This lesson covers the three frameworks you will meet most, then turns them into a list of artifacts and shows where each one comes from on the platform you built in Weeks 7 to 9.

> [!warn] This lesson is not legal advice. It summarises primary sources so that you can build the right evidence and ask your legal team better questions. Whether a particular system is high-risk, or whether you are its provider or deployer, is a legal judgement for counsel.

## The EU AI Act

The AI Act is [Regulation (EU) 2024/1689](https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=OJ:L_202401689). It is a regulation, so it applies directly in every Member State, and it reaches anyone placing AI systems on the EU market or whose system's output is used in the EU. It sorts AI systems by risk, and treats general-purpose AI models (the large models you call through an API) as a separate track.

```viz
caption: Obligations scale with risk. Most helpdesk agents sit in the transparency tier; an HR agent that makes decisions about workers can move into high risk.
<div class="vz-panel sk b"><h5>Prohibited (Article 5)</h5><p>for example social scoring, emotion recognition at work or in education, untargeted scraping of facial images</p></div>
<div class="vz-panel sk w"><h5>High risk (Article 6, Annexes I and III)</h5><p>for example CV screening, decisions on promotion or termination, credit scoring, safety components of regulated products: risk management, logging, human oversight, conformity assessment</p></div>
<div class="vz-panel sk"><h5>Transparency (Article 50)</h5><p>chatbots must tell people they are talking to an AI; synthetic content must be marked; deep fakes disclosed</p></div>
<div class="vz-panel sk g"><h5>Minimal risk</h5><p>for example spam filters: no specific obligations</p></div>
<div class="vz-row"><span class="ch wide sk ghost">separate track: general-purpose AI models (Articles 51 to 55), obligations on model providers</span></div>
<div class="vz-src">Tiers and examples from the European Commission's <a href="https://digital-strategy.ec.europa.eu/en/policies/regulatory-framework-ai">AI Act overview</a> and the text of <a href="https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=OJ:L_202401689">Regulation (EU) 2024/1689</a>.</div>
```

### Providers and deployers

The Act assigns duties by role. A **provider** develops an AI system (or has it developed) and places it on the market or puts it into service under its own name. A **deployer** uses an AI system under its own authority. A company that builds a support agent on a hosted model and runs it for its own customers is usually the provider of that agent; the model vendor is the provider of the general-purpose model underneath. Roles can stack, and changing a system's intended purpose can change who is responsible, which is one reason to keep the inventory below accurate.

### What changed in 2026: the Digital Omnibus on AI

The original timeline put most high-risk obligations on 2 August 2026. The Commission proposed simplifications on 19 November 2025, and the co-legislators reached political agreement on 7 May 2026 ([Commission overview](https://digital-strategy.ec.europa.eu/en/policies/regulatory-framework-ai)). The result is [Regulation (EU) 2026/1744](https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=OJ:L_202601744), the "Digital Omnibus on AI", adopted on 8 July 2026, published in the Official Journal on 24 July 2026 and **in force since 27 July 2026** (its Article 4: the third day after publication). It is law, not a proposal. The changes engineers should know:

| Change | Before | After the Omnibus |
|---|---|---|
| High-risk systems in Annex III areas (employment, credit, education, biometrics and others) | 2 August 2026 | **2 December 2027** |
| High-risk systems in products under Annex I (for example toys and lifts) | 2 August 2027 | **2 August 2028** |
| New prohibitions: AI that generates non-consensual intimate imagery of identifiable people, or child sexual abuse material | none | **2 December 2026** |
| Marking of synthetic content (Article 50(2)) for systems already on the market before 2 August 2026 | 2 August 2026 | **2 December 2026** |
| AI literacy (Article 4) | Take measures to ensure "a sufficient level" of AI literacy of staff | "Take measures to support the development" of AI literacy; no specific level guaranteed |
| Fines for small mid-cap companies (SMCs) | Same caps as large companies | The lower of the amount or percentage (new Article 99(6a)) |

The rest of Article 50 was not postponed: it has applied since 2 August 2026.

### The timeline, as it stands in October 2026

```viz
caption: Prohibitions, AI literacy, model-provider duties and transparency already apply. The heavy high-risk obligations now start in December 2027 and August 2028.
<div class="vz-row"><span class="ch sk g">1 Aug 2024</span><span>the Act enters into force</span></div>
<div class="vz-row"><span class="ch sk g">2 Feb 2025</span><span>prohibitions, AI literacy</span></div>
<div class="vz-row"><span class="ch sk g">2 Aug 2025</span><span>model-provider duties, governance, penalties</span></div>
<div class="vz-row"><span class="ch sk g">27 Jul 2026</span><span>Digital Omnibus on AI in force</span></div>
<div class="vz-row"><span class="ch sk g">2 Aug 2026</span><span>general application; Article 50; fines on model providers</span></div>
<div class="vz-row"><span class="ch sk ghost">2 Dec 2026</span><span>two new prohibitions; Article 50(2) for older systems</span></div>
<div class="vz-row"><span class="ch sk ghost">2 Aug 2027</span><span>models released before 2 Aug 2025 comply</span></div>
<div class="vz-row"><span class="ch sk ghost">2 Dec 2027</span><span>high-risk: Annex III systems</span></div>
<div class="vz-row"><span class="ch sk ghost">2 Aug 2028</span><span>high-risk: Annex I product systems</span></div>
<div class="vz-row"><span class="ch sk ghost">2 Aug 2030</span><span>high-risk systems of public authorities</span></div>
<p>solid: already applies; dashed: still ahead</p>
<div class="vz-src">Article 113 and Article 111 of <a href="https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=OJ:L_202401689">Regulation (EU) 2024/1689</a>, as amended by Articles 1(39) and 1(40) of <a href="https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=OJ:L_202601744">Regulation (EU) 2026/1744</a>.</div>
```

### Transparency: Article 50

Article 50 is the part most agent teams meet first, and it already applies:

1. **Article 50(1):** providers must design systems that interact directly with people so that people are informed they are interacting with an AI system, unless that is obvious from the context. For a helpdesk agent, say so in the interface and at the start of a conversation, and do not let the agent claim to be human.
2. **Article 50(2):** providers of systems that generate synthetic audio, image, video or text must mark outputs in a machine-readable format so they are detectable as AI-generated, as far as technically feasible. There is an exception for assistive editing functions. The Commission's voluntary [Code of Practice on marking and labelling AI-generated content](https://digital-strategy.ec.europa.eu/en/policies/code-practice-ai-generated-content) is the practical guide; ask counsel how it applies to text replies in your product.
3. **Article 50(4):** deployers must disclose deep fakes, and AI-generated text published to inform the public on matters of public interest.

### High risk: what it would demand of a helpdesk

Most support agents are not high-risk. But Annex III point 4(b) lists AI systems "intended to be used to make decisions affecting terms of work-related relationships, the promotion or termination of work-related contractual relationships, to allocate tasks based on individual behaviour or personal traits or characteristics or to monitor and evaluate the performance and behaviour of persons in such relationships". An HR agent that answers policy questions is a different system from one that approves leave or flags employees for performance review.

Article 6(3) lets an Annex III system escape the high-risk label if it does not materially influence decisions, for example when it performs "a narrow procedural task" or "a preparatory task", but never when it profiles people, and Article 6(4) requires the provider to **document that assessment** before the system goes live. Scope is a design decision: keeping the HR agent out of decisions about workers keeps it out of high risk, and that boundary should be enforced in Checkpoint policy, not only in the prompt.

If a system is high-risk, these articles become engineering work:

| Article | Requirement (paraphrased; read the text) | Engineering artifact |
|---|---|---|
| 12 | Systems must "technically allow for the automatic recording of events (logs) over the lifetime of the system" | Request, decision and approval logs with trace IDs |
| 14 | Systems must be designed so that people can effectively oversee them while in use | Approval holds, a console, a kill switch, the ability to override |
| 26(6) | Deployers keep automatically generated logs under their control for at least six months, unless other law says otherwise | Retention settings, enforced by a job |
| 73 | Providers report serious incidents no later than 15 days after becoming aware; 2 days for widespread infringements or critical infrastructure disruption; 10 days in the event of a death | An incident runbook with a regulator-notification step and a clock |

### Penalties

```viz
caption: Fines are the higher of a fixed amount or a share of worldwide turnover. SMEs pay the lower of the two, and since the Omnibus so do small mid-caps for the second and third tiers.
<div class="vz-bars"><span>prohibited practices</span><span class="bar sk"><i class="sk b" style="--w:100%"></i></span><b>EUR 35M or 7%</b><span>most other obligations, including Article 50</span><span class="bar sk"><i class="sk b" style="--w:43%"></i></span><b>EUR 15M or 3%</b><span>misleading information to authorities</span><span class="bar sk"><i class="sk b" style="--w:21%"></i></span><b>EUR 7.5M or 1%</b><span>general-purpose model providers (Commission)</span><span class="bar sk"><i class="sk b" style="--w:43%"></i></span><b>EUR 15M or 3%</b></div>
<p>bar length: the fixed amount</p>
<div class="vz-src">Articles 99(3) to 99(6) and 101(1) of <a href="https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=OJ:L_202401689">Regulation (EU) 2024/1689</a>; Article 99(6a) inserted by <a href="https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=OJ:L_202601744">Regulation (EU) 2026/1744</a>.</div>
```

### General-purpose AI models: whose duty is it?

Article 53 obliges **model providers** to keep technical documentation, give downstream providers documentation of capabilities and limitations, have a copyright policy and publish a summary of training content. Models trained with more than 10^25 floating-point operations are presumed to have systemic risk (Article 51(2)) and carry further duties. If you call a hosted model, these duties sit with the vendor; your part is to **use** what they give you: keep the vendor's model documentation with your risk assessment, and record which model version each request used. If you fine-tune or substantially modify a model, ask counsel whether you have become a provider of a model.

## The NIST AI Risk Management Framework

The [NIST AI RMF 1.0](https://www.nist.gov/itl/ai-risk-management-framework), released on 26 January 2023, is voluntary guidance from the US National Institute of Standards and Technology. It organises AI risk work into four functions: **Govern** (policies, roles, culture), **Map** (context and risks of each system), **Measure** (analyse and track those risks) and **Manage** (prioritise and act). NIST states that it is revising the framework as part of the White House AI Action Plan; no revised version had been published at the time of writing.

The [Generative AI Profile, NIST AI 600-1](https://doi.org/10.6028/NIST.AI.600-1), released on 26 July 2024, applies the framework to generative AI. It names 12 risks that generative AI creates or makes worse, and maps suggested actions to the four functions. Five matter directly to a helpdesk:

| NIST AI 600-1 risk | In a helpdesk | Where you control it |
|---|---|---|
| Confabulation | Invents a refund rule or an IT procedure | Retrieval with citations, groundedness evals |
| Data privacy | Leaks one employee's HR case to another | Identity-scoped tools, Checkpoint policy, cross-tenant red-team |
| Information security | Prompt injection through a ticket or email | Checkpoint output scanning, least privilege, approvals |
| Human-AI configuration | Approvers click "approve" on everything | Approval rate and time metrics, sampling reviews |
| Value chain and component integration | A third-party MCP server or skill changes behaviour | Atlas review, pinned versions and digests |

## ISO/IEC 42001

[ISO/IEC 42001:2023](https://www.iso.org/standard/42001) is the international standard for an **AI management system**: requirements for establishing, implementing, maintaining and continually improving how an organisation governs the AI it builds, provides or uses. It is built like ISO/IEC 27001 for information security, and like it, organisations can be certified against it by an accredited third party. For engineers, a 42001 audit asks the same thing as the others: show the process, and show the records that prove you followed it.

```viz
caption: Three frameworks, one evidence base. Law sets duties, NIST describes the risk work, ISO certifies the management system; all three ask for the same records.
<div class="vz-cols" style="--k:3">
  <div class="vz-panel sk c"><h5>EU AI Act</h5><p>binding law; duties by risk tier and role; fines</p></div>
  <div class="vz-panel sk c"><h5>NIST AI RMF and 600-1</h5><p>voluntary; Govern, Map, Measure, Manage; 12 generative AI risks</p></div>
  <div class="vz-panel sk c"><h5>ISO/IEC 42001</h5><p>certifiable management system; audited process</p></div>
</div>
<span class="arr d sk"></span>
<div class="vz-row"><span class="ch sk m">inventory</span><span class="ch sk m">risk assessments</span><span class="ch sk m">logs</span><span class="ch sk m">oversight records</span><span class="ch sk m">incidents</span><span class="ch sk m">change history</span><span class="ch sk m">retention</span></div>
```

## What engineers must actually produce

Strip the frameworks down and seven artifacts remain. Each one should be generated by the platform, not typed up before an audit.

| Artifact | What it must contain | Where it comes from on the platform |
|---|---|---|
| **AI inventory** | Every agent, model, tool server and skill; owner; purpose; risk tier; version | Atlas: artifacts with owner team, version, digest and status; Switchboard: which apps call which models |
| **Risk assessment per system** | Intended purpose, risk tier and reasoning (including any Article 6(3) assessment), NIST 600-1 risks, mitigations, residual risk | A file in the agent's repository, linked from its Atlas entry and reviewed in the golden pipeline |
| **Logs** | What the system did, when, for whom, with which model and policy | Switchboard `usage_events` (model, tokens, cost, fallback per request); Checkpoint `decisions` (agent, user, tool, decision, policies); traces |
| **Human oversight** | Who approved which action, on what exact arguments; how to stop the system | Checkpoint `approvals` (bound to agent, user, tool and argument digest, `decided_by`); kill switches |
| **Incident reporting** | Detection, triage, a decision on notification, and the timeline | Alerts and runbooks from Week 5, plus a regulator-notification step with the Article 73 clock |
| **Change control** | Every change to model, prompt, tool, skill or policy: who, when, reviewed by whom, eval result | Git history and the eval gate (Week 4); immutable Atlas versions; Switchboard `admin_audit`; Checkpoint policy file in git |
| **Data retention** | How long each record is kept, and proof that deletion happens | Switchboard `retention_days` per app (1 to 400) and `purge-expired`; a retention job for every other table |

```viz
caption: Each obligation maps to a record a platform service already writes. The gaps are what you build next.
<div class="vz-cols">
  <div class="vz-panel sk"><h5>Obligation</h5>
    <div class="vz-row"><span class="ch sk">inventory</span></div>
    <div class="vz-row"><span class="ch sk">logs</span></div>
    <div class="vz-row"><span class="ch sk">human oversight</span></div>
    <div class="vz-row"><span class="ch sk">change control</span></div>
    <div class="vz-row"><span class="ch sk">retention</span></div>
  </div>
  <div class="vz-panel sk g"><h5>Platform record</h5>
    <div class="vz-row"><span class="ch sk g">Atlas artifacts and audit</span></div>
    <div class="vz-row"><span class="ch sk g">Switchboard ledger, Checkpoint decisions</span></div>
    <div class="vz-row"><span class="ch sk g">Checkpoint approvals</span></div>
    <div class="vz-row"><span class="ch sk g">git, Atlas versions, admin audit</span></div>
    <div class="vz-row"><span class="ch sk b">bodies only; decisions keep forever</span></div>
  </div>
</div>
<p>gaps in the reference services: no risk-tier field in Atlas, no retention job for Checkpoint decisions or Atlas audit</p>
```

### Change control for models and prompts

A model upgrade or a prompt edit changes behaviour as much as a code change, so it goes through the same path, with evidence attached:

1. The change is a pull request: a new model pin in `models.yaml`, a prompt file, a skill version, or a Cedar rule.
2. The eval gate runs and its report is attached to the pull request (Week 3 and Week 4).
3. A reviewer who is not the author approves. For skills and tool servers, Atlas enforces this: a reviewer can never approve their own submission.
4. The deploy pins the exact artifact: image digest, prompt hash, model ID. Every trace records them.
5. The change log is the git history plus Atlas and Switchboard audit tables, so "what changed on 3 March?" is a query.

> [!rule] Never point production at a model alias that the vendor can move. A pinned model ID is the only way your logs can say which model produced an answer, and the only way an eval result still describes what is running.

### Logs and personal data pull in opposite directions

Regulators want logs; data protection law wants you to keep less. Design for both:

- Log **metadata** for every request (who, which model, which tool, which policy, cost, latency) and keep it for the period your counsel sets, at least six months for high-risk systems under Article 26(6).
- Log **content** (prompts and responses) only where needed, redacted, with a short expiry. Switchboard does this: bodies are stored only when an app opts in, always redacted, and expire after the app's `retention_days`.
- Prove deletion: a scheduled purge job, its metrics, and a test that a record past its expiry is gone.

## Failure modes

| Failure | How it shows up | Mitigation |
|---|---|---|
| Inventory drift | An agent runs in production that nobody listed | Derive the inventory from gateway traffic and Atlas, not from a form; alert on unknown apps |
| Compliance documents detached from the system | The risk assessment describes last year's tools | Keep it in the repository; the pipeline fails if tools change without updating it |
| Rubber-stamp approvals | 99% of holds approved in under five seconds | Track approval rate and time; sample approved actions for review |
| Logs kept forever | Personal data in prompt logs from three years ago | Expiry on every content table; purge job with metrics |
| Logs too thin | An incident cannot be reconstructed | Trace ID on every record; model, prompt hash and policy IDs on every decision |
| Missed incident clock | Nobody owns the regulator notification | Runbook step with a named owner and the deadline |
| Silent scope creep | The HR agent starts recommending dismissals | Policy forbids the tools; red-team cases for the boundary; re-run the Article 6 assessment on every new tool |

## Design review questions

> [!interview] List every AI system you run. Where does that list come from, and how would you find one that is missing?

> [!interview] Which of your agents could be high-risk under Annex III, and what stops each one from crossing that line?

> [!interview] A customer asks why the agent denied their refund on 12 March. Walk me through the records you would pull.

> [!interview] How do you tell users they are talking to an AI, and what test proves it still happens after a prompt change?

> [!interview] How long do you keep prompts and responses, and how do you prove they are deleted?

> [!interview] A serious incident happens on a Friday evening. Who decides whether to notify a regulator, and by when?

## Further reading

- [Regulation (EU) 2024/1689, the AI Act](https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=OJ:L_202401689), and [Regulation (EU) 2026/1744, the Digital Omnibus on AI](https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=OJ:L_202601744). Read Articles 5, 6, 12, 14, 26, 50, 73 and 113.
- The European Commission's [AI Act overview](https://digital-strategy.ec.europa.eu/en/policies/regulatory-framework-ai) and [questions and answers](https://digital-strategy.ec.europa.eu/en/faqs/navigating-ai-act).
- [NIST AI RMF](https://www.nist.gov/itl/ai-risk-management-framework) and the [Generative AI Profile, NIST AI 600-1](https://doi.org/10.6028/NIST.AI.600-1).
- [ISO/IEC 42001:2023](https://www.iso.org/standard/42001).
- The [architecture review](#w6-review) format, for running a governance review alongside a design review.

```quiz
[
  {"q": "What is the legal status of the Digital Omnibus on AI in October 2026?", "options": ["A Commission proposal under negotiation", "A political agreement awaiting a vote", "Regulation (EU) 2026/1744, in force since 27 July 2026", "Withdrawn"], "answer": 2, "why": "It was adopted on 8 July 2026, published on 24 July 2026 and entered into force three days later."},
  {"q": "From when do the high-risk obligations apply to an Annex III system such as a CV-screening tool, after the Omnibus?", "options": ["2 August 2026", "2 December 2026", "2 December 2027", "2 August 2028"], "answer": 2, "why": "Article 113(c)(i), as amended, sets 2 December 2027 for Annex III; Annex I product systems follow on 2 August 2028."},
  {"q": "Your customer-support chatbot launched in September 2026. Which Article 50 duty already applies to it?", "options": ["None until 2027", "Informing people they are interacting with an AI system, unless obvious", "A conformity assessment", "Registration as a general-purpose model"], "answer": 1, "why": "Article 50 has applied since 2 August 2026; only Article 50(2) marking for systems already on the market before that date got until 2 December 2026."},
  {"q": "An HR agent answers questions about the leave policy. A proposed new tool lets it flag employees for performance review. Why does that matter?", "options": ["It does not", "Monitoring and evaluating workers' performance is an Annex III use case, so the system may become high-risk", "It changes the model provider's duties", "HR data cannot be used by AI at all"], "answer": 1, "why": "Annex III point 4(b) covers monitoring and evaluating the performance of people at work. Re-run the Article 6 assessment before adding the tool."},
  {"q": "Which record best proves human oversight of a large refund?", "options": ["The system prompt says to ask a human", "A Checkpoint approval bound to the agent, user, tool and exact arguments, with who decided and when", "A Slack message", "The model's reasoning trace"], "answer": 1, "why": "Oversight evidence must tie a named person's decision to the exact action executed."},
  {"q": "What are the four functions of the NIST AI RMF?", "options": ["Plan, Do, Check, Act", "Govern, Map, Measure, Manage", "Identify, Protect, Detect, Respond", "Inform, Optimize, Operate, Report"], "answer": 1, "why": "AI RMF 1.0 organises risk work into Govern, Map, Measure and Manage."},
  {"q": "Why should prompt and response bodies have a shorter retention than request metadata?", "options": ["They are larger", "Metadata answers most audit questions, while bodies hold personal data that data protection law says to minimise", "Regulators forbid storing bodies", "Bodies cannot be redacted"], "answer": 1, "why": "Keep the evidence regulators need without keeping more personal data than necessary."}
]
```
