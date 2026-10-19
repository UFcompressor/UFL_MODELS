"""Compatibility launcher; registration implementation lives in CAESAR."""

import os
from pathlib import Path
import subprocess
import sys

if __name__ == "__main__":
    source = Path(
        os.environ.get(
            "CAESAR_SOURCE_DIR", str(Path(__file__).resolve().parent.parent / "CAESAR")
        )
    )
    script = source / "register_model.py"
    if not script.is_file():
        raise SystemExit(
            "Set CAESAR_SOURCE_DIR to a CAESAR checkout containing register_model.py"
        )
    args = sys.argv[1:]
    if args == ["--check"]:
        args = ["check"]
    if args and args[0] in ("check", "sync") and "--database" not in args:
        args += ["--database", str(Path(__file__).resolve().parent)]
    raise SystemExit(subprocess.call([sys.executable, str(script), *args]))
