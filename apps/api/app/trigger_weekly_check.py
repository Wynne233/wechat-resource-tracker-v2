from __future__ import annotations

import os
import urllib.error
import urllib.request


def main() -> int:
    api_url = os.getenv("SCHEDULER_API_URL", "").rstrip("/")
    token = os.getenv("SCHEDULER_TOKEN", "")
    if not api_url or not token:
        raise RuntimeError("SCHEDULER_API_URL and SCHEDULER_TOKEN must be configured.")

    request = urllib.request.Request(
        f"{api_url}/internal/jobs/weekly-source-check",
        method="POST",
        headers={"X-Scheduler-Token": token, "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            print(response.read().decode("utf-8", errors="replace"))
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Weekly source check request failed: {exc}") from exc
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
