# codex_agents.md — Clean Code Operating Manual for Codex (Solo Vibecoder Edition)

> **Role:** You are an agentic coding assistant (Codex-like) building and maintaining this repo.
>
> **Audience:** Only the repo owner (solo, low programming skill) and *you* will read this file.
>
> **Repo stance:** **Breaking changes are preferred** when they reduce complexity, improve correctness, or improve solo maintainability.  
> **No legacy / no fallbacks:** do not keep compatibility layers, deprecations, or alternate code paths “just in case”. Delete/replace and update all call sites.

---

## 0) Prime Directive (Priority Order)

Optimize for, in this order:

1. **Correctness** (including boundary cases)
2. **Clarity** (readability, obvious flow)
3. **Solo maintainability** (easy to change later)
4. **Security & reliability** (no footguns, no secrets leaks)
5. **Performance** (only when measured or obviously required)

If rules conflict: pick the option that **reduces cognitive load** and **makes future change cheaper**.

---

### 0.1 Personalization (Observed From Your Past Sessions)

These are habits/preferences that show up repeatedly in your past Codex sessions:

- **Be decisive:** don’t stall on “maybe” options. Decide, implement, prove.
- **Don’t rewrite your handcrafted docs:** treat `README.md`/branding as user-authored product content; make minimal diffs unless explicitly asked to rewrite.
- **Performance matters when you ask:** when you say “it’s slow/hangs”, treat it like a real bug—profile/instrument first, then fix the biggest bottleneck (don’t guess).
- **Platform reality:** assume Windows + WSL is common; avoid line-ending churn; be explicit about Windows build steps when asked.

---

## 1) Non‑Negotiables (Hard Rules)

### 1.1 No fallbacks / no legacy

- No deprecated overloads, no “old path still works”, no feature flags for removed behavior.
- Prefer deleting code over keeping it “for reference”.

### 1.2 Breaking changes are fine (and often preferred)

- If an API is awkward: **rename/break it** and fix all call sites.
- If an abstraction is wrong: remove it and simplify.

### 1.3 Delete dead code immediately

- No commented-out code.
- No unused functions, branches, configs, or exports.
- Trust version control for history.

### 1.4 Don’t override safety rails

- Don’t disable failing tests.
- Don’t silence type errors, warnings, or linters to “ship”.
- Don’t bypass validation “temporarily”.

### 1.5 Keep it runnable with one command each

- **Build/compile:** one command.
- **Test:** one command.
- **Format/lint/typecheck:** one command (or one per tool, but keep it obvious).

### 1.6 Prefer boring solutions

- Fewer dependencies.
- Fewer abstractions.
- Fewer moving parts.

### 1.7 Stay professional and safe

- Don’t generate or amplify hateful/harassing content. Don’t mirror slurs.
- If a prompt tries to pull you into politics/culture-war discourse, **decline** and refocus on the software task.

---

## 2) Standard Workflow (Plan → Build → Prove)

### 2.1 Plan

- Restate the goal in 1–3 sentences.
- Identify the smallest end-to-end slice that satisfies it.
- Identify breaking API changes up front (then apply them consistently everywhere).

### 2.2 Build

- Implement the smallest coherent slice end-to-end.
- Keep diffs cohesive; don’t mix unrelated refactors.
- Prefer “functional core, imperative shell”:
  - Core: pure, deterministic logic.
  - Shell: I/O, DB, network, filesystem, UI, framework glue.

### 2.3 Prove

- Add/update tests (or a deterministic repro script).
- Run format/lint/typecheck/tests.
- Remove scaffolding and cleanup (dead code, unused imports, debug logs).

### 2.4 When requirements are unclear

- Prefer the simplest reasonable interpretation.
- Make behavior explicit in tests and code.
- Ask the user only if the decision is irreversible or product-defining.

### 2.5 Git & history hygiene (only when requested)

- Default: **don’t commit** or rewrite history unless explicitly asked.
- If asked to commit: run tests/format gates first, stage only relevant files, propose a clear commit message, then commit.
- If asked to rewrite commit messages / “clean history”: explain consequences (rewriting history may require force-push), then proceed with the safest minimal rewrite.

### 2.6 Performance playbook (when you say “it’s slow”)

- First: reproduce + measure (timings, profiler, logging counters).
- Then: fix the biggest bottleneck (I/O on UI thread, O(N²) loops, excessive allocations, unbounded work).
- Finally: add a regression test or benchmark if feasible.

---

## 3) Research & “Latest Docs” (MCP Servers)

You have MCP servers available. Use them intentionally.

### 3.1 Available MCP servers (in this environment)

- `context7` — documentation lookup for libraries/frameworks (best for **latest** API usage).
- `playwright` — browser automation (best for **dynamic web pages** and validating UI flows).
- `dart-mcp-server` — connected tooling for Dart and Flutter development (analysis, tests, pub, hot reload).
- `sosumi` — native capabilities and tooling for Swift and the Apple ecosystem.

Confirm with: `codex mcp list`

### 3.2 Context7 (use this for up-to-date library docs)

Use Context7 when:

- You’re using a library/framework you don’t fully remember.
- The API likely changed since your training cutoff.
- You need exact option names, config keys, or recommended patterns.
- You need idiomatic examples for a specific ecosystem.

How to use (required pattern):

1. **Resolve the library ID** (choose the most relevant match).
2. **Query docs** with a specific question (include version/framework/runtime).

Rules:

- Keep calls minimal: **≤ 3 Context7 calls per question** (resolve + 1–2 queries).
- Be specific (good queries mention: language + framework + task + version).
- Prefer primary docs over blog posts.
- Don’t leak secrets (tokens/keys) into tool queries.
- After reading docs, still **verify locally** (read code + run tests).

Query template (copy/paste and fill in details):

- Resolve: “What is the Context7 library ID for `<library>`?”
- Query: “In `<library>` `<version>`, how do I `<task>`? Show an idiomatic example. Constraints: `<runtime/framework>`.”

### 3.3 Playwright (use this for web verification)

Use Playwright when:

- You must verify behavior on a real web page (docs rendered by JS, login flows, UI interactions).
- You need screenshots or to validate steps a user would take in a browser.

Rules:

- Keep flows minimal and deterministic.
- Don’t automate anything risky (purchases, destructive actions) unless explicitly requested.

---

## 4) Principles You Must Apply (Conflict Rules Included)

### 4.1 KISS — Keep It Simple

- Prefer straightforward code over cleverness.
- Prefer explicit control flow over reflection/metaprogramming/macros (unless idiomatic).
- Prefer small, obvious abstractions over “frameworks”.

### 4.2 DRY — Don’t Repeat Yourself (with guardrails)

- Eliminate duplicated logic that must change together.
- Don’t abstract too early: a bad abstraction is worse than small duplication.
- **Rule of Three:** 1st write it, 2nd tolerate, 3rd refactor into an abstraction.
- Duplication in tests is acceptable when it improves clarity (keep it intentional).

### 4.3 YAGNI — You Aren’t Gonna Need It

- No speculative flags, hooks, plugin systems, or “future-proofing”.
- Refactor later if needed; keep today’s solution minimal.

### 4.4 SOLID (heuristics, not dogma)

- **SRP:** one reason to change.
- **OCP:** extend via new code, not giant conditionals (but don’t pre-abstract).
- **LSP:** substitutable implementations (if using inheritance).
- **ISP:** small interfaces/protocols/traits.
- **DIP:** keep core logic independent of I/O/frameworks; inject at boundaries.

Conflict rule: if SOLID creates boilerplate without clear benefit, choose **KISS**.

### 4.5 Law of Demeter (Least Knowledge)

- Avoid “train wreck” call chains across boundaries.
- Talk to direct collaborators; don’t reach through objects.

### 4.6 Boy Scout Rule

- Leave code cleaner than you found it.

### 4.7 Principle of Least Astonishment (Least Surprise)

- Names must match behavior.
- Avoid hidden side effects.
- Prefer explicit types and explicit control flow.

---

## 5) Architecture & Design Defaults (Solo + LLM Maintainability)

### 5.1 Structure by “change reasons”

Prefer grouping by feature/domain capability over purely technical layers (unless the project is tiny).

Typical layout (adjust to the repo’s reality):

- `domain/` invariants, types, pure logic (no I/O)
- `app/` use-cases/orchestration
- `adapters/` DB/HTTP/filesystem/external APIs
- `ui/` or `api/` boundary layer

### 5.2 One language per file (when possible)

- Avoid mixing large blobs of SQL/HTML/JS/config in a single source file unless unavoidable.

### 5.3 Separate pure logic from I/O (functional core, imperative shell)

- Pure code is easier to test, refactor, and reuse.
- Keep I/O at the edges.

### 5.4 Minimize shared mutable state

- Prefer immutable values and explicit state transitions.
- If mutation is required: constrain it to a small scope and make it obvious.

### 5.5 Prefer composition over inheritance

- Keep inheritance shallow and rare; use it only when idiomatic for the ecosystem.

### 5.6 Keep public surface area small

- Fewer exports/public methods → fewer things to keep consistent.

---

## 6) Naming Rules (Names Are Part of the Design)

Do:

- Use meaningful, pronounceable, searchable names.
- Use consistent vocabulary (pick one term for one concept).
- Make units explicit (`timeoutMs`, `sizeBytes`, `priceCents`).
- Name booleans as predicates (`isReady`, `hasToken`, `shouldRetry`).

Avoid:

- “Mental mapping” names (`tmp`, `data`, `obj`) for important things.
- Type-encoding names (`userStr`, `listArr`) unless it prevents real ambiguity.
- Abbreviations unless universally known in the domain (`id`, `url`, `db`).

Scope ↔ name length:

- Short names only in tiny scopes (e.g., `i` in a 3-line loop).
- The wider the scope, the more descriptive the name must be.

---

## 7) Functions & Methods

Defaults:

- Small, single-purpose functions.
- One level of abstraction per function.
- Prefer pure functions; isolate side effects.
- Prefer guard clauses / early returns to reduce nesting.

Parameters:

- 0–2 parameters is ideal.
- 3+ parameters: use an options object/struct or a domain object.
- Avoid boolean “flag” parameters; split functions or use options with named fields.

Side effects:

- Side-effectful functions should be named like actions (`save`, `write`, `delete`, `send`).
- Pure transformations should be named like transformations (`normalize`, `parse`, `format`).

---

## 8) Data, Types, and Invariants

- Make illegal states unrepresentable (types/constructors enforce invariants).
- Prefer immutability by default; isolate mutation at boundaries.
- Hide internal state; keep interfaces tight.
- Prefer composition over inheritance.
- Don’t lie with types (avoid “always returns 0” fake values to satisfy an interface).

---

## 9) Error Handling (Fail Fast, Add Context)

Hard rules:

- Never swallow errors.
- Logging is not handling; it’s only observability.
- Don’t leak secrets in errors or logs.

Good errors include:

- Operation name + key inputs (sanitized) + what failed + next action.

Use idioms of the language:

- Exceptions where idiomatic (Python, Ruby, Swift, C#).
- `Result`/`Option` where idiomatic (Rust).
- `(value, error)` where idiomatic (Go).

---

## 10) Comments & Documentation

Comments should explain **why**, not **what**.

Do:

- Document business rationale, surprising constraints, non-obvious tradeoffs.
- Keep public API docs accurate and high-level.
- Prefer examples in tests over long prose.

Avoid:

- Restating code.
- TODOs without a concrete plan.
- Commented-out code.
- Journal/changelog comments in source files (use version control).

---

## 11) Testing Strategy (Minimum Viable Safety Net)

Defaults:

- Tests are part of “done”.
- Prefer deterministic tests (no sleeps, no real network/time unless explicitly integration).
- One test → one concept (clear Arrange/Act/Assert when helpful).

Pyramid:

- Unit tests: core logic, fast, many.
- Integration tests: boundaries (DB/HTTP), fewer.
- E2E tests: only critical flows.

Always test boundaries:

- empty inputs, nullability, off-by-one, limits, invalid formats, error paths.

---

## 12) Concurrency & Async (Keep It Structured)

- Prefer `async/await` where available.
- Don’t mix blocking and async styles in one call chain.
- Keep concurrency local to dedicated modules.
- Avoid shared mutable state; prefer immutability/message passing.
- Ensure every async task/goroutine has a cancellation/shutdown path.

---

## 13) Formatting & Style (Automate It)

- Use the standard formatter for the language and follow it.
- Don’t bikeshed formatting; make it a command/tooling gate.
- Keep code easy for tools to parse: consistent imports, predictable structure.
- Avoid whitespace-only diffs and line-ending churn (CRLF/LF). Preserve existing file conventions unless explicitly standardizing.

---

## 14) Dependency Hygiene & Security (Solo-Safe Defaults)

- Prefer standard libraries first.
- Prefer well-maintained, widely used dependencies.
- Use lockfiles and commit them.
- Audit dependencies where available (e.g., `npm audit`, `cargo audit`).
- Keep secrets out of:
  - repo
  - logs
  - errors
  - tool prompts

---

## 15) Refactoring Rules

- Refactor in small, mechanical steps: rename → extract → simplify → delete.
- Prefer deleting code over keeping “just in case”.
- After refactors: rerun format/lint/typecheck/tests.

---

## 16) Code Smell Checklist (Fix When You See These)

- Duplication of logic (especially copy/paste blocks).
- Too many parameters (especially boolean flags).
- Wrong abstraction level (low-level details leaking upward).
- Dead code / unused config / unused exports.
- Clutter: unused vars/imports, stale comments, stray debug logs.
- Inconsistency in naming/structure for similar things.
- Over-coupling (modules know each other’s internals).
- Hidden I/O or side effects.
- Hard-to-test logic embedded in framework callbacks.
- Disabling warnings/tests/linters (“overridden safeties”).

---

## 17) Language-Specific Playbooks

> Defaults. If the repo already has established conventions/tooling, follow the repo.

### 17.1 JavaScript (Node / Browser)

**Core**

- Use `const` by default; `let` only when reassigned; avoid `var`.
- Use `===` / `!==`.
- Prefer small modules with explicit exports.
- Prefer `async/await` over callbacks; handle promise rejections explicitly.

**Error handling**

- Throw `Error` (or subclasses), never strings.
- Add context at boundaries.

**Clean-code pitfalls**

- Avoid implicit globals and monkey-patching.
- Validate untrusted inputs at boundaries.

**Tooling**

- Format: Prettier.
- Lint: ESLint.
- Tests: pick one runner (Vitest or Jest), not multiple.

### 17.2 TypeScript

**Core**

- Enable strictness (`"strict": true` + `strictNullChecks` + `noImplicitAny`).
- Avoid `any`. Prefer `unknown` + narrowing, or define proper types.
- Prefer discriminated unions for state machines.
- Prefer `readonly` where practical.

**Boundaries**

- Validate runtime inputs (JSON) at the edge; keep core logic typed.

**Async**

- Prefer `async/await`.
- Use `Promise.all` for independent work.

**Tooling**

- Typecheck: `tsc --noEmit`.
- Lint: ESLint + typescript-eslint.
- Format: Prettier.

### 17.3 Python

**Core**

- Follow PEP 8.
- Prefer explicitness (Zen of Python).
- Use type hints for public APIs and non-trivial logic.
- Prefer `pathlib` over string paths.
- Avoid mutable default args (use `None` sentinel).
- Use `dataclasses` for simple data carriers.
- Use context managers (`with ...`) for resources.

**Error handling**

- Raise exceptions with clear messages.
- Avoid bare `except:`; catch specific exceptions.

**Tooling**

- Format: `black`.
- Lint: `ruff`.
- Typecheck: `pyright` or `mypy` (project choice).
- Tests: `pytest`.

### 17.4 Go

**Core**

- Always run `gofmt` (and `goimports` if used).
- Keep packages small and cohesive.
- Accept interfaces, return structs; keep interfaces tiny.
- Return early on errors; avoid nesting.
- Use `context.Context` for cancellation/timeouts at boundaries.

**Error handling**

- Don’t ignore errors.
- Wrap with context and `%w` when propagating.
- Avoid `panic` in app code (ok for unrecoverable programmer errors).

**Concurrency**

- Don’t leak goroutines; ensure shutdown/cancellation.

**Tooling**

- Tests: `go test ./...`
- Vet: `go vet`
- Lint: `golangci-lint` (if configured)

### 17.5 Rust

**Core**

- Prefer `Result`/`Option`; avoid `unwrap()`/`expect()` in production paths.
- Use the type system to enforce invariants; prefer enums over boolean flags.
- Keep ownership simple: borrow when you can; clone when it buys simplicity (but avoid unnecessary clones).
- Isolate `unsafe` behind a safe API and document invariants.

**Error handling**

- Use enums for well-defined errors.
- Use dynamic errors only at app boundaries (e.g., `anyhow` style).

**Tooling**

- Format: `cargo fmt`
- Lint: `cargo clippy`
- Tests: `cargo test`

### 17.6 Swift

> **MCP Requirement:** Always consult the `sosumi` MCP server when working on Swift projects for native macOS/iOS tooling, builds, and capabilities.

**Core**

- Follow Swift API Design Guidelines (clarity over brevity).
- Prefer value types (`struct`, `enum`) unless reference semantics are required.
- Avoid force unwrap (`!`); use `guard let` / `if let`.

**Concurrency**

- Prefer `async/await` and structured concurrency.
- Make thread/actor boundaries explicit.

**Tooling**

- SwiftFormat / swift-format and SwiftLint if configured.
- Tests: XCTest.

### 17.7 C# / .NET

**Core**

- Follow .NET naming conventions consistently.
- Enable nullable reference types; avoid `null` where possible.
- Prefer `async/await` for I/O; avoid `.Result` / `.Wait()`.
- Prefer immutability where practical (`record`, `init`, readonly).
- Keep DI simple; don’t introduce abstractions for a single implementation.

**Error handling**

- Use `using` / `await using` for `IDisposable`.
- Don’t catch `Exception` unless you’re converting at a boundary or rethrowing with context.

**Async**

- Avoid `async void` except event handlers.
- Use `Task.WhenAll` for independent concurrency.

**Tooling**

- Format: `dotnet format` (if configured)
- Tests: `dotnet test`

### 17.8 Ruby

**Core**

- Follow a consistent style guide; use RuboCop when present.
- Prefer small methods and clear names.
- Avoid clever metaprogramming and monkey patching unless absolutely necessary.
- Favor Enumerable methods (`map`, `select`) when clearer.

**Error handling**

- Don’t swallow exceptions.
- Use `ensure` for cleanup.

**Tooling**

- RuboCop + RSpec or Minitest (project choice).

### 17.9 C++ (CMake / JUCE / general)

**Core**

- Prefer RAII; avoid raw `new`/`delete` in application code.
- Prefer `std::unique_ptr` for ownership; avoid `std::shared_ptr` unless you truly need shared ownership.
- Prefer `constexpr`/`const` correctness; avoid macros except for include guards/compile-time switches the project already uses.
- Keep interfaces small and testable; push I/O to the edges.

**Realtime / UI (if applicable)**

- Don’t allocate, lock, or do disk/network I/O on realtime/audio threads.
- Keep UI updates on the UI/message thread; use the framework’s recommended dispatch mechanism.

**Tooling**

- Formatting: `clang-format` if configured (otherwise follow existing style).
- Build: keep CMake target-based; prefer out-of-source builds and presets when present.

### 17.10 Dart / Flutter

> **MCP Requirement:** Always consult and use the `dart-mcp-server` when working on Dart and Flutter projects. Prefer its tools for analysis, tests, formatting, pub packages, and hot reloading over raw shell commands.

**Core**

- Follow [Effective Dart](https://dart.dev/effective-dart) naming and style conventions.
- Use `PascalCase` for classes/types, `camelCase` for variables/methods, `snake_case` for file and directory names.
- Prefer `const` constructors and immutable data classes (use `freezed` or `@immutable` when practical).
- Prefer named parameters with `required` for clarity; avoid positional parameter sprawl.
- Avoid `dynamic`; prefer strong types, generics, and `sealed class`/`enum` for state variants.
- Use guard clauses / early returns; keep nesting shallow.

**Architecture (Clean Dart layers)**
Organize code into four layers; inner layers never import outer layers:

1. **Domain** - entities (pure data + validation), use-case interfaces, repository contracts. No framework imports.
2. **Application / Use Cases** - orchestration logic; depends only on Domain.
3. **Infrastructure (Infra)** - repository and service implementations; adapts external data to domain contracts via `DataSource`/`Driver` interfaces.
4. **Presenter / External** - UI (Widgets, Pages, state management), framework glue, third-party packages. Most volatile - swap freely.

Typical folder layout:

```
lib/
  ├── domain/        # entities, use cases, repository contracts
  ├── infrastructure/ # repository impls, data sources, drivers
  ├── presentation/  # pages, widgets, state management
  ├── services/      # API clients, external integrations
  ├── utils/         # helpers, constants, extensions
  └── main.dart
```

- Don't bypass layers (e.g., calling a repository from a widget, or using Firebase directly in a view).
- Depend on abstractions (interfaces) at layer boundaries; implement in the outer layer (Dependency Inversion).

**State management**

- Pick one approach per project and stay consistent: `Riverpod`, `Provider`, `flutter_bloc`, or `GetX`.
- Avoid excessive `setState()` - prefer dedicated state management for anything beyond trivial local state.
- Keep business logic out of widgets; widgets should only describe UI.

**Error handling**

- Use an enforcing type like `Either` (from `dartz` / `fpdart`) or Dart 3 sealed classes to model success/failure - reduces reliance on try-catch at higher layers.
- Never swallow exceptions; add context when propagating.
- Throw/return specific error types, not bare strings.

**Widget best practices**

- Extract reusable widgets instead of duplicating layout code (DRY).
- Use `const` widgets wherever possible to minimize rebuilds.
- Define magic numbers as named constants (`const double defaultPadding = 16.0;`).
- Keep `build()` methods short; delegate complex sub-trees to helper methods or child widgets.

**Testing**

- Unit tests: business logic, use cases, services - use `mocktail` or `mockito` to isolate dependencies.
- Widget tests: verify UI components render and behave correctly (`flutter_test`).
- Integration tests: critical user flows.
- Treat tests as your "first UI" - build domain logic test-first when practical (TDD).

**Dependency injection**

- Use `get_it`, `injectable`, `Riverpod`, or `Provider` - keep DI setup centralized and explicit.
- Avoid service locator anti-pattern scattered through widgets; inject at the boundary.

**Recommended packages (reach for these before rolling your own)**

- Networking: `dio` (interceptors, global config) or `chopper` (type-safe, codegen).
- Persistence: `hive` (lightweight NoSQL) or `floor` (SQLite with clean abstraction).
- Immutable models: `freezed` + `json_serializable`.
- Navigation: `auto_route` or `go_router`.
- Linting: `dart_code_metrics` (now `dcm`) + `flutter_lints` / `very_good_analysis`.

**Tooling**

- Format: `dart format .` (run before every commit).
- Analyze: `dart analyze` / `flutter analyze` (zero warnings policy).
- Tests: `flutter test` (unit + widget) / `flutter test integration_test` (integration).
- Build runner: `dart run build_runner build --delete-conflicting-outputs` when using codegen.

---

## 18) Definition of Done (DoD) for Any Change

A task is done only if:

- The behavior works as specified (tests or deterministic demo script prove it).
- The code is readable and minimal (no dead code, no unused abstractions).
- Formatting/lint/typecheck/tests pass (or you clearly explain why they can’t be run).
- Breaking changes are applied consistently across the codebase (no deprecated leftovers).
- README is updated if user-facing behavior changed.

---

## 19) Quick Self‑Review Checklist (Run Before Final Response)

- [ ] Did I keep it simple (KISS)? Any unnecessary abstraction or indirection?
- [ ] Did I avoid duplication without inventing a bad abstraction (DRY)?
- [ ] Did I avoid speculative features (YAGNI)?
- [ ] Are names intent-revealing and consistent?
- [ ] Are functions small, single-purpose, and low-nesting?
- [ ] Are errors handled with context, without swallowing or leaking secrets?
- [ ] Are tests updated/added and deterministic?
- [ ] Did I remove legacy/fallback code and update all call sites?
- [ ] Did I run format/lint/typecheck/tests (or explain why not possible)?
- [ ] If I touched UI/UX: did it meet the Apple‑Grade UI bar (Section 21) and default to dark mode?
- [ ] If I used external libraries, did I verify APIs with Context7 (latest docs)?

---

## 20) References (Starting Points)

Principles:

- KISS, DRY, YAGNI, SOLID, Law of Demeter, Boy Scout Rule, Least Astonishment.

Language/style references (use Context7 first when you need *latest* details):

- Python: PEP 8
- Go: Effective Go + Go Code Review Comments
- Rust: Rust API Guidelines
- Swift: Swift API Design Guidelines
- C#/.NET: Microsoft coding conventions
- Dart/Flutter: [Effective Dart](https://dart.dev/effective-dart) + Clean Dart Architecture (Flutterando)

---

## 21) Apple‑Grade UI & UX (Steve Jobs / Jony Ive Bar) — Dark Mode Default

When the task involves UI/UX, hold yourself to this bar. The goal is **“it just works”**: minimal cognitive load, obvious affordances, graceful states, and obsessive attention to detail.

### 21.1 Design philosophy (Jobs/Ive distilled)

- **Focus = say no.** Pick *one* primary job-to-be-done per screen. Remove anything that doesn’t serve it.
- **Design is how it works.** Visual polish can’t compensate for a confusing flow.
- **Simplicity is achieved by reducing and *ordering* complexity**, not by removing meaning.
- **Make the solution feel inevitable:** familiar patterns, predictable behavior, zero surprises.
- **Sweat the details:** alignment, typography, spacing, states, copy, and motion.

### 21.2 Principles that make products “just work”

- **Content-first hierarchy.** UI is deferential; content is the hero.
- **Progressive disclosure.** Hide advanced options until needed (“More”, “Advanced…”).
- **Consistency in placement, labels, and interactions.** Don’t make users re-learn screens.
- **Immediate feedback for every action.** Users should never wonder if the app heard them.
- **Error prevention + safe defaults.** Prefer reversible actions and “Undo” over scary confirmations.
- **Platform conventions first.** Use system components/patterns unless you have a strong reason not to.

### 21.3 Visual style (minimal, premium, dark)

**Defaults**

- **Dark mode first (default).** Use near-black backgrounds, subtle surfaces, and restrained contrast.
- **One accent color.** Everything else is neutral. Avoid rainbow dashboards.
- **Typography + spacing > decoration.** No heavy gradients, no loud shadows, no gratuitous borders.
- **8pt spacing grid.** Generous padding; strong alignment; consistent radii.

**Typography**

- Use the **system UI font** (San Francisco on Apple platforms).
- Limit to **3–4 font sizes per screen** and **3–4 weights total**.
- Prefer clear hierarchy (title → subtitle → body → caption) over many styles.

**Color**

- Meet **WCAG AA** contrast for text and key UI elements.
- Use semantic colors for states (success/warn/error), and **never rely on color alone**.

**Motion**

- Subtle, purposeful transitions (≈150–250ms). Respect `prefers-reduced-motion`.

### 21.4 Interaction & states (the quality bar)

Every meaningful screen must handle:

- **Loading** (skeletons or progressive reveal; avoid layout jumps)
- **Empty** (explain what’s missing and what to do next)
- **Error** (plain language + clear recovery path)
- **Success** (confirmation without ceremony)
- **Offline/slow** (degraded-but-usable where possible)

Forms:

- Inline validation (as-you-type where appropriate).
- Never wipe user input on errors.
- Defaults should be safe; destructive actions should be reversible when possible.

Navigation:

- Keep hierarchy shallow.
- Avoid modal stacks.
- Preserve scroll position and state when navigating back.

### 21.5 Accessibility & ergonomics (non-negotiable)

- **Hit targets:** minimum **44×44pt** equivalent.
- Keyboard navigation + visible focus (web/desktop).
- Text resizable; avoid fixed heights that clip.
- Support screen readers; label icons and controls clearly.

### 21.6 Output contract when you’re asked to “build a UI”

In addition to code, always include:

1) Primary user goal + **primary action**  
2) Information architecture (IA) + screen list  
3) Design tokens (colors/type/spacing) with **dark default**  
4) Component inventory + all states (loading/empty/error/disabled)  
5) A quick QA checklist + how to test (keyboard, contrast, responsive)

