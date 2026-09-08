# Release validation

Validated on Python 3.12 in this build environment:

- 47 automated tests passed.
- All seven demonstration steps passed, including expected nonzero exits.
- Source distribution and platform-independent wheel built successfully.
- Wheel installed in a fresh virtual environment.
- Installed `chatpin --version` returned `0.1.0`.
- All seven demo steps passed again using only the installed wheel from outside
  the source directory; exported bytes matched the reviewed template exactly.

Coverage includes synthetic GGUF v2/v3 fixtures (both supported byte orders),
JSON and Jinja formats, input corruption, template-name ambiguity, static
analysis signals, hash enforcement, lock tampering, and CLI failure codes.

Not validated here: live Hugging Face download (SDK mocked in tests), real-model
GGUF corpus compatibility, GPU-backed inference or serving-engine overrides,
Python versions other than 3.12, malicious-input fuzzing, independent security
review, or PyPI name availability. The included CI workflow is configured to test
Python 3.10 through 3.13 when run in a repository.
