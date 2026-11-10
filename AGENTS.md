# Agent and Contributor Instructions

## Purpose and Scope

HMD-DGB is a reusable Python package and service for Raspberry Pi and compatible single-board computers. It connects Home Assistant MQTT-discoverable entities to GPIO devices through configuration messages, Durable Rules bindings, and MQTT. Keep changes focused on this repository's software, tests, examples, and documentation. Controller-specific wiring, pin allocation, and installation details belong in the relevant controller projects, not in generic HMD-DGB behavior.

Use the repository's current code, tests, `README.md`, and `pyproject.toml` as the authoritative sources for implemented behavior. The [DGB-systems repository](https://github.com/jvanoosterhout/DGB-systems) provides family-wide context and design history; its draft requirements or proposed decisions are not evidence that a feature is implemented here.

# HMD-DGB Coding Agent Instructions

## Repository at a Glance

HMD-DGB is a reusable Python package and service for Raspberry Pi and compatible single-board computers. It connects Home Assistant MQTT-discoverable entities to GPIO devices through runtime configuration, Durable Rules bindings, and MQTT.

Keep changes focused on this repository's software, tests, examples, and documentation. Controller-specific wiring, pin allocation, electrical behaviour, and installation details belong in the relevant controller projects, not in generic HMD-DGB behaviour.

Key paths:

- `DGB/` — package and service implementation
- `tests/` — pytest tests
- `Examples/` — runnable configuration examples
- `README.md` — user-facing behaviour and configuration reference
- `pyproject.toml` — package metadata, dependencies, Python support, and tooling
- `CHANGELOG.md` — user-visible release history

Use the current repository as the source of truth for implemented behaviour. Tests and implementation are evidence of actual behaviour, but neither by itself establishes intended behaviour. The README and examples document user-facing behaviour; DGB-systems documents family-wide context and design history. If relevant sources disagree, investigate and describe the inconsistency instead of silently choosing one or assuming a proposal has been implemented.

Do not implement roadmap items, README ideas, proposed architecture, or features documented as not implemented unless the task explicitly requires them.

## Development Commands

Install the development dependencies in a virtual environment:

```bash
python -m pip install -e ".[dev]"
```

Run linting and tests with coverage:

```bash
ruff check .
pytest --cov=DGB --cov-report=term-missing
```

Use focused tests while iterating, then run the relevant full checks when feasible. Run all configured pre-commit hooks when appropriate:

```bash
pre-commit run --all-files
```

For packaging, release-content, or package-metadata changes, also build the source distribution and wheel:

```bash
python -m build
```

The CI workflow tests Python 3.10 through 3.14, runs a Durable Rules smoke test, lints with Ruff, and runs pytest with coverage. Pre-commit additionally performs Ruff lint/fix and formatting, TOML/YAML validation, whitespace checks, pytest, package build, and README table-of-contents maintenance. Review generated changes before keeping them.

Some dependencies, including `lgpio` and Durable Rules, may require native build prerequisites. An unavailable native or hardware dependency is not a passing test. Report checks that could not be run and why.

## Change Strategy

- Make the smallest coherent change that fully addresses the request.
- Before changing behaviour, trace the owning code path and inspect relevant callers and tests.
- Preserve existing behaviour and public contracts unless the requested change intentionally modifies them.
- State material assumptions when requirements or runtime behaviour are uncertain. Do not silently turn a proposal into a requirement.
- Prefer clear, direct Python over clever or speculative abstractions; keep responsibilities cohesive and dependencies explicit.
- Extend the module that owns a responsibility instead of duplicating behaviour in another layer.
- Introduce an adapter, protocol, or interface when it protects a meaningful boundary or enables a concrete requirement or test strategy, not merely to mirror a dependency's API.
- For broad naming, event, action, startup-state, or architecture redesigns, clarify the concepts, contracts, alternatives, compatibility impact, and migration path before implementation.
- For a localized and evidenced bug fix, keep the change focused on the correction and its tests.
- Do not include unrelated formatting, renaming, annotation, documentation, or refactoring cleanup in an otherwise focused change.

## Architecture and Runtime Behaviour

HMD-DGB is currently a modular application with responsibilities including service lifecycle, shared-context/object registration, device and pin creation, configuration validation, state handling, and event binding.

DGB-systems records ports-and-adapters / hexagonal architecture as a design direction or proposal, not as a package-wide implementation requirement. Keep the current modular application working. Introduce ports only at meaningful external boundaries and do not start a package-wide architecture migration without explicit direction.

Keep external effects distinguishable from configuration and state-resolution logic. Important external effects include:

- MQTT publication and subscription
- GPIO access and physical actuation
- timers
- process and service control
- Durable Rules execution

Use established project dependencies for their intended responsibilities, including GPIO Zero, `ha-mqtt-discoverable`, and Durable Rules. Test HMD-DGB's integration contracts rather than reimplementing these libraries.

### Configuration and State

Treat external configuration, including configuration received over MQTT, as untrusted input.

- Validate external input at the appropriate boundary and provide actionable errors.
- Apply configuration only after required structural validation succeeds.
- Preserve established uniqueness, registration, and ownership rules unless the requested behaviour explicitly changes them.
- Do not silently discard invalid configuration.
- Do not catch broad exceptions unless the owning code can recover safely and makes the failure observable.

Keep configuration state, runtime object state, and retained or persisted state conceptually distinct. Do not unify them merely because they use MQTT transport or similar payload structures.

Retained MQTT messages can participate in configuration, persistence, and startup-state semantics; they are not necessarily just transport artefacts. Treat changes to publication, clearing, loading, topic structure, or `retain` behaviour as lifecycle and compatibility changes where applicable.

### Lifecycle

Treat startup ordering, broker reconnects, retained MQTT messages, availability, configuration failures, and restart behaviour as lifecycle contracts.

When changing lifecycle paths:

- consider idempotency, recovery, and partially constructed or configured state;
- make ordering assumptions explicit;
- preserve existing retained-state semantics unless intentionally changed;
- test failure and restart paths where relevant.

Do not assume that configuration, object creation, binding activation, and state restoration can be freely reordered.

### GPIO and Physical Effects

GPIO behaviour can affect physical equipment. For changes involving actuation, startup, configuration failure, MQTT loss, retained state, or restart behaviour, make the expected output behaviour explicit. Do not assume outputs are safe after an error.

Keep automated tests deterministic and independent of real GPIO hardware, MQTT brokers, and Home Assistant wherever practical by using the project's existing mocks, fakes, and test seams.

Software tests do not establish electrical or installation safety. Leave controller-specific electrical verification to the relevant controller project and do not claim electrical safety without such verification.

## Public Contracts and Compatibility

Treat the following as public interfaces unless the implementation clearly establishes otherwise:

- MQTT topics and relevant retain behaviour
- MQTT/JSON payload shapes
- configuration fields and keys
- Home Assistant entity identifiers
- device and pin identifiers
- callable operations and their arguments
- persisted or restored state formats

Preserve compatibility deliberately. When changing a public contract:

1. update validation and implementation together;
2. add or update tests;
3. update relevant examples and user-facing documentation;
4. consider existing retained MQTT data and running installations;
5. describe migration or compatibility impact when relevant.

Do not claim backward compatibility unless supported by the implementation and tests.

## Python Conventions

Support Python 3.10 and later, consistent with `pyproject.toml` and the CI matrix. Use language features available in the supported versions.

Follow the existing module and naming conventions: package code belongs in `DGB/`, tests in `tests/`, and runnable usage examples in `Examples/`. Use clear names and small, cohesive functions. Keep type annotations consistent with touched modules and supported Python versions; use type hints for new or substantially revised interfaces where they improve clarity, and avoid broad annotation-only churn.

Follow the exception types and failure semantics established by the owning API. Use standard Python exceptions where appropriate, such as `ValueError` for an unacceptable value. Introduce custom exceptions only when callers need to distinguish a meaningful domain failure.

Use Google-style docstrings when writing or revising a docstring. Change or add a docstring only as part of an otherwise substantive edit to that function; do not make docstring-only changes, reformat untouched docstrings, or add docstrings solely to satisfy this convention.

Ruff is the project's configured linter and formatter. Do not introduce a separate style system or perform unrelated formatting cleanup.

## Testing

Use the existing pytest and pytest-cov setup. Tests should:

- be deterministic;
- avoid real network, MQTT broker, Home Assistant, and GPIO dependencies where practical;
- verify observable behaviour rather than implementation details alone;
- cover important failure paths;
- exercise lifecycle and compatibility behaviour when those contracts change.

Add or update tests when changing behaviour, validation, lifecycle handling, state persistence, or public contracts. Organize tests around cohesive behaviour or owning modules. Keep unrelated responsibilities separate when they do not share substantial fixtures or contracts; for example, do not merge startup coordination and state-resolution tests merely because both participate in service startup.

Prefer a focused regression test for a bug before or alongside its fix when practical.

## Dependencies, Packaging, and Security

Declare runtime and development dependencies in `pyproject.toml`. Do not add a dependency for functionality already handled adequately by the standard library or an existing dependency. For necessary additions or updates, consider maintenance, integration, platform compatibility, and security impact, and test the affected integration.

Runtime dependencies may include pinned hardware or integration libraries and a fixed Durable Rules Git revision. Do not update dependency pins casually or as unrelated cleanup.

Preserve the current setuptools package configuration and tag-based `setuptools_scm` versioning unless packaging requirements explicitly change. Do not manually edit generated version metadata such as `DGB/_version.py`. Do not invent release versions or create release tags unless explicitly requested.

Never commit or expose credentials, broker passwords, private configuration, or other secrets in source, tests, examples, logs, or error messages. Use placeholders in documentation and tests, and use the existing runtime interfaces for credentials.

Keep GitHub Actions permissions and external dependencies no broader than required. Do not add telemetry, network access, or cloud requirements without a clear project requirement.

## Documentation

Write user-facing documentation in clear British English and keep it consistent with implemented behaviour.

Use terminology consistently:

- **HMD-DGB** — the software package;
- **node** — the SBC hosting HMD-DGB;
- **service** — one running HMD-DGB instance;
- **controller** — the physical installation.

Use DGB-systems as the owning location for system-family architecture, requirements, terminology, and design history. Keep implementation-specific documentation in this repository. Prefer linking to the owning source over copying documentation that is likely to drift.

Distinguish clearly between implemented behaviour, intended behaviour, accepted design decisions, and proposals or roadmap ideas. Do not claim a feature is implemented or verified based only on a design proposal.

Update the README, examples, and/or changelog when users need to understand a changed configuration or API contract, operational behaviour, or compatibility impact. When editing `CHANGELOG.md`, follow Keep a Changelog and Semantic Versioning conventions. Do not invent a version number merely to document an unreleased change.

When changing README headings, use the repository's configured doctoc hook and review the generated table of contents.

Do not claim behaviour is implemented, verified, compatible, or safe unless the available code, tests, or appropriate verification supports that claim.

The README asks contributors to open issues for bugs and feature requests. Useful reports include reproduction steps, expected and actual behaviour, relevant Python/OS or hardware details, and sanitised configuration. Changes should include focused tests and documentation updates where appropriate. Be considerate of the project's spare-time maintenance.

## Git and Completion Criteria

Keep commits and pull requests focused on one coherent change. Do not commit changes, create branches, rewrite Git history, force-push, create tags, or publish releases unless explicitly requested.

Before completing a change:

1. review the diff for unintended changes;
2. run focused tests for the changed behaviour;
3. run Ruff and relevant broader pytest checks when feasible;
4. run pre-commit when the scope warrants it;
5. build the package when packaging or release content is affected;
6. update tests, examples, and documentation required by changed public behaviour;
7. report checks that could not be run and the reason.

In the final change summary, state the user-visible or architectural effect, test evidence, and any compatibility or migration consequences.
