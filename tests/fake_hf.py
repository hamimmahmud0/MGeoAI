#!/usr/bin/env python3
"""Offline stand-in for the `hf` CLI used by the backup tests: buckets map to a directory."""
import os
import shutil
import sys
from pathlib import Path

base = Path(os.environ["FAKE_BUCKET_DIR"])


def remote(uri: str) -> Path:
    return base / uri.split("hf://buckets/", 1)[1].split("/", 2)[2]


args = sys.argv[1:]
if args[:2] == ["buckets", "sync"]:
    src, dest = Path(args[2]), remote(args[3])
    for item in src.rglob("*"):
        if item.is_file():
            target = dest / item.relative_to(src)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, target)
elif args[:2] == ["buckets", "cp"]:
    source, destination = args[2], args[3]
    if source.startswith("hf://"):
        found = remote(source)
        if not found.exists():
            print("not found", file=sys.stderr)
            sys.exit(1)
        shutil.copy2(found, destination)
    else:
        target = remote(destination)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
