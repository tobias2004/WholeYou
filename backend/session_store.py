from typing import Any

# Local MVP storage only. Production should replace this with per-user signed
# sessions and encrypted token storage.
SESSION_DATA: dict[str, Any] = {}
