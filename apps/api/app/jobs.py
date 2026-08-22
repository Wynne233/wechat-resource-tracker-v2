from __future__ import annotations

import sys

from .db import create_session, engine, ensure_runtime_schema
from .models import Base
from .repository import run_due_source_checks


def weekly_source_check() -> int:
    Base.metadata.create_all(bind=engine)
    ensure_runtime_schema()
    with create_session() as session:
        result = run_due_source_checks(session)
    print(
        "weekly source check completed: "
        f"articles={result.imported_count}, resources={result.resource_count}"
    )
    return 0


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] != "weekly-source-check":
        print("Usage: python -m app.jobs weekly-source-check", file=sys.stderr)
        return 2
    return weekly_source_check()


if __name__ == "__main__":
    raise SystemExit(main())
