#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyzipper", "pillow"]
# ///
"""Decrypt already-released cases into decrypted/case_NNN (skips existing). usage: pull_cases.py <from> <to>"""
import sys, pathlib
from opus_case import fetch_key, find_zip, decrypt, HERE
for g in range(int(sys.argv[1]), int(sys.argv[2]) + 1):
    d = HERE / "decrypted" / f"case_{g:03d}"
    if d.exists() and any(d.iterdir()):
        continue
    d.mkdir(parents=True, exist_ok=True)
    decrypt(find_zip(g), fetch_key(g), d)
    print(g, sorted(p.name for p in d.rglob("*") if p.is_file()))
