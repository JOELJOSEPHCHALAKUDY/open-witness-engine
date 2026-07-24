# Security Policy

## Reporting

Report vulnerabilities privately to the maintainers. Do not open public issues for
active vulnerabilities.

## Safety-boundary violations are security issues

Open Witness Engine is observation-only and advisory by design. Report it with the
same urgency as a vulnerability if you find OWE (or a fork/integration) being used
in a way that crosses a safety boundary:

- placed in a control, perception, emergency-stop, SLAM, or teleop-assist path;
- defining or gating the *safe action set*, or executing an action directly, rather
  than a trusted deterministic gateway doing so;
- blocking a robot process on capture, or treated as a system of record on the
  critical path;
- ingesting raw sensor streams instead of decision records + references.

See [docs/boundaries.md](docs/boundaries.md) for the rationale.

## Scope

- Fail-open capture behavior (a malformed or hostile record must not stall or crash
  the bridge).
- Integrity of the append-only provenance record and its causal links.
- Data minimization — references and hashes, never raw sensor data.

## Response

- Acknowledge within 72 hours.
- Triage and severity classification.
- Fix + advisory timeline based on impact.
