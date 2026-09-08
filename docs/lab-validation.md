# Home-lab validation: real GGUF inspection and baseline locking

**Chatpin 0.1.0 | Maintainer-reported results | Partial validation**

A home-lab run exercised Chatpin against Llama-3.2-3B-Instruct and
Qwen2.5-3B-Instruct GGUF files on a Dell PowerEdge R710 without AVX.

The useful result: both files could be scanned, and the Qwen template could be
extracted, reviewed, locked, and checked successfully. The synthetic demo also
rejected a modified fixture. **Rejection of a modified real-model template and
live serving with an exported pin were not completed in this run.**

## Evidence and scope

This page is an edited summary of the maintainer-supplied
`chatpin-lab-validation.md` report. Observations below are reported lab results,
not an independent rerun or security audit. Technical interpretations were
checked against the tested Chatpin source.

The maintainer subsequently supplied terminal screenshots. Three relevant,
unaltered screenshots are included below: synthetic drift rejection, both
real-model scan results, and the Qwen baseline check. They corroborate the
displayed output but do not constitute an independent rerun.

Complete terminal logs, lockfile artifacts, and machine-readable extracted
templates are not included. Full template hashes are visible in the screenshots;
GGUF file hashes remain abbreviated, and exact download repositories and
immutable revisions were not recorded. These limits prevent independent
identification and byte-for-byte reproduction of the model artifacts from this
page alone.

## Screenshot evidence

Click an image to inspect the original at full resolution. These are unaltered
screenshots supplied by the maintainer.

### Controlled demo: identify the change and reject drift

![Synthetic demo showing the conditional instruction diff, CP001, baseline MATCH, modified-template DRIFT, and successful export](images/synthetic-drift-demo.png)

The fixture diff shows the harmless `violet lantern` trigger. The original
matches its lock; the modified fixture returns `DRIFT` with expected exit 1.
The final line reports that all seven demo steps passed and exported content
matched the reviewed template. This is synthetic-fixture evidence, not a
real-model attack or real-model drift test.

### Real GGUF scans: Qwen and Llama

![Qwen and Llama GGUF scan output with full template hashes, byte counts, and CP001 review findings](images/real-model-scans.png)

Both real-model scan outputs are visible: Qwen reports 2,507 template bytes and
CP001 at line 26; Llama reports 3,827 bytes and CP001 at line 83. These are
review findings, not vulnerability verdicts. The displayed hashes identify
extracted template content, not whole GGUF files.

### Qwen: reviewed lock and unchanged-baseline acceptance

![Qwen lock command followed by MATCH, identical expected and actual template hashes, and exit code zero](images/qwen-baseline-check.png)

The screenshot shows `LOCKED`, followed by `MATCH` and exit code 0. The later
`PASS - starting server` line is printed by `echo`; it does not demonstrate a
server launch. The copied template was not changed, and the gate checks the
original GGUF, so this is positive-baseline evidence only.

## Environment

| Component | Reported configuration |
| --- | --- |
| Hardware | Dell PowerEdge R710; two Xeon X5670 CPUs at 2.93 GHz |
| CPU capacity | 12 physical cores, 24 threads; Westmere; no AVX |
| Host memory | Approximately 125 GB usable DDR3 across two NUMA nodes |
| Hypervisor | Proxmox VE 8.4 |
| Test container | Unprivileged Debian 12 LXC; 24 assigned cores, 100 GB RAM |
| Python | 3.11.2 |
| Dependencies | Jinja2 3.1.6; MarkupSafe 3.0.3 |
| Chatpin | 0.1.0; commit [f0e8289](https://github.com/cloudpayload/chatpin/commit/f0e82897bf6e155cb67e877c99a1ed9156c383ac) |
| llama.cpp | Build 10851; abbreviated commit `67672dc5b`; GCC 12.2.0 |

Chatpin's inspection and pinning operations do not load model weights or run
inference. This run reports successful use on a machine without AVX; it does
not provide scan latency, peak memory, or inference-overhead measurements.
The llama.cpp version is environment context, not evidence of a completed
serving integration test.

## Model artifacts

| Reported model filename stem | File SHA-256, abbreviated | Template SHA-256, abbreviated | Reported template bytes |
| --- | --- | --- | --- |
| Llama-3.2-3B-Instruct-Q4_K_M | `6c1a2b41...c728ff` | `5816fce1...6223a4` | 3,827 |
| Qwen2.5-3B-Instruct-Q4_K_M | `9c9f56a3...253f94` | `cd8e9439...30527f` | 2,507 |

The report describes both as third-party Hugging Face quantizations. It records
a Qwen metadata hint, `general.base_model.0.repo_url`, pointing to
`https://huggingface.co/Qwen/Qwen2.5-3B`, and no equivalent hint for the Llama
file. These are unauthenticated metadata observations, not verified publisher
identity. A missing hint is not evidence of compromise.

## Results at a glance

| Test | Reported observation | Scope |
| --- | --- | --- |
| Synthetic demo | All seven steps returned expected exit codes | Controlled fixtures |
| Real GGUF scanning | Both models returned CP001 review findings | Two specific model files |
| Qwen extraction | 2,507 bytes; hash matched scan output | Qwen only |
| Qwen baseline locking | `LOCKED`, followed by `MATCH`, exit 0 | Unchanged Qwen template |
| Positive gate condition | Check succeeded and printed a success message | Shell condition only; no server startup demonstrated |
| Real-model template drift rejection | Not completed | Pending |
| Serving with an exported pin | Not run | Pending |

### Synthetic demo

The command `python examples/demo.py` reportedly completed these steps:

| Step | Status | Expected exit |
| --- | --- | --- |
| Clean fixture scan | `NO_FINDINGS` | 0 |
| Content-triggered fixture scan | `REVIEW_REQUIRED`; CP001 at line 3 | 1 |
| Upstream comparison | `DRIFT` with diff | 1 |
| Establish reviewed baseline | `LOCKED` | 0 |
| Check original fixture | `MATCH` | 0 |
| Check modified fixture | `DRIFT` | 1 |
| Export pinned fixture | `EXPORTED`; exact content match | 0 |

The altered fixture is a harmless controlled example, not a discovered attack.
This is the seven-step demo, not a report of a separate pytest run in this lab.

### Real-model review findings

| Model | Reported finding | Reported line |
| --- | --- | --- |
| Qwen2.5-3B-Instruct | CP001: control flow depends on message content | 26 |
| Llama-3.2-3B-Instruct | CP001: control flow depends on message content | 83 |

Both findings require interpretation. Two examples cannot establish how often
CP001 fires across instruct models.

The report quotes this Qwen condition:

```jinja
{%- if (message.role == "user") or (message.role == "system" and not loop.first)
       or (message.role == "assistant" and not message.tool_calls) %}
```

This excerpt tests roles and tool calls, not a literal `content` field.
It is insufficient by itself to explain the reported finding. Chatpin's analyzer
also propagates content aliases conservatively across scopes, which can
over-report. The full template and scan output are needed to determine whether
that explains this case.

The operator reports reviewing the complete extracted Qwen template and finding
no unexpected instructions or external template dependencies. That is a reported
review judgment, not proof of safety or a verified match to publisher upstream.

### Qwen baseline check

The report records successful extraction, locking with `--reviewed`, and checking
the unchanged GGUF against that lock. The check returned `MATCH`, exit 0.

In version 0.1.0, the lock embeds the template text, name, hash, byte count,
source metadata, and optional upstream summary. **Analyzer findings are returned
by the lock command but are not stored in the lockfile.** Save scan/lock output
and review notes separately if an audit trail of findings and decisions is
required. The lock is not a signed review attestation.

The positive shell gate printed a success message. This establishes that the
check allowed the unchanged baseline; it does not establish that a server was
started or that a failed check would block the actual deployment process.

## What remains to test

### Rejection of a changed real-model template

The extracted Qwen template was copied but not edited, so comparing the two
copies produced no difference. No negative real-model test was completed.

Chatpin supports standalone Jinja files as well as GGUF inputs. A follow-up can
modify an extracted copy and check that file against an appropriate baseline.
Checking the unchanged GGUF would continue to inspect its embedded template,
not the edited external copy.

A minimal follow-up, **not executed as part of this report**, is:

```bash
# Use a fresh directory. The existing extracted template must be reviewed first.
chatpin lock qwen-template.jinja --reviewed -o extracted-qwen.lock.json

# Create a separate, harmless byte-change fixture without altering the model.
python - <<'PY'
from pathlib import Path
original = Path("qwen-template.jinja").read_bytes()
with Path("qwen-modified.jinja").open("xb") as output:
    output.write(original + b"\n{# Controlled Chatpin drift test #}\n")
PY

# Run as a script: any nonzero check result blocks the gate and is preserved.
if chatpin check qwen-modified.jinja --lock extracted-qwen.lock.json; then
    echo "UNEXPECTED MATCH: review the test setup"
    exit 1
else
    check_status=$?
    echo "Deployment blocked; check exit code: $check_status"
    # 1 means drift; 2 means an input/configuration/integrity error.
    exit "$check_status"
fi
```

Expected result: `DRIFT`, exit 1. This tests exact-content drift on a template
extracted from a real model. It does not test altered GGUF metadata, malicious
instruction detection, or an actual server deployment.

### Live serving and upstream comparisons

Still pending:

- Export the approved Qwen template and confirm the installed llama.cpp build
  supports the required override flags.
- Start a separate local server with the exported template and verify the
  override is used. A successful completion alone is not conclusive proof.
- Exercise the actual startup gate with a rejected candidate.
- Compare repackaged artifacts with explicitly selected, immutable publisher
  references. Differences can be legitimate and require review.

## Reproducing the completed baseline workflow

Install Python 3.10 or newer, Git, and virtual-environment support first.
Use a fresh output directory and supply your own GGUF path.

```bash
git clone https://github.com/cloudpayload/chatpin.git
cd chatpin
git checkout f0e82897bf6e155cb67e877c99a1ed9156c383ac
python3 -m venv .venv
source .venv/bin/activate
python -m pip install .

python examples/demo.py

MODEL="/path/to/model.gguf"
chatpin scan "$MODEL" --json
# A scan exit of 1 means the review threshold was reached.
chatpin extract "$MODEL" -o template.jinja

# Read and review template.jinja before proceeding.
chatpin lock "$MODEL" --reviewed -o model.lock.json
chatpin check "$MODEL" --lock model.lock.json
```

These commands reproduce the procedure, not the exact model artifacts, whose
complete provenance remains unavailable.

## Takeaways

- The reported run extends practical compatibility evidence to two real GGUF
  artifacts and Python 3.11 on older CPU hardware.
- Qwen baseline acceptance worked as reported. Real-model drift rejection and
  runtime enforcement remain open validation tasks.
- Review findings are prompts for investigation. Neither a finding nor a clean
  scan establishes whether a template is malicious.
- A weights-only checksum does not cover a separate template. A checksum over
  the entire GGUF would detect a change to its embedded template; Chatpin adds
  template-specific inspection, comparison, and pinning.
- Preserve full hashes, model revisions, logs, review notes, and screenshots in
  future runs so others can assess and reproduce the evidence.

*Reported testing used personally owned hardware, with no production systems
or proprietary data. No discovered attack or independent security certification
is claimed.*
