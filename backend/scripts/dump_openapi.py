"""Write the OpenAPI contract to docs/openapi.json without running a server.

The snapshot used to be taken with `curl http://localhost:8000/openapi.json`,
which meant it silently went stale whenever nobody had an instance running. The
app object builds the schema on import, so the same file can be produced offline
and diffed in CI (see the `openapi` job in .github/workflows/ci.yml).

Read-only: it touches no database and starts no scheduler.

    cd backend && python scripts/dump_openapi.py          # rewrite the snapshot
    cd backend && python scripts/dump_openapi.py --check  # fail if it is stale
"""
import json
import os
import pathlib
import sys

BACKEND = pathlib.Path(__file__).resolve().parent.parent
ROOT = BACKEND.parent
OUT = ROOT / "docs" / "openapi.json"

os.environ.setdefault("DISABLE_SCHEDULER", "1")
sys.path.insert(0, str(BACKEND))

from app.main import app  # noqa: E402  (import after sys.path/env are set)


def render() -> str:
    return json.dumps(app.openapi(), indent=2, ensure_ascii=False) + "\n"


if __name__ == "__main__":
    text = render()
    if "--check" in sys.argv:
        current = OUT.read_text(encoding="utf-8") if OUT.exists() else ""
        if current != text:
            print(f"{OUT.relative_to(ROOT)} is out of date. "
                  f"Run: python backend/scripts/dump_openapi.py", file=sys.stderr)
            sys.exit(1)
        print(f"{OUT.relative_to(ROOT)} matches the live contract.")
    else:
        OUT.write_text(text, encoding="utf-8")
        print(f"wrote {OUT.relative_to(ROOT)} ({len(text):,} bytes, "
              f"{len(app.openapi()['paths'])} paths)")
