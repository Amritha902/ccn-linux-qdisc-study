#!/usr/bin/env python3
"""Inline every \input so the manuscript uploads to Overleaf as one file."""
import os, re

base = os.path.dirname(os.path.abspath(__file__))

def resolve(name):
    for cand in (name, name + ".tex"):
        p = os.path.normpath(os.path.join(base, cand))
        if os.path.exists(p):
            return p
    return None

def expand(text, depth=0):
    if depth > 5:
        return text
    def sub(m):
        p = resolve(m.group(1).strip())
        if not p:
            return m.group(0)
        return expand(open(p).read(), depth + 1)
    return re.sub(r"\\input\{([^}]+)\}", sub, text)

out = expand(open(os.path.join(base, "main.tex")).read())
dest = os.path.join(base, "submission.tex")
open(dest, "w").write(out)
print(f"wrote {dest} ({len(out.splitlines())} lines)")
