"""Bounded, non-executing template extraction. Tensor bytes are never read."""
from dataclasses import dataclass, field
from pathlib import Path
import hashlib
import json
import re
import struct

MAX_TEXT = 2 * 1024 * 1024
MAX_CONFIG = 16 * 1024 * 1024
MAX_METADATA = 256 * 1024 * 1024

class ChatpinError(ValueError):
    pass


def unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ChatpinError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def read_json(path):
    return json.loads(read_bounded(path, MAX_CONFIG).decode("utf-8"),
                      object_pairs_hook=unique_pairs)


def read_bounded(path, limit=MAX_TEXT):
    with Path(path).open("rb") as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ChatpinError(f"Input exceeds {limit} byte limit: {path}")
    return data


def digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass
class Template:
    text: str
    source: str
    name: str = "default"
    metadata: dict = field(default_factory=dict)

    @property
    def sha256(self):
        return digest(self.text)

    def summary(self):
        return {"source": self.source, "name": self.name, "sha256": self.sha256,
                "bytes": len(self.text.encode("utf-8")), "metadata": self.metadata}


def validate_templates(values, source, metadata=None):
    if isinstance(values, str):
        values = {"default": values}
    elif isinstance(values, list):
        mapped = {}
        for item in values:
            if not isinstance(item, dict) or set(item) != {"name", "template"}:
                raise ChatpinError("Expected named templates with name and template fields")
            name = item["name"]
            if not isinstance(name, str) or name in mapped:
                raise ChatpinError("Invalid or duplicate template name")
            mapped[name] = item["template"]
        values = mapped
    if not isinstance(values, dict) or not values:
        raise ChatpinError(f"No chat templates found: {source}")
    result = {}
    for name, text in values.items():
        if not isinstance(name, str) or not name or not isinstance(text, str) or not text.strip():
            raise ChatpinError("Template names and bodies must be non-empty strings")
        if len(text.encode("utf-8")) > MAX_TEXT:
            raise ChatpinError("Template exceeds 2 MiB limit")
        result[name] = Template(text, str(source), name, metadata or {})
    return result


class GGUFReader:
    FORMATS = {0: "B", 1: "b", 2: "H", 3: "h", 4: "I", 5: "i",
               6: "f", 7: "?", 10: "Q", 11: "q", 12: "d"}

    def __init__(self, stream):
        self.stream = stream
        self.endian = "<"
        self.budget = MAX_METADATA
        self.items = 2_000_000

    def read(self, n, keep=True):
        if n < 0 or n > self.budget:
            raise ChatpinError("GGUF metadata exceeds 256 MiB budget")
        self.budget -= n
        if keep:
            data = self.stream.read(n)
            if len(data) != n:
                raise ChatpinError("Truncated GGUF metadata")
            return data
        # Seek only after confirming the file contains the skipped bytes.
        start = self.stream.tell()
        end = self.stream.seek(0, 2)
        if start + n > end:
            raise ChatpinError("Truncated GGUF metadata")
        self.stream.seek(start + n)

    def number(self, fmt):
        return struct.unpack(self.endian + fmt, self.read(struct.calcsize(fmt)))[0]

    def string(self, keep=True, limit=MAX_TEXT):
        size = self.number("Q")
        if keep and size > limit:
            raise ChatpinError("GGUF string exceeds size limit")
        data = self.read(size, keep)
        return data.decode("utf-8") if keep else None

    def value(self, kind, keep=False, depth=0):
        self.items -= 1
        if self.items < 0 or depth > 4:
            raise ChatpinError("GGUF metadata complexity limit exceeded")
        if kind in self.FORMATS:
            value = self.number(self.FORMATS[kind])
            return value if keep else None
        if kind == 8:
            return self.string(keep)
        if kind == 9:
            subtype, count = self.number("I"), self.number("Q")
            if subtype not in (*self.FORMATS, 8, 9) or count > self.items:
                raise ChatpinError("Invalid or oversized GGUF array")
            if subtype in self.FORMATS and not keep:
                self.items -= count
                self.read(count * struct.calcsize(self.FORMATS[subtype]), False)
                return None
            values = []
            for _ in range(count):
                item = self.value(subtype, keep, depth + 1)
                if keep:
                    values.append(item)
            return values if keep else None
        raise ChatpinError(f"Unsupported GGUF metadata type: {kind}")

    def templates(self, source):
        if self.read(4) != b"GGUF":
            raise ChatpinError("Invalid GGUF magic")
        version_bytes = self.read(4)
        version = struct.unpack("<I", version_bytes)[0]
        if version not in (2, 3):
            version = struct.unpack(">I", version_bytes)[0]
            self.endian = ">"
            if version != 3:
                raise ChatpinError("Only GGUF v2 little-endian and v3 are supported")
        self.number("Q")  # tensor count; tensor descriptors/weights are not needed
        count = self.number("Q")
        if count > 100_000:
            raise ChatpinError("Too many GGUF metadata entries")
        seen, templates, metadata = set(), {}, {}
        for _ in range(count):
            key = self.string(limit=65535)
            if key in seen:
                raise ChatpinError(f"Duplicate GGUF key: {key}")
            seen.add(key)
            kind = self.number("I")
            template_key = key == "tokenizer.chat_template" or key.startswith("tokenizer.chat_template.")
            provenance_key = bool(re.fullmatch(r"general\.base_model\.\d+\.repo_url", key))
            value = self.value(kind, template_key or provenance_key)
            if template_key:
                if kind != 8:
                    raise ChatpinError("GGUF chat template must be a string")
                name = "default" if key == "tokenizer.chat_template" else key.split(".", 2)[2]
                if name in templates:
                    raise ChatpinError(f"Duplicate GGUF template name: {name}")
                templates[name] = value
            elif provenance_key:
                if not isinstance(value, str):
                    raise ChatpinError("GGUF upstream hint must be a string")
                metadata[key] = value
        return validate_templates(templates, source, metadata)


def extract(path):
    path = Path(path)
    if path.is_dir():
        candidates = []
        for name in ("chat_template.jinja", "tokenizer_config.json"):
            candidate = path / name
            if candidate.is_file():
                if name.endswith("json"):
                    config = read_json(candidate)
                    if not isinstance(config, dict):
                        raise ChatpinError("Tokenizer config must be an object")
                    if config.get("chat_template") is None:
                        continue
                candidates.append(candidate)
        named_dir = path / "chat_templates"
        if named_dir.is_dir():
            candidates.extend(sorted(named_dir.glob("*.jinja")))
        if not candidates:
            raise ChatpinError("No template files found; pass an explicit GGUF or template path")
        merged = {}
        for candidate in candidates:
            values = extract(candidate)
            if candidate.parent == named_dir:
                values = validate_templates({candidate.stem: next(iter(values.values())).text}, candidate)
            for name, template in values.items():
                if name in merged and merged[name].sha256 != template.sha256:
                    raise ChatpinError(f"Conflicting copies of template {name!r}; select a file explicitly")
                merged[name] = template
        return merged
    if path.suffix.lower() == ".gguf":
        with path.open("rb") as stream:
            return GGUFReader(stream).templates(path)
    if path.suffix.lower() == ".json":
        config = read_json(path)
        if not isinstance(config, dict):
            raise ChatpinError("Tokenizer config must be an object")
        return validate_templates(config.get("chat_template"), path)
    if path.suffix.lower() not in (".jinja", ".jinja2", ".j2"):
        raise ChatpinError("Expected a model directory, GGUF, tokenizer JSON, or Jinja file")
    return validate_templates(read_bounded(path).decode("utf-8"), path)


def select(path, name=None):
    templates = extract(path)
    if name is not None:
        if name not in templates:
            raise ChatpinError(f"Template {name!r} absent; available: {', '.join(templates)}")
        return templates[name]
    if len(templates) != 1:
        raise ChatpinError("Multiple templates found; choose explicitly with --template")
    return next(iter(templates.values()))
