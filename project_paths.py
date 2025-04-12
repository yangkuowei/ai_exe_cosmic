"""项目路径配置公共模块"""
from pathlib import Path

class ProjectPaths:
    """项目路径配置"""
    base_dir: Path = Path(__file__).parent.resolve()
    ai_promote: Path = base_dir / "ai_promote"
    requirements: Path = base_dir / "requirements"
    output: Path = base_dir / "out_put_files"
    
    # 各阶段输出文件前缀
    REQUIREMENT_PREFIX = "req_analysis_"
    TRIGGER_EVENT_PREFIX = "trigger_events_"
