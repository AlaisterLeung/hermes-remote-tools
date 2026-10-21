"""hermes-remote-tools - Remote execution tools for configured SSH hosts."""

import logging
from pathlib import Path

from . import remote_config, remote_pool
from .remote_tools import TOOLS

logger = logging.getLogger(__name__)

TOOLSET = "remote_tools"

_SKILLS: dict[str, str] = {
    "remote-hosts": (
        "Run commands or do file operations on a remote SSH host through the hermes-remote-tools plugin."
    ),
}


def register(ctx) -> None:
    remote_config.load(ctx)
    ctx.on_unload(remote_pool.shutdown)

    for name, schema, handler, check_fn, emoji in TOOLS:
        ctx.register_tool(
            name=name,
            toolset=TOOLSET,
            schema=schema,
            handler=handler,
            check_fn=check_fn,
            emoji=emoji,
        )

    logger.info("hermes-remote-tools: registered %d tools", len(TOOLS))

    skills_dir = Path(__file__).parent / "skills"
    for name, description in _SKILLS.items():
        skill_md = skills_dir / name / "SKILL.md"
        if not skill_md.is_file():
            continue
        try:
            ctx.register_skill(
                name=name,
                path=skill_md,
                description=description,
                frontmatter={"name": name, "description": description},
            )
        except Exception as exc:
            logger.warning("hermes-remote-tools: skill %s skipped: %s", name, exc)


__all__ = ["register"]
