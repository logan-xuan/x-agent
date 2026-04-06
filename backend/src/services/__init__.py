"""Service layer for X-Agent."""

__all__ = [
    "StorageService",
    "SkillParser",
    "parse_skill_metadata",
    "SkillParseError",
    "SkillRegistry",
    "get_skill_registry",
    "reset_skill_registry",
]


def __getattr__(name: str):
    if name == "StorageService":
        from .storage import StorageService

        return StorageService
    if name in {"SkillParser", "parse_skill_metadata", "SkillParseError"}:
        from .skill_parser import SkillParseError, SkillParser, parse_skill_metadata

        return {
            "SkillParser": SkillParser,
            "parse_skill_metadata": parse_skill_metadata,
            "SkillParseError": SkillParseError,
        }[name]
    if name in {"SkillRegistry", "get_skill_registry", "reset_skill_registry"}:
        from .skill_registry import SkillRegistry, get_skill_registry, reset_skill_registry

        return {
            "SkillRegistry": SkillRegistry,
            "get_skill_registry": get_skill_registry,
            "reset_skill_registry": reset_skill_registry,
        }[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
