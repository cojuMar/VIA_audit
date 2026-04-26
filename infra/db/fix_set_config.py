"""
Sprint 22 mechanical conversion script.

Finds all `set_config('app.tenant_id', $1, false)` call sites and:
  1. Flips the third arg to `true` (transaction-local).
  2. Adds `, conn.transaction()` to the immediately-preceding
     `async with X.acquire() as conn:` line so the LOCAL setting is
     bound to a real transaction.

Idempotent: skips files where the pattern is already transaction-scoped.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "services"

# Match  await conn.execute("SELECT set_config('app.tenant_id', $1, false)" ...
RE_FALSE = re.compile(
    r"""(SELECT\s+set_config\(\s*['"]app\.tenant_id['"]\s*,\s*\$1\s*,\s*)false(\s*\))""",
    re.IGNORECASE,
)

# Match    async with <something>.acquire() as conn:
# Capture indent and the prefix so we can rewrite.
RE_ACQUIRE = re.compile(
    r"""^(?P<indent>\s*)async\s+with\s+(?P<expr>[A-Za-z_][\w\.\[\]]*)\.acquire\(\s*\)\s+as\s+(?P<var>conn)\s*:\s*$"""
)


def process(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    if "set_config('app.tenant_id'" not in text and 'set_config("app.tenant_id"' not in text:
        return False

    lines = text.splitlines(keepends=False)
    out = list(lines)
    changed = False

    for i, line in enumerate(lines):
        m = RE_FALSE.search(line)
        if not m:
            continue
        # Flip false → true.
        new_line = RE_FALSE.sub(lambda m: m.group(1) + "true" + m.group(2), line)
        if new_line != line:
            out[i] = new_line
            changed = True

        # Walk backwards to find the nearest enclosing async with X.acquire()
        for j in range(i - 1, max(-1, i - 6), -1):
            am = RE_ACQUIRE.match(out[j])
            if not am:
                continue
            # Skip if already has a transaction co-context.
            if "conn.transaction()" in out[j]:
                break
            indent = am.group("indent")
            expr = am.group("expr")
            out[j] = (
                f"{indent}async with {expr}.acquire() as conn, conn.transaction():"
            )
            changed = True
            break

    if changed:
        path.write_text("\n".join(out) + ("\n" if text.endswith("\n") else ""), encoding="utf-8")
    return changed


def main() -> None:
    converted = 0
    for py in ROOT.rglob("*.py"):
        if process(py):
            print(f"converted: {py.relative_to(ROOT.parent)}")
            converted += 1
    print(f"\n{converted} files modified.")


if __name__ == "__main__":
    main()
