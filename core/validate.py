# src/core/validate.py
from pathlib import Path
from .config import AppConfig

def validate_config(cfg: AppConfig) -> list[str]:
    """Validate configuration and return list of warnings/errors"""
    issues = []
    
    # Check model files
    for model_data in cfg.models:
        model_path = Path(model_data['path'])
        if not model_path.exists() and not model_data.get('url'):
            issues.append(f"⚠️ Model '{model_data['name']}' has no file and no download URL")
    
    # Check directory permissions
    for path_name, path_str in cfg.paths.model_dump().items():
        path = Path(path_str).parent
        if not path.exists():
            try:
                path.mkdir(parents=True, exist_ok=True)
            except PermissionError:
                issues.append(f"❌ No write permission for {path_name}: {path}")
    
    # Check quiet hours
    a, b = cfg.assistant.quiet_hours
    if not (0 <= a < 24 and 0 <= b < 24):
        issues.append(f"⚠️ Invalid quiet_hours: {cfg.assistant.quiet_hours}")
    
    # Check code execution safety
    if cfg.assistant.allow_code_exec:
        issues.append("⚠️ Code execution enabled - ensure you trust all inputs!")
    
    return issues