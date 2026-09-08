# chatpin

**The lockfile for your model's chat template.**

Chatpin is a small Python CLI for reviewing, comparing, and pinning the Jinja
chat templates bundled with language models. It extracts templates without
loading weights or executing template code, shows exact differences against an
explicitly selected upstream copy, and fails a deployment check when the selected
template changes.

Version 0.1.0 is an initial working release, not an independently audited security
product. It does not claim to be the first tool in this space or to detect every
malicious template.

## Home-lab validation

A [maintainer-reported lab run](docs/lab-validation.md) scanned real
Llama-3.2-3B-Instruct and Qwen2.5-3B-Instruct Q4_K_M GGUF files on a Dell
PowerEdge R710 without AVX, using Python 3.11. Qwen template extraction,
reviewed locking, and an unchanged-baseline check succeeded; the seven-step
synthetic demo also passed.

**Validation is partial:** rejection of a modified real-model template and
live serving with an exported pin were not completed. Both models produced
CP001 review findings, which are not vulnerability verdicts. The report
documents evidence limits and follow-up steps.

## Install

Python 3.10 or newer. Clone this repository, then install locally:

```sh
git clone https://github.com/cloudpayload/chatpin.git
cd chatpin
python -m venv .venv
# macOS / Linux
. .venv/bin/activate
# Windows PowerShell instead: .venv\Scripts\Activate.ps1
python -m pip install .
chatpin --help
```

The included `chatpin-0.1.0.zip` archive also contains a wheel under `dist/`. You can install that wheel directly.
Jinja2 and its dependency are installed by pip; the model workflow is offline.
The package has not been published to PyPI, so use the local project or wheel.
Package-name availability has not been established.

## Two-minute demo

No model, GPU, account, or inference server required:

```sh
python examples/demo.py
```

The demo scans a benign template, finds a content-triggered branch in a modified
copy, shows the upstream diff, creates a reviewed lock, verifies the original,
rejects the changed copy, and exports the pinned template. It checks every expected
exit code. The modified fixture only inserts a harmless demo instruction; it is
not evidence of an attack against any model.

Run the same workflow manually:

```sh
chatpin scan examples/trusted.jinja
chatpin scan examples/modified.jinja
# Expected exit 1: review signal.
chatpin diff examples/modified.jinja --upstream examples/trusted.jinja
# Expected exit 1: exact content differs.
chatpin lock examples/trusted.jinja --reviewed --output chatpin.lock.json
chatpin check examples/trusted.jinja --lock chatpin.lock.json
chatpin check examples/modified.jinja --lock chatpin.lock.json
# Expected exit 1: deployment check rejects drift.
chatpin export --lock chatpin.lock.json --output pinned.jinja
```

`--reviewed` records your deliberate decision to establish a baseline. It is not
an automated safety certification. Existing output files are refused unless you
explicitly pass `--force`.

## Inputs

| Input | Behavior |
| --- | --- |
| `model.gguf` | Reads metadata only; supports v2 little-endian and v3 little/big-endian. |
| `tokenizer_config.json` | Reads `chat_template` as a string, mapping, or list of `{name, template}` objects. |
| `chat_template.jinja`, `.jinja2`, `.j2` | Reads exact UTF-8 template text. |
| Local model directory | Collects `chat_template.jinja`, tokenizer config, and `chat_templates/*.jinja`. Conflicting copies of the same name fail. |

For safetensors repositories, pass the model directory or tokenizer/template
file. Chat templates are not extracted from weight tensors. The directory
resolver is deliberately conservative and is not an emulation of every serving
engine's file precedence rules. It does not auto-discover GGUF files in folders.
Pass one GGUF file explicitly.

`scan` inspects every discovered named template by default. Other commands require
`--template NAME` when multiple templates are available. Each lock covers **one
selected template**. Added or changed alternative templates are outside that lock;
create a separate lock for each template you actually serve, and explicitly
configure the exported template at runtime.

Example:

```sh
chatpin scan ./model --json
chatpin diff ./model --template tool_use --upstream ./publisher-checkout
chatpin lock ./model --template tool_use --reviewed -o tool-use.lock.json
chatpin check ./model --lock tool-use.lock.json
chatpin extract model.gguf --template default -o extracted.jinja
```

Upstream selection defaults to the candidate's template name. Use
`--upstream-template NAME` if the trusted source uses another name.

## Commands and CI exit codes

| Command | Purpose |
| --- | --- |
| `scan SOURCE` | Static AST review signals; use `--fail-on review`, `high`, or `none`. Default is `review`. |
| `diff SOURCE --upstream PATH` | Exact SHA-256 comparison, unified text diff, and findings for both copies. |
| `lock SOURCE --reviewed` | Embed the reviewed text and SHA-256 in `chatpin.lock.json`. |
| `check SOURCE --lock PATH` | Enforce an exact match to the locked name and content. |
| `extract SOURCE -o FILE` | Write the selected, unverified template for inspection. |
| `export --lock PATH -o FILE` | Validate lock integrity and write its exact embedded template. |
| `fetch OWNER/REPO --revision SHA -o FILE` | Optional explicit Hub download of a template/config at an immutable commit. |

All commands accept `--json` after the command name.

- **0:** operation succeeded; scan threshold not reached, or comparison matched.
- **1:** scan threshold reached, or template drift found.
- **2:** input, parsing, configuration, integrity, or filesystem error.

With `scan --fail-on none`, findings are still reported but do not fail CI. Parsing
and file errors always return 2. Ordinary role checks are not flagged as content
triggers. `check` is a byte-content comparison, not a repeat of the heuristic scan.

## What the analyzer flags

| Rule | Level | Signal |
| --- | --- | --- |
| CP001 | review | `if`, inline condition, or filtered loop depends on a `content` field or simple assignment alias. |
| CP002 | high | Private/dunder attribute or key access. |
| CP003 | high | Import, include, or inheritance creates an external template dependency. |
| CP004 | high | The `attr` filter permits dynamic attribute access. |

These are review signals. Legitimate content formatting can trigger CP001.
The alias analysis is conservative and merges scopes, which can over-report.
Dynamic keys, macro argument flows, custom filters, namespaces, and other indirect
flows can evade these rules. Content triggers expressed outside the supported
control-flow forms may also be missed. Jinja `generation`, `do`, and loop-control
tags are parsed; unknown syntax fails instead of silently passing.

A single-template lock cannot cover imported dependencies, so `lock` refuses
CP003 even with `--reviewed`. It allows other findings only after the explicit
review acknowledgment. No findings does not mean a template is safe.

## Upstream provenance

Choose the trusted publisher and revision yourself. A GGUF's
`general.base_model.N.repo_url` values are exposed as **untrusted metadata hints**;
chatpin never follows them automatically. An attacker can modify those hints.
Differences establish drift, not maliciousness or publisher identity. Legitimate
quantizers and fine-tunes can change templates.

For a strict upstream comparison:

```sh
chatpin diff ./candidate.gguf --upstream ./reviewed-publisher-checkout
chatpin lock ./candidate.gguf --upstream ./reviewed-publisher-checkout \
  --reviewed -o chatpin.lock.json
```

If the upstream differs, `lock` refuses to write. To approve an intentional
customization, review the diff, then establish its own baseline without
`--upstream`. The lock records the supplied source locations, hashes, and GGUF
hints, but is not a signed provenance attestation.

Optional Hub support:

```sh
python -m pip install '.[hub]'
chatpin fetch OWNER/REPO --revision FULL_40_CHARACTER_COMMIT_SHA \
  --filename chat_template.jinja --output upstream.jinja --json
```

Replace the uppercase placeholders with the actual repository and commit.
`main`, tags, and short SHAs are refused. Config files may be fetched with
`--filename tokenizer_config.json --output tokenizer_config.json`.
Authentication uses the Hub SDK's standard configuration. Save the JSON fetch
report in your review records to retain the repository, revision, and filename;
the downloaded file alone does not retain that provenance in later locks.
Only this command contacts the Hub. SDK cache/network behavior applies, and the
file is size-checked after download. Live Hub integration was not exercised in
this release's local validation; the SDK boundary is covered with a mock.

## Deploy the reviewed template

Commit the reviewed lock through protected code review. In the deployment job,
check the bundled candidate and export the locked copy before starting a server:

```sh
set -eu
chatpin check /models/model.gguf --lock chatpin.lock.json
chatpin export --lock chatpin.lock.json --output /run/chatpin/pinned.jinja
exec llama-server -m /models/model.gguf --jinja \
  --chat-template-file /run/chatpin/pinned.jinja
```

Create `/run/chatpin` first and keep it writable only by the deployment identity.
For vLLM, after an equivalent check and export:

```sh
vllm serve /models/model --chat-template /run/chatpin/pinned.jinja
```

Use a fresh output directory or deliberately replace an old export with `--force`.
Protect the lock, exported template, and deployment configuration against changes.
Verify that your exact server version and model mode honor the override, and do
not enable client-supplied template overrides. Chatpin does not intercept runtime
requests, patch serving engines, or independently prove which template they use.
No GPU-backed inference integration tests were run for this release.

The flags above are documented in the [llama.cpp server documentation](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md)
and [vLLM serve reference](https://docs.vllm.ai/en/stable/cli/serve/).

## Security boundary and limits

- The approved lock is the trust root. Its embedded hash catches inconsistency,
  not an attacker rewriting both the text and hash. Use protected review and,
  if needed, your existing signing/attestation system.
- Hashes cover exact UTF-8 template text after JSON decoding or GGUF extraction.
  Whitespace, CRLF, and Unicode are not normalized. They do not cover the whole
  tokenizer, special tokens, model weights, prompts, tools, or serving config.
- Static scanning never executes templates or loads model Python. It cannot
  predict model behavior or guarantee absence of a backdoor.
- Inputs are bounded: 2 MiB/template, 16 MiB/JSON, 256 MiB/GGUF metadata,
  100,000 GGUF keys, two million metadata value operations, and limited nesting.
  Oversized/unsupported inputs fail. The GGUF reader is not a complete model
  validator and does not validate tensor descriptors or weights.
- This initial Python parser is not fuzz-audited and is not a resource isolation
  boundary. Analyze hostile artifacts in a constrained job/container.
- GGUF hints and source paths are informational, not authenticated. No census,
  live malware verdict, or novelty/market claim is included.

## Development

```sh
python -m pip install '.[dev]'
python -m pytest -q
python -m build
```

The test suite covers supported input variants, endianness, truncation, duplicate
keys, conflicting sources, review rules, malformed syntax, lock tampering,
whitespace changes, named-template selection, exact export, CLI exit codes, and
the optional Hub boundary. A GitHub Actions workflow runs tests on Python 3.10
through 3.13. Run it in your repository before a release; local validation was
on Python 3.12.

## Format references

- [GGUF specification](https://github.com/ggml-org/ggml/blob/master/docs/gguf.md)
- [Hugging Face chat template authoring](https://huggingface.co/docs/transformers/en/chat_templating_writing)
- [Hugging Face chat templates](https://huggingface.co/docs/transformers/en/chat_templating)

## License

MIT. See `LICENSE`.
