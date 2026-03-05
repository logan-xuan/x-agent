Phase 3: 资格评估与多源加载 (长期)
3.1 技能资格评估器
python
# backend/src/services/skill/eligibility.py

@dataclass
class SkillRequirements:
    os: list[str] | None = None
    bins: list[str] | None = None
    any_bins: list[str] | None = None
    env: list[str] | None = None
    config: list[str] | None = None

class SkillEligibilityChecker:
    def __init__(self, config: dict):
        self.config = config
        self.platform = sys.platform  # darwin/linux/win32
    
    def should_include(self, skill: SkillEntry) -> bool:
        """评估技能是否应该包含"""
        req = skill.metadata.requires if skill.metadata else None
        if not req:
            return True
        
        # OS 检查
        if req.os and self.platform not in self._normalize_os(req.os):
            return False
        
        # 必需二进制检查
        if req.bins and not all(self._has_binary(b) for b in req.bins):
            return False
        
        # 任一二进制检查
        if req.any_bins and not any(self._has_binary(b) for b in req.any_bins):
            return False
        
        # 环境变量检查
        if req.env and not all(os.environ.get(e) for e in req.env):
            return False
        
        return True
    
    def _has_binary(self, name: str) -> bool:
        return shutil.which(name) is not None
    
    def _normalize_os(self, os_list: list[str]) -> set[str]:
        mapping = {"macos": "darwin", "mac": "darwin", "windows": "win32"}
        return {mapping.get(o.lower(), o.lower()) for o in os_list}
3.2 多源技能加载
python
# backend/src/services/skill/loader.py

class MultiSourceSkillLoader:
    """多源技能加载器，优先级：workspace > project > personal > managed > bundled"""
    
    SKILL_SOURCES = [
        ("bundled", lambda cfg: Path(__file__).parent.parent.parent / "skills"),
        ("managed", lambda cfg: Path.home() / ".x-agent" / "skills"),
        ("personal", lambda cfg: Path.home() / ".agents" / "skills"),
        ("project", lambda cfg: Path(cfg.get("workspace", {}).get("path", ".")) / ".agents" / "skills"),
        ("workspace", lambda cfg: Path(cfg.get("workspace", {}).get("path", ".")) / "skills"),
    ]
    
    def load_all(self, config: dict) -> dict[str, SkillEntry]:
        """加载所有技能，后者覆盖前者"""
        merged = {}
        for source_name, path_fn in self.SKILL_SOURCES:
            skills_dir = path_fn(config)
            if not skills_dir.exists():
                continue
            for skill in self._load_from_dir(skills_dir, source_name):
                merged[skill.name] = skill  # 后者覆盖前者
        return merged
