"""One-shot: fix nested single-quote syntax error in set_config calls."""
from pathlib import Path

OLD = "'SELECT set_config('app.tenant_id', $1, true)'"
NEW = "\"SELECT set_config('app.tenant_id', $1, true)\""

ROOT = Path(__file__).resolve().parents[2] / "services"
n = 0
for py in ROOT.rglob("*.py"):
    text = py.read_text(encoding="utf-8")
    if OLD in text:
        py.write_text(text.replace(OLD, NEW), encoding="utf-8")
        print(f"fixed: {py.relative_to(ROOT.parent)}")
        n += 1
print(f"\n{n} files fixed.")
