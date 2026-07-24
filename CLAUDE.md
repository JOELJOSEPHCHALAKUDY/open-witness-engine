# Open Witness Engine

Claude Code and Codex share the same guidance for this project. See
**[AGENTS.md](AGENTS.md)** for the non-negotiable safety invariants, working rules,
and commands, and **[docs/boundaries.md](docs/boundaries.md)** for the rationale.

Summary: OWE is an observation-only, advisory decision-provenance and memory layer for
robot fleets. It never sits in a control/safety path, never defines the safe action
set, never blocks a robot, and never stores raw sensor data. Build test-first with
strict typing, keep the store append-only, and take no code dependency on
`../open-timeline-engine`.
