"""Plugin config: the targets mapping, captured once at register()."""

TARGETS: dict = {}


def load(ctx) -> None:
    """Load the plugin config at register(). Config edits take effect on restart. Validation is done at call time."""

    global TARGETS
    value = ctx.get_config("targets", {})
    TARGETS = value if isinstance(value, dict) else {}
