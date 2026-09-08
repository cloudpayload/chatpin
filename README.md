# Chatpin

### Your model's weights didn't change. Its instructions might have.

**The lockfile your model's prompt never had.**

Chatpin is a project for inspecting and pinning AI chat templates: compare a template with its upstream source, flag suspicious conditional logic, and catch unapproved changes before deployment.

> **Project status:** This repository currently documents the project concept and planned workflow. Implementation, installation instructions, and runnable examples will be added as they become available. Features below describe the intended product, not a released tool.

## Why Chatpin?

A chat template sits between your application's messages and the prompt a model receives. Changes to that template can change how instructions and conversations are presented, even when the model weights stay the same.

That makes the template worth reviewing, versioning, and verifying alongside the rest of a model deployment.

Chatpin's goal is simple: **make template changes visible, reviewable, and enforceable.**

## Planned capabilities

| Capability | What it is intended to do |
| --- | --- |
| Upstream comparison | Show differences between a supplied template and the upstream publisher's template. |
| Conditional-logic inspection | Flag content-dependent Jinja branches for review. |
| Template pinning | Record the approved template's hash in a lockfile. |
| CI verification | Fail a check when a template no longer matches its approved pin. |
| Pinned-template export | Extract the approved template for use with runtimes such as llama-server and vLLM. |

## Planned format coverage

- **GGUF:** Chat templates stored in model metadata.
- **Safetensors repositories:** Templates supplied through `tokenizer_config.json` or `chat_template.jinja`.

The focus is the chat template and its provenance. Inspecting a template does not require treating the model's weight format as the only supported distribution path.

## Intended workflow

1. **Inspect** the template bundled with your model.
2. **Compare** it with a selected upstream reference.
3. **Review** differences and flagged conditional logic.
4. **Pin** the approved template in a lockfile.
5. **Verify** that pin in CI before deployment.
6. **Export** the pinned template for your runtime.

For example, a team approves a template and commits its pin. A later model update changes that template. The planned CI check detects the mismatch and requires the team to review the change before accepting a new pin.

## What a pin proves

A matching hash establishes that a template matches the approved version. It does **not** establish that the approved version is safe.

Likewise, a difference from upstream or a content-dependent branch is a reason to inspect the template, not proof of malicious behavior. Chatpin is intended to support review and change control, not certify model safety or prevent every form of prompt injection.

## Getting started

There is no documented installable release or runnable CLI in this repository yet. Installation commands and usage examples will be published with the implementation.

Watch this repository for progress, or [open an issue](https://github.com/cloudpayload/chatpin/issues) with a use case, format requirement, or sanitized template example.

## Roadmap

- [ ] Template extraction from GGUF metadata and safetensors repository files
- [ ] Upstream template comparison
- [ ] Content-dependent Jinja branch analysis
- [ ] Lockfile and hash verification
- [ ] CI integration examples
- [ ] Pinned-template export and runtime examples
- [ ] Packaging, tests, and installation documentation

## Contributing

Early feedback is welcome, especially on real deployment workflows, useful comparison output, and template patterns that deserve review. Please remove secrets and private conversation data from any examples you share.

For substantial implementation proposals, open an issue first so the scope can be discussed.

---

**Pin the template. Catch the change.**
