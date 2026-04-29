# Agent Loop Strategy

## Goal

The agent should answer policy and document questions by repeatedly checking whether the available evidence is enough, not by stopping after a fixed number of keyword hits. The loop should make explicit decisions about local search, web verification, and answer readiness.

## Proposed Loop

1. Understand the question and produce an initial plan.
   - Identify the user intent.
   - Extract likely search terms.
   - Detect whether the answer depends on current policy, dates, money, ratios, thresholds, or official sources.

2. Run local search.
   - Search local Markdown files with the current terms.
   - Merge and rank evidence by source path and score.

3. Evaluate evidence after each round.
   - Decide whether the local evidence answers the question.
   - Identify missing facts such as year, amount, ratio, process, eligibility, or official source.
   - Decide whether web verification is required.
   - Generate next search terms only when the evidence has a clear gap.

4. Continue or stop.
   - Stop when evidence is sufficient.
   - Continue local search when the missing facts can plausibly be found locally.
   - Use web search when the question is time-sensitive, official-current, or local evidence is weak.
   - Stop when the round limit is reached, but record that evidence may be incomplete.

5. Verify web evidence when needed.
   - Prefer official sources.
   - Fetch page body when configured.
   - Cross-check dates, ratios, amounts, and policy year against local evidence.

6. Write the answer.
   - Answer directly in Chinese.
   - Separate local and web evidence when relevant.
   - State uncertainty when evidence is incomplete or stale.
   - Include sources.

## Relationship To Common Agent Patterns

### Plan-and-Solve

This is the strongest match. The agent first creates a search plan, then solves the problem by executing the plan through local search, web verification, and answer synthesis.

The current project already has a lightweight version of this in `QueryPlanner.initial_plan()`. The missing part is that the plan is not revised by evidence quality.

### ReAct

This design uses a constrained form of ReAct:

- Reason: evaluate whether the evidence is enough and what is missing.
- Act: run local search, run web search, fetch pages, or answer.
- Observe: inspect local hits and web pages before deciding the next action.

It is not a full open-ended ReAct agent because tools are fixed and bounded. That is intentional: the project is a policy/document query CLI, so deterministic tool boundaries are safer than arbitrary tool use.

### Reflection

The evidence evaluation step is a lightweight reflection pass. It checks:

- Does the evidence answer the question?
- Is the evidence current enough?
- Are there conflicts between sources?
- Is web verification required?
- What exact facts are missing?

The design does not add a second LLM critique after answer generation yet. That can be added later if answer quality remains weak.

## Implementation Shape

Add an `EvidenceEvaluator` boundary with one method:

```python
evaluate(question, terms, local_sources, rounds, plan) -> EvidenceDecision
```

The decision should include:

- `is_sufficient`: whether the agent can stop local search.
- `needs_web`: whether web verification is required.
- `next_terms`: terms for the next local search round.
- `missing_facts`: short labels for unresolved information.
- `reason`: a short explanation useful for debugging.

The default evaluator should be deterministic so tests and offline use remain stable. A later LLM-backed evaluator can use the same interface and return the same structured decision.

## Expected Improvement

The old loop stopped when it found three local documents. The new loop stops when an evaluator says the evidence is enough. For questions like "上海公积金是如何缴存的", the evaluator should notice that official yearly details such as basis, ratio, and amount limits are important, and should require web verification when current policy is involved.
