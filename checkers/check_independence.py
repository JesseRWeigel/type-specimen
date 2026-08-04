#!/usr/bin/env python3
"""Prove, by reading the source rather than by assertion in a README, that the checker and the
generator share no code.

The claim being proved has two halves, and only both together mean anything:

  1. ``checkers/check_font_facts.py`` never reaches ``typespec`` or ``fontTools``, at any depth
     of its import graph, and has no dynamic-import escape hatch.
  2. ``typespec`` DOES reach ``fontTools``.

Without the second half the claim is vacuous: two modules that both parse bytes with ``struct``
in the same way would satisfy the first half and still share every assumption. Here one derivation
goes through a mature font library and the other through a hand-written sfnt reader, so a bug
would have to occur identically in both to pass unnoticed.

    python3 checkers/check_independence.py
"""

import ast
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHECKER = os.path.join(REPO, "checkers", "check_font_facts.py")
GENERATOR_PACKAGE = os.path.join(REPO, "typespec")
FORBIDDEN_IN_CHECKER = ("typespec", "fontTools")
DYNAMIC_IMPORT_NAMES = ("__import__", "eval", "exec", "compile")
DYNAMIC_IMPORT_ATTRS = ("import_module", "load_module", "exec_module", "SourceFileLoader")


def module_imports(path):
    """Top-level module names imported by one file, plus any dynamic-import escape hatches."""
    with open(path, encoding="utf-8") as fh:
        tree = ast.parse(fh.read(), filename=path)
    modules, dynamic = set(), []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level:                       # a relative import, resolved by the caller
                modules.add("." * node.level + (node.module or ""))
            elif node.module:
                modules.add(node.module)
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id in DYNAMIC_IMPORT_NAMES:
                dynamic.append(f"{func.id}() at line {node.lineno}")
            elif isinstance(func, ast.Attribute) and func.attr in DYNAMIC_IMPORT_ATTRS:
                dynamic.append(f".{func.attr}() at line {node.lineno}")
    return modules, dynamic


def resolve(module, from_path):
    """The file a module name refers to inside this repository, or None if it is external."""
    if module.startswith("."):
        base = os.path.dirname(from_path)
        name = module.lstrip(".")
        up = len(module) - len(module.lstrip(".")) - 1
        for _ in range(up):
            base = os.path.dirname(base)
        parts = name.split(".") if name else []
    else:
        base = REPO
        parts = module.split(".")
    candidate = os.path.join(base, *parts)
    if os.path.isfile(candidate + ".py"):
        return candidate + ".py"
    if os.path.isdir(candidate) and os.path.isfile(os.path.join(candidate, "__init__.py")):
        return os.path.join(candidate, "__init__.py")
    return None


def closure(entry):
    """Every repo file reachable from ``entry`` by import, and every external module named."""
    seen_files, external, dynamic = set(), set(), []
    queue = [entry]
    while queue:
        path = queue.pop()
        if path in seen_files:
            continue
        seen_files.add(path)
        modules, found_dynamic = module_imports(path)
        for hit in found_dynamic:
            dynamic.append(f"{os.path.relpath(path, REPO)}: {hit}")
        for module in modules:
            target = resolve(module, path)
            if target is None:
                external.add(module.split(".")[0] if not module.startswith(".") else module)
            else:
                queue.append(target)
                # A relative import inside a package also pulls in the package itself.
                pkg_init = os.path.join(os.path.dirname(target), "__init__.py")
                if os.path.isfile(pkg_init):
                    queue.append(pkg_init)
    return seen_files, external, dynamic


def main():
    problems = []

    files, external, dynamic = closure(CHECKER)
    local = sorted(os.path.relpath(f, REPO) for f in files)
    for name in FORBIDDEN_IN_CHECKER:
        if any(mod == name or mod.startswith(name + ".") for mod in external):
            problems.append(f"the checker imports {name}, so it is not independent")
        if any(rel.startswith(name + os.sep) for rel in local):
            problems.append(f"the checker reaches a file inside {name}/, so it is not independent")
    if dynamic:
        problems.append("the checker can import at runtime, which this proof cannot see through: "
                        + "; ".join(dynamic))

    gen_entry = os.path.join(GENERATOR_PACKAGE, "cli.py")
    gen_files, gen_external, _ = closure(gen_entry)
    if not any(mod == "fontTools" for mod in gen_external):
        problems.append("the generator does not import fontTools, so the two derivations are not "
                        "as different as this proof claims")

    print(f"checker entry     {os.path.relpath(CHECKER, REPO)}")
    print(f"  reaches {len(files)} file(s) in this repo: {', '.join(local)}")
    print(f"  external modules: {', '.join(sorted(external))}")
    print(f"generator entry   {os.path.relpath(gen_entry, REPO)}")
    print(f"  reaches {len(gen_files)} file(s) in this repo")
    print(f"  external modules: {', '.join(sorted(gen_external))}")

    if problems:
        for problem in problems:
            print(f"FAIL  {problem}")
        return 1
    print("ok    the checker shares no code with the generator, and the two read the font by "
          "different means")
    return 0


if __name__ == "__main__":
    sys.exit(main())
