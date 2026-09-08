"""Exact UTF-8 content pins. The reviewed lockfile is the trust root."""
import json
import os
from pathlib import Path
import re
import tempfile
from .sources import ChatpinError, digest, read_json


def write_file(path, data, force=False):
    path = Path(path)
    if not force:
        with path.open("xb") as stream:
            stream.write(data)
        return
    fd, temporary = tempfile.mkstemp(prefix=".chatpin-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def make_lock(template, upstream=None):
    result = {"schema_version": 1, "tool": "chatpin", "algorithm": "sha256",
              "template": {**template.summary(), "text": template.text},
              "upstream": upstream.summary() if upstream else None}
    return (json.dumps(result, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def load_lock(path):
    lock = read_json(path)
    if not isinstance(lock, dict) or type(lock.get("schema_version")) is not int or lock["schema_version"] != 1 or lock.get("algorithm") != "sha256":
        raise ChatpinError("Unsupported or malformed lockfile")
    entry = lock.get("template")
    if not isinstance(entry, dict) or not isinstance(entry.get("text"), str) or not entry["text"].strip():
        raise ChatpinError("Lockfile has no template text")
    if not isinstance(entry.get("name"), str) or not entry["name"]:
        raise ChatpinError("Invalid lockfile template name")
    if not isinstance(entry.get("sha256"), str) or not re.fullmatch(r"[a-f0-9]{64}", entry["sha256"]):
        raise ChatpinError("Invalid lockfile SHA-256")
    if digest(entry["text"]) != entry["sha256"]:
        raise ChatpinError("Lockfile embedded template does not match its hash")
    if type(entry.get("bytes")) is not int or entry["bytes"] != len(entry["text"].encode("utf-8")):
        raise ChatpinError("Invalid lockfile byte count")
    return lock
