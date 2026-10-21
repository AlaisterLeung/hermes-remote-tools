"""Plugin config state, kept out of the root __init__ so the tool modules can import it without executing the loader entry."""

_config_getter = None  # set by register()


def set_config_getter(getter) -> None:
    global _config_getter
    _config_getter = getter


def get_config() -> dict:
    """Return the raw plugin settings mapping (empty when unset)."""
    if _config_getter is None:
        return {}
    value = _config_getter("targets", {})
    return value if isinstance(value, dict) else {}
