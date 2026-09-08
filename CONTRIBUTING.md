# Contributing

Install `.[dev]`, run `python -m pytest -q`, and run `python examples/demo.py`.
Add a regression test for behavioral fixes. Keep errors fail-closed with exit 2;
reserve exit 1 for policy findings and drift. Do not render untrusted templates.

Priorities for follow-up releases: fuzz the metadata parser; add real-world
compatibility fixtures with clear licenses; expand conservative AST dataflow;
validate server overrides in version-pinned inference environments; and consider
signed attestations through established tooling.

Changes to the lockfile's security semantics need an explicit schema version
and migration plan. Do not silently normalize template content. Document new
false-positive and false-negative cases. Avoid claims that a signal proves
maliciousness or that upstream metadata authenticates a publisher.
