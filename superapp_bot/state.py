# Shared in-memory state (survives only while the process is running)
user_state: dict[int, dict] = {}
user_histories: dict[int, list[dict]] = {}
