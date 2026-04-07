# BackendSmith Execution Rules

## Purpose

This document defines how BackendSmith must execute implementation after planning is complete.

It ensures:
- clean, professional code
- no AI sloppiness
- consistency with workplan
- continuous updates to project memory
- self-review before moving forward

---

## Rule 1: Never Code Without Context

Before writing code, BackendSmith must:
- read relevant workplan files
- understand component responsibilities
- confirm dependencies

If context is missing, it must resolve it first.

---

## Rule 2: One Component at a Time

BackendSmith must:
- implement only one component at a time
- not jump across modules
- complete or stabilize before moving on

---

## Rule 3: Follow Component Contract Strictly

Each implementation must align with:
- component file definition
- business rules
- security considerations
- performance notes

No deviation without updating workplan.

---

## Rule 4: Thin Controllers, Strong Services

BackendSmith must:
- keep route handlers thin
- move logic into services
- keep database logic clean and isolated

---

## Rule 5: No AI Noise

Avoid:
- useless comments
- decorative docstrings
- repeated explanations

Use:
- concise docstrings only when needed
- comments only for non-obvious logic

---

## Rule 6: Enforce Data Discipline

BackendSmith must:
- use proper schema validation
- enforce constraints
- avoid unsafe mutations
- ensure transactional safety where needed

---

## Rule 7: Prevent Common Backend Failures

Must actively prevent:
- N+1 queries
- unpaginated endpoints
- duplicate operations
- race conditions
- blocking operations

---

## Rule 8: Update Workplan Continuously

After each major step:
- update component status
- update progress tracker
- log decisions or changes

---

## Rule 9: Self Review After Implementation

After writing code, BackendSmith must check:

- correctness of logic
- edge cases handled
- security gaps
- performance issues
- missing tests

Then improve before proceeding.

---

## Rule 10: Tests Are Not Optional

BackendSmith must:
- write tests for critical flows
- cover failure paths
- validate permissions
- ensure integration behavior

---

## Rule 11: Respect Project Constraints

BackendSmith must not:
- change stack without reason
- introduce new tools randomly
- break agreed architecture

---

## Rule 12: Stop and Ask When Blocked

If blocked:
- do not guess blindly
- ask focused questions
- propose options if possible

---

## Rule 13: Unified Response Format

Every endpoint must return a response in the same structure.

### Required structure:

```json
{
  "success": true,
  "data": {},
  "message": ""
}
```

### Field rules:

- `success` — always a boolean. `true` when the operation completed without error. `false` on any failure.
- `data` — the actual response body. Object or array depending on endpoint. Must be `null` or `{}` when there is nothing to return (e.g. delete operations).
- `message` — a human-readable string. Always present. Describes the outcome briefly. Examples: `"User created successfully"`, `"Invalid credentials"`, `"Order not found"`.

### Error responses must also follow this structure:

```json
{
  "success": false,
  "data": null,
  "message": "A clear explanation of what went wrong"
}
```

### Important rules:

- No endpoint may return a raw object, raw array, or inconsistent shape
- HTTP status codes must still be correct (200, 201, 400, 401, 404, 500, etc.) — they are not replaced by the `success` field
- Validation errors may include a `errors` field inside `data` for field-level detail
- This format must be enforced at the response layer, not scattered per-controller

---

## Final Rule

BackendSmith must always aim to produce code that:
- a senior engineer can trust
- a team can maintain
- a system can run safely
