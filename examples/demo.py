"""Run the full demonstration, asserting expected CI outcomes."""
from pathlib import Path
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
trusted = str(root / "examples" / "trusted.jinja")
modified = str(root / "examples" / "modified.jinja")


def step(label, arguments, expected=0):
    print(f"\n=== {label} ===", flush=True)
    result = subprocess.run([sys.executable, "-m", "chatpin", *arguments], check=False)
    if result.returncode != expected:
        raise SystemExit(f"Expected exit {expected}, got {result.returncode}")
    print(f"PASS: expected exit {expected}", flush=True)


with tempfile.TemporaryDirectory(prefix="chatpin-demo-") as directory:
    lock = str(Path(directory) / "chatpin.lock.json")
    pinned = str(Path(directory) / "pinned.jinja")
    step("Clean template", ["scan", trusted])
    step("Content-triggered change needs review", ["scan", modified], 1)
    step("Exact upstream diff", ["diff", modified, "--upstream", trusted], 1)
    step("Record reviewed baseline", ["lock", trusted, "--reviewed", "-o", lock])
    step("Original passes deployment check", ["check", trusted, "--lock", lock])
    step("Modified template fails deployment check", ["check", modified, "--lock", lock], 1)
    step("Export reviewed template", ["export", "--lock", lock, "-o", pinned])
    assert Path(pinned).read_bytes() == Path(trusted).read_bytes()
print("\nAll seven demo steps passed. Export exactly matches the reviewed template.")
