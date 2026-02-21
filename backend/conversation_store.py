"""
In-memory conversation store for multi-turn chat.
Maps conversation_id -> list of {role, content}. Capped per conversation to limit tokens.
"""
from collections import OrderedDict

# Max messages to keep per conversation (user + assistant pairs). 6 = last 3 exchanges.
MAX_HISTORY_MESSAGES = 6

_store: dict[str, list[dict]] = {}


def get_history(conversation_id: str) -> list[dict]:
    """Return list of {role, content} for the conversation, most recent last. Empty if new."""
    return list(_store.get(conversation_id, []))


def append_turn(conversation_id: str, user_content: str, assistant_content: str) -> None:
    """Append one user message and one assistant reply. Trim to MAX_HISTORY_MESSAGES."""
    if conversation_id not in _store:
        _store[conversation_id] = []
    history = _store[conversation_id]
    history.append({"role": "user", "content": user_content})
    history.append({"role": "assistant", "content": assistant_content})
    # Keep only the last N messages
    if len(history) > MAX_HISTORY_MESSAGES:
        _store[conversation_id] = history[-MAX_HISTORY_MESSAGES:]
