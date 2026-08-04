#!/usr/bin/env python3
"""Apply one exact textual substitution, and refuse to pretend it worked.

A sabotage that did not apply is a no-op with a confident write-up attached. Every failure mode
below has actually happened somewhere, so each one exits non-zero rather than continuing:

  * the target text is not in the file
  * the target text appears more than once, so which one was hit is ambiguous
  * the replacement equals the original

    python3 scripts/patch.py FILE OLD NEW
"""

import pathlib
import sys


def main(argv):
    if len(argv) != 3:
        print("usage: patch.py FILE OLD NEW", file=sys.stderr)
        return 2
    path, old, new = argv
    p = pathlib.Path(path)
    if not p.exists():
        print(f"PATCH DID NOT APPLY: no such file {path}", file=sys.stderr)
        return 1
    text = p.read_text(encoding="utf-8")
    count = text.count(old)
    if count == 0:
        print(f"PATCH DID NOT APPLY: {old!r} is not in {path}", file=sys.stderr)
        return 1
    if count > 1:
        print(f"PATCH IS AMBIGUOUS: {old!r} appears {count} times in {path}", file=sys.stderr)
        return 1
    if old == new:
        print("PATCH IS A NO-OP: the replacement equals the original", file=sys.stderr)
        return 1
    p.write_text(text.replace(old, new, 1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
