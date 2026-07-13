# Coding Guidelines

> A shared team guide for writing efficient, readable, and correct code.
> Centered on universal, language-agnostic principles, with language-specific examples where helpful.

---

## Table of Contents

1. [Core Philosophy](#1-core-philosophy)
2. [Naming Conventions](#2-naming-conventions)
3. [Function Design](#3-function-design)
4. [Readability](#4-readability)
5. [Comments and Documentation](#5-comments-and-documentation)
6. [Error Handling](#6-error-handling)
7. [Efficiency and Performance](#7-efficiency-and-performance)
8. [Ensuring Correctness](#8-ensuring-correctness)
9. [Testing](#9-testing)
10. [Structure and Architecture](#10-structure-and-architecture)
11. [Version Control and Collaboration](#11-version-control-and-collaboration)
12. [Security Fundamentals](#12-security-fundamentals)
13. [Code Review Checklist](#13-code-review-checklist)

---

## 1. Core Philosophy

- **Code is read far more often than it is written.** Write for the reader — including yourself six months from now.
- Improve in this order: **working code → correct code → readable code → fast code.** Avoid premature optimization.
- **KISS (Keep It Simple, Stupid)**: Prefer the simplest solution that works.
- **DRY (Don't Repeat Yourself)**: The same knowledge/logic should not be duplicated in multiple places. However, do not force together code that is only coincidentally similar (beware of premature abstraction).
- **When you're about to copy-paste a block you just wrote (or find yourself matching an existing block character-for-character), stop and unify instead**: extract a shared function/factory/component and call it from both sites, rather than leaving two copies. Before writing new UI/style/logic that looks like something already in the codebase, search for an existing shared helper (e.g., a factory class/module) and reuse or extend it first.
- **YAGNI (You Aren't Gonna Need It)**: Do not build features you don't need yet.
- **Consistency beats personal preference.** If the project already has an established style, follow it.

---

## 2. Naming Conventions

### 2.1 Principles

- A name alone should reveal its **role and intent**.
- Use pronounceable, searchable names. (`d`, `tmp2`, `data` ❌)
- Only use abbreviations the team has agreed on. (`idx`, `cfg`, `req` are generally acceptable.)
- Prefer positive names over negative ones. (`isNotValid` ❌ → `isValid` ✅)

### 2.2 Conventions

| Target | Rule | Example |
|---|---|---|
| Variables, functions | Verb/noun + camelCase or snake_case (follow language convention) | `userCount`, `fetch_orders()` |
| Booleans | Prefix with `is/has/can/should` | `isActive`, `hasPermission` |
| Classes/types | Noun, PascalCase | `OrderService`, `PaymentResult` |
| Constants | UPPER_SNAKE_CASE | `MAX_RETRY_COUNT` |
| Collections | Plural | `users`, `orderItems` |
| Functions | Start with a verb; state exactly what it does | `calculateTotalPrice()`, `sendWelcomeEmail()` |

### 2.3 Bad → Good

```python
# ❌ Bad
def proc(d):
    r = []
    for i in d:
        if i[2] > 30:
            r.append(i)
    return r

# ✅ Good
def filter_adult_users(users: list[User]) -> list[User]:
    return [user for user in users if user.age > ADULT_AGE_THRESHOLD]
```

---

## 3. Function Design

- **A function should do one thing** (Single Responsibility Principle).
- Keep functions to **one screen (roughly 20–40 lines)**. If longer, consider splitting.
- **Prefer 3 or fewer parameters.** If there are more, group them into an object/struct.
- **Minimize side effects.** Separate functions that compute values from functions that change state (Command–Query Separation).
- Favor **pure functions** that return the same output for the same input.
- Avoid flag arguments (`doSomething(true)`); split the function or use an explicit options object instead.
- Use **early returns** to reduce nesting.

```javascript
// ❌ Deep nesting
function processOrder(order) {
  if (order) {
    if (order.isPaid) {
      if (order.items.length > 0) {
        // actual logic
      }
    }
  }
}

// ✅ Early returns
function processOrder(order) {
  if (!order) return;
  if (!order.isPaid) return;
  if (order.items.length === 0) return;
  // actual logic
}
```

---

## 4. Readability

- Keep **indentation depth to 2–3 levels**. If it gets deeper, extract a function.
- Limit line length to **80–120 characters** (follow team standard).
- **No magic numbers**: replace them with meaningful constants.

```java
// ❌
if (user.age >= 19) { ... }

// ✅
private static final int LEGAL_ADULT_AGE = 19;
if (user.age >= LEGAL_ADULT_AGE) { ... }
```

- Keep related code **close together** and separate unrelated code with **blank lines**.
- Extract complex conditionals into **meaningful variables or functions**.

```python
# ❌
if user.age >= 19 and user.verified and not user.banned and user.balance > 0:
    ...

# ✅
def can_make_purchase(user: User) -> bool:
    is_eligible = user.age >= LEGAL_ADULT_AGE and user.verified
    is_in_good_standing = not user.banned and user.balance > 0
    return is_eligible and is_in_good_standing

if can_make_purchase(user):
    ...
```

- Integrate formatters (Prettier, Black, gofmt, etc.) and linters (ESLint, Ruff, Checkstyle, etc.) **into CI** to end style debates with tooling.

---

## 5. Comments and Documentation

### 5.1 Principles

- **Good code explains itself.** Before writing a comment, try improving names and structure first.
- Comments should explain "**why**," not "**what**."

```python
# ❌ Comment that merely repeats the code
i += 1  # increment i by 1

# ✅ Comment that explains context/intent
# The external payment API expects 1-indexed pages, not 0-indexed
page_number = index + 1
```

### 5.2 When Comments Are Required

- Non-obvious business rules and legal/policy constraints
- Code that intentionally looks "odd" for performance or other reasons
- Workarounds for bugs in external systems (include a link to the related issue)
- Write `TODO`/`FIXME` with an owner and issue number: `# TODO(hong, #123): add cache invalidation`

### 5.3 Documentation

- Write **docstrings/JSDoc/Javadoc** for public APIs and library functions (parameters, return values, exceptions, usage examples).
- `README.md` should include at minimum: project purpose, installation/run instructions, environment variables, and how to run tests.
- **Update comments and docs together with code changes.** A stale comment is worse than no comment.

---

## 6. Error Handling

- **Never ignore errors.** Empty `catch` blocks are forbidden.

```java
// ❌ Never do this
try { doSomething(); } catch (Exception e) { }

// ✅ At minimum log; recover or propagate when possible
try {
    doSomething();
} catch (PaymentException e) {
    log.error("Payment processing failed: orderId={}", orderId, e);
    throw new OrderProcessingException("Payment failed.", e);
}
```

- Catch **specific exceptions**. Don't indiscriminately catch top-level `Exception`.
- Use exceptions only for **exceptional situations**, never for normal control flow.
- Make failure visible in the signature of functions that can fail (e.g., `Optional`, `Result`, declared exceptions, Go's `error` return).
- **Never trust input.** Validate external input (users, APIs, files) at the boundary.
- Error messages should include **cause + context + remediation**. (`"Error occurred"` ❌ → `"Payment failed for order #123: card limit exceeded. Please try another payment method."` ✅)
- Always release resources (files, connections, locks) using `try-with-resources`, `with`, `defer`, `finally`, etc.

---

## 7. Efficiency and Performance

### 7.1 Principles

- **Don't optimize without measuring.** Profile first, then fix the bottleneck.
- Algorithm and data structure choices matter far more than micro-optimizations that hurt readability.

### 7.2 Practices

- **Be conscious of time complexity.** Watch out for nested loops and DB calls inside loops (the N+1 problem).

```python
# ❌ O(n²): repeated list scans
for order in orders:
    if order.user_id in [u.id for u in users]:  # rebuilds the list every time
        ...

# ✅ O(n): use a set/dict
user_ids = {u.id for u in users}
for order in orders:
    if order.user_id in user_ids:
        ...
```

- Pick the right data structure: lookup-heavy → hash map/set, ordered → list, priority → heap.
- **Reduce unnecessary I/O**: use batching, caching, and pagination appropriately.
- For large datasets, process via **streaming/generators** instead of loading everything into memory.
- Query only the columns you need, and consider indexes for frequently used conditions.
- When improving performance, **record before/after numbers** (benchmarks, APM metrics, etc.).

---

## 8. Ensuring Correctness

- **Always check boundary conditions**: empty collections, `null`/`None`, 0, negative numbers, maximum values, Unicode/emoji strings, etc.
- **Leverage types aggressively**: define narrow types in statically typed languages; use type hints/TypeScript in Python/JS.
- Default to **immutable data**, allowing mutable state only where change is genuinely needed.
- In concurrent code, minimize shared mutable state and use proven patterns: locks, channels, immutable messages.
- **Never compute money with floating point** (use `Decimal`, `BigDecimal`, or integer minor units).
- Always make time zones **explicit**; store timestamps in UTC by default.
- Keep compiler/linter warnings at **zero**. Warnings are latent bugs.

---

## 9. Testing

- **Write tests alongside new features.** When fixing a bug, write a reproducing test first.
- Structure tests with the **AAA pattern** (Arrange–Act–Assert / Given–When–Then).

```python
def test_order_total_is_sum_of_item_prices_and_shipping_fee():
    # Given (Arrange)
    order = Order(items=[Item(price=10000)], shipping_fee=3000)

    # When (Act)
    total = order.calculate_total()

    # Then (Assert)
    assert total == 13000
```

- Test names should state the **behavior under test and the expected result**.
- Each test verifies **one concept only**.
- Tests must be **independent** and must not depend on execution order.
- Isolate external dependencies (DB, network, time) with mocks/stubs/fakes, but also verify real integrations with integration tests.
- Coverage is only a reference metric. **Covering core logic and boundary conditions matters more than the number.**
- **Never merge with failing tests.** Fix or quarantine flaky tests immediately.

---

## 10. Structure and Architecture

- **Separate concerns**: split presentation (UI), business logic, and data access into layers.
- **Dependencies point inward (toward the domain)**: business logic must not depend on framework or DB details.
- Keep coupling between modules low (loose coupling) and cohesion within modules high (high cohesion).
- Depend on interfaces (abstractions), not implementations (Dependency Inversion).
- Avoid global state and singleton abuse; ensure testability through **dependency injection**.
- Never hardcode configuration (URLs, keys, thresholds); externalize it into **environment variables/config files**.
- If circular dependencies appear, revisit the design.

---

## 11. Version Control and Collaboration

### 11.1 Commits

- Keep commits **small and logical**. One commit = one intent.
- Commit messages should explain **why** the change was made. Recommended format (Conventional Commits):

```
feat: refund points automatically when an order is canceled

- Refund used points at the moment cancellation is approved
- Partial cancellations refund proportionally (issue #245)
```

- Prefix examples: `feat` (feature), `fix` (bug), `refactor`, `test`, `docs`, `chore`

### 11.2 Branches and PRs

- Never commit directly to `main`; merge **through PRs**.
- Keep PRs at a **reviewable size** (ideally under 300–400 changed lines).
- PR descriptions should include the reason for the change, key changes, and how to test.
- Keep feature work and large-scale refactoring/formatting in **separate PRs**.

---

## 12. Security Fundamentals

- **Never commit secrets (API keys, passwords, tokens) to code or the repository.** Use environment variables or a secrets manager.
- Validate all external input, and use **parameter binding** (prepared statements) for SQL. Never build queries with string concatenation.
- Prevent XSS by **escaping output** (use your framework's built-in mechanisms).
- Never store passwords in plaintext; use **proven hashes like bcrypt/argon2**.
- Regularly audit dependency vulnerabilities (`npm audit`, `pip-audit`, Dependabot, etc.).
- Mask personal data and secrets so they never appear in logs.
- Perform authorization checks **on the server side**. Client-side validation is only a UX aid.

---

## 13. Code Review Checklist

Items to check yourself — and for reviewers to verify — before merging:

### Correctness
- [ ] Does it meet the requirements? Are boundary conditions handled (empty values, null, 0, max values)?
- [ ] Are errors properly handled, propagated, and logged?
- [ ] Any risk of concurrency issues (race conditions, deadlocks)?

### Readability
- [ ] Can you tell what things do from their names alone?
- [ ] Does each function do one thing? Is nesting kept to 3 levels or fewer?
- [ ] Are magic numbers replaced with constants?
- [ ] Do comments explain "why"? Are there any stale comments?

### Efficiency
- [ ] No unnecessary repeated computation, N+1 queries, or excessive memory use?
- [ ] Are the data structure choices appropriate?

### Testing
- [ ] Is new logic covered by tests? Is there a reproducing test for bug fixes?
- [ ] Are tests independent, with clear names?

### Security
- [ ] No secrets included?
- [ ] External input validated, SQL parameterized, output escaped?

### Maintainability
- [ ] No duplicated code? Were existing utilities/modules reused?
- [ ] Were docs (README, API docs) updated along with the code?

---

## Appendix: Official/Representative Style Guides by Language

| Language | Guide |
|---|---|
| Python | PEP 8, Google Python Style Guide |
| JavaScript/TypeScript | Airbnb Style Guide, Google TS Style Guide |
| Java | Google Java Style Guide |
| Go | Effective Go, Go Code Review Comments |
| Kotlin | Kotlin Coding Conventions (official) |
| C++ | Google C++ Style Guide, C++ Core Guidelines |
| Rust | The Rust Style Guide (official) |

> This is a living document. Keep updating it as your team's experience grows.
