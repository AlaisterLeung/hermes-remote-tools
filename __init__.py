"""Hermes plugin providing remote execution tools for configured SSH hosts.

Loader entry: the plugin manager imports this package's __init__ and calls register(ctx). All implementation lives in the remote_tools subpackage.
The imports are lazy so test collection can import this module without a parent package (register is only ever called by the loader, which has one).
"""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_toolset = "remote_tools"


def register(ctx) -> None:
    from .remote_tools import plugin_state, remote_pool
    from .tools import TOOLS

    plugin_state.set_config_getter(ctx.get_config)
    ctx.on_unload(remote_pool.shutdown)
    for name, schema, handler, check_fn, emoji in TOOLS:
        ctx.register_tool(
            name=name,
            toolset=_toolset,
            schema=schema,
            handler=handler,
            check_fn=check_fn,
            emoji=emoji,
        )
    _register_skills(ctx, Path(__file__).parent / "skills")
    logger.info("hermes-remote-tools: registered %d tools", len(TOOLS))


def _register_skills(ctx, skills_root: Path) -> None:
    """Register every skills/<name>/SKILL.md in the repo as a plugin skill."""
    if not skills_root.is_dir():
        return
    from agent.skill_utils import yaml_load

    for child in sorted(skills_root.iterdir()):
        skill_md = child / "SKILL.md"
        if not child.is_dir() or not skill_md.is_file():
            continue
        try:
            content = skill_md.read_text(encoding="utf-8-sig").lstrip("\ufeff")
            if not content.startswith("---"):
                raise ValueError("missing YAML frontmatter")
            end = content.find("\n---", 3)
            if end == -1:
                raise ValueError("unterminated YAML frontmatter")
            frontmatter = yaml_load(content[3:end]) or {}
            if not isinstance(frontmatter, dict):
                raise TypeError("frontmatter must be an object")
            ctx.register_skill(
                name=str(frontmatter.get("name") or child.name),
                path=skill_md,
                description=str(frontmatter.get("description") or ""),
                frontmatter=frontmatter,
            )
        except Exception as exc:
            logger.warning("hermes-remote-tools: skill %s skipped: %s", child.name, exc)


__all__ = ["register"]
