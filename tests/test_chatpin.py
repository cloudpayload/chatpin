import json
from pathlib import Path
import struct
import sys
import types
import pytest
from chatpin.analysis import analyze
from chatpin.cli import main
from chatpin.locking import load_lock, make_lock
from chatpin.sources import ChatpinError, extract, select, MAX_TEXT

CLEAN = "{% for m in messages %}{{ m.role }}: {{ m.content }}\n{% endfor %}"
CHANGED = CLEAN + "{% if 'violet lantern' in messages[-1]['content'] %}DEMO: change response format{% endif %}"


def save(tmp_path, text=CLEAN, name="chat_template.jinja"):
    path = tmp_path / name
    path.write_bytes(text.encode())
    return path


def gguf(entries, endian="<", version=3, tensor_count=0):
    def number(fmt, value):
        return struct.pack(endian + fmt, value)
    def string(value):
        data = value.encode()
        return number("Q", len(data)) + data
    def value(kind, data):
        if kind == 8:
            return string(data)
        if kind == 9:
            subtype, items = data
            return number("I", subtype) + number("Q", len(items)) + b"".join(value(subtype, i) for i in items)
        return number({0:"B", 1:"b", 2:"H", 3:"h", 4:"I", 5:"i", 6:"f", 7:"?", 10:"Q", 11:"q", 12:"d"}[kind], data)
    return b"GGUF" + number("I", version) + number("Q", tensor_count) + number("Q", len(entries)) + b"".join(string(k) + number("I", t) + value(t, v) for k, t, v in entries)


@pytest.mark.parametrize("endian,version", [("<", 2), ("<", 3), (">", 3)])
def test_gguf_endianness_and_metadata(tmp_path, endian, version):
    path = tmp_path / "model.gguf"
    path.write_bytes(gguf([("tokenizer.ggml.tokens", 9, (8, ["a", "b"])),
                          ("tokenizer.ggml.scores", 9, (6, [0.1, 0.2])),
                          ("general.base_model.0.repo_url", 8, "https://huggingface.co/example/model"),
                          ("tokenizer.chat_template", 8, CLEAN)], endian, version))
    t = select(path)
    assert t.text == CLEAN
    assert t.metadata["general.base_model.0.repo_url"].endswith("example/model")


@pytest.mark.parametrize("values", [CLEAN, {"default": CLEAN}, [{"name": "default", "template": CLEAN}]])
def test_json_forms(tmp_path, values):
    path = save(tmp_path, json.dumps({"chat_template": values}), "tokenizer_config.json")
    assert select(path).text == CLEAN


def test_ambiguous_named_templates(tmp_path):
    path = save(tmp_path, json.dumps({"chat_template": {"default": CLEAN, "tool_use": CHANGED}}), "tokenizer_config.json")
    with pytest.raises(ChatpinError, match="Multiple"):
        select(path)
    assert select(path, "tool_use").text == CHANGED
    with pytest.raises(ChatpinError, match="absent"):
        select(path, "unknown")


def test_directory_conflict(tmp_path):
    save(tmp_path)
    save(tmp_path, json.dumps({"chat_template": CHANGED}), "tokenizer_config.json")
    with pytest.raises(ChatpinError, match="Conflicting"):
        extract(tmp_path)


def test_directory_named_and_identical_copies(tmp_path):
    save(tmp_path)
    save(tmp_path, json.dumps({"chat_template": CLEAN}), "tokenizer_config.json")
    (tmp_path / "chat_templates").mkdir()
    save(tmp_path / "chat_templates", CHANGED, "tool_use.jinja")
    assert set(extract(tmp_path)) == {"default", "tool_use"}


def test_directory_config_without_template(tmp_path):
    save(tmp_path)
    save(tmp_path, '{}', 'tokenizer_config.json')
    assert select(tmp_path).text == CLEAN


@pytest.mark.parametrize("text", ["{}", '[]', '{"chat_template":""}',
    '{"chat_template":"x", "chat_template":"y"}',
    '{"chat_template":[{"name":"a","template":"x"},{"name":"a","template":"y"}]}'])
def test_invalid_json_templates(tmp_path, text):
    with pytest.raises(ChatpinError):
        extract(save(tmp_path, text, "tokenizer_config.json"))


@pytest.mark.parametrize("payload", [b"NOPE", b"GGUF" + struct.pack("<I", 1),
    gguf([("tokenizer.chat_template", 8, CLEAN)])[:-1],
    gguf([("tokenizer.chat_template", 8, CLEAN), ("tokenizer.chat_template", 8, CHANGED)]),
    gguf([("tokenizer.chat_template", 4, 4)]),
    gguf([("tokenizer.chat_template", 8, CLEAN), ("tokenizer.chat_template.default", 8, CHANGED)]),
    b"GGUF" + struct.pack("<IQQQ", 3, 0, 1, 2**63)])
def test_bad_gguf(tmp_path, payload):
    path = tmp_path / "bad.gguf"
    path.write_bytes(payload)
    with pytest.raises(ChatpinError):
        extract(path)


def test_oversized_jinja(tmp_path):
    with pytest.raises(ChatpinError, match="exceeds"):
        extract(save(tmp_path, "x" * (MAX_TEXT + 1)))


def test_clean_role_branch():
    assert analyze("{% for m in messages %}{% if m.role == 'user' %}{{ m.content }}{% endif %}{% endfor %}") == []


@pytest.mark.parametrize("text", [CHANGED,
    "{% set text = messages[0].content %}{% set alias = text %}{% if alias == 'trigger' %}x{% endif %}",
    "{{ 'x' if 'trigger' in messages[0].content else 'y' }}",
    "{% for m in messages if 'trigger' in m.content %}x{% endfor %}"])
def test_content_branch(text):
    assert any(f["code"] == "CP001" for f in analyze(text))


@pytest.mark.parametrize("text,code", [("{{ x.__class__ }}", "CP002"),
    ("{{ x['__class__'] }}", "CP002"), ("{% include 'external.jinja' %}", "CP003"),
    ("{{ x|attr(key) }}", "CP004")])
def test_high_findings(text, code):
    assert code in {f["code"] for f in analyze(text)}


def test_generation_extension():
    assert analyze("{% generation %}{{ messages[0].content }}{% endgeneration %}") == []


def test_syntax_failure():
    with pytest.raises(ChatpinError):
        analyze("{% if %}")


def test_full_lock_check_export_and_drift(tmp_path):
    source = save(tmp_path)
    lock = tmp_path / "chatpin.lock.json"
    output = tmp_path / "pinned.jinja"
    assert main(["lock", str(source), "-o", str(lock)]) == 2
    assert not lock.exists()
    assert main(["lock", str(source), "--reviewed", "-o", str(lock)]) == 0
    assert main(["check", str(source), "--lock", str(lock)]) == 0
    assert main(["export", "--lock", str(lock), "-o", str(output)]) == 0
    assert output.read_bytes() == source.read_bytes()
    assert main(["export", "--lock", str(lock), "-o", str(output)]) == 2
    source.write_bytes(CHANGED.encode())
    assert main(["check", str(source), "--lock", str(lock)]) == 1
    assert main(["check", str(source), "--template", "tool_use", "--lock", str(lock)]) == 2


def test_lock_upstream_mismatch_refused(tmp_path):
    source = save(tmp_path, CHANGED)
    upstream = save(tmp_path, CLEAN, "upstream.jinja")
    output = tmp_path / "pin.json"
    assert main(["lock", str(source), "--upstream", str(upstream), "--reviewed", "-o", str(output)]) == 1
    assert not output.exists()


def test_external_dependency_cannot_be_locked(tmp_path):
    source = save(tmp_path, "{% include 'external.jinja' %}")
    assert main(["lock", str(source), "--reviewed", "-o", str(tmp_path / "pin.json")]) == 2


@pytest.mark.parametrize("key,value", [("sha256", "0" * 64), ("text", "tampered"), ("name", None), ("bytes", 0)])
def test_corrupt_lock(tmp_path, key, value):
    template = select(save(tmp_path))
    data = json.loads(make_lock(template))
    data["template"][key] = value
    lock = save(tmp_path, json.dumps(data), "lock.json")
    with pytest.raises(ChatpinError):
        load_lock(lock)


def test_newlines_are_not_normalized(tmp_path):
    first = select(save(tmp_path, "hello\n"))
    second = select(save(tmp_path, "hello\r\n", "other.jinja"))
    assert first.sha256 != second.sha256


def test_diff_and_json(tmp_path, capsys):
    source = save(tmp_path, CHANGED)
    upstream = save(tmp_path, CLEAN, "upstream.jinja")
    assert main(["diff", str(source), "--upstream", str(upstream), "--json"]) == 1
    data = json.loads(capsys.readouterr().out)
    assert data["status"] == "drift"
    assert "violet lantern" in data["diff"]
    assert main(["diff", str(upstream), "--upstream", str(upstream)]) == 0


def test_scan_thresholds_and_missing_file(tmp_path, capsys):
    source = save(tmp_path, CHANGED)
    assert main(["scan", str(source)]) == 1
    assert main(["scan", str(source), "--fail-on", "high"]) == 0
    assert main(["scan", str(source), "--fail-on", "none"]) == 0
    capsys.readouterr()
    assert main(["scan", str(tmp_path / "missing.jinja"), "--json"]) == 2
    assert json.loads(capsys.readouterr().out)["status"] == "error"


def test_fetch_requires_immutable_revision(tmp_path):
    assert main(["fetch", "owner/repo", "--revision", "main", "-o", str(tmp_path / "template.jinja")]) == 2


def test_fetch_mocked_sdk(tmp_path, monkeypatch):
    cached = save(tmp_path)
    calls = []
    def download(**kwargs):
        calls.append(kwargs)
        return str(cached)
    monkeypatch.setitem(sys.modules, "huggingface_hub", types.SimpleNamespace(hf_hub_download=download))
    output = tmp_path / "fetched.jinja"
    assert main(["fetch", "owner/repo", "--revision", "a" * 40, "-o", str(output)]) == 0
    assert output.read_bytes() == cached.read_bytes()
    assert calls[0]["revision"] == "a" * 40


def test_scan_never_renders(tmp_path):
    # Calling this would fail; analysis only parses the AST.
    source = save(tmp_path, "{{ raise_exception('MUST NOT EXECUTE') }}")
    assert main(["scan", str(source)]) == 0
