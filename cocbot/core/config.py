from dataclasses import dataclass
import math


def apply_settings(config, settings):
    """Validate supported user overrides without treating unknown keys as code."""
    version = settings.get("schema_version", 1)
    if type(version) is not int or version != 1:
        raise ValueError(f"Unsupported settings schema version: {version}")
    for section in ("controls", "waits", "recovery", "attack", "farm", "notifications"):
        if section in settings and not isinstance(settings[section], dict):
            raise ValueError(f"{section} settings must be an object")
    for name, point in settings.get("controls", {}).items():
        if not isinstance(point, dict) or not all(
            isinstance(point.get(axis), (int, float)) and not isinstance(point[axis], bool)
            and math.isfinite(point[axis]) and 0 <= point[axis] <= 1 for axis in ("x", "y")
        ):
            raise ValueError(f"Invalid normalized control: {name}")
    for name, seconds in settings.get("waits", {}).items():
        if isinstance(seconds, bool) or not isinstance(seconds, (int, float)) or not math.isfinite(seconds) or not 0 <= seconds <= 300:
            raise ValueError(f"Invalid wait: {name}")
    attack = settings.get("attack", {})
    duration, waves = attack.get("time_limit", 30), attack.get("max_waves", 3)
    if isinstance(duration, bool) or not isinstance(duration, (int, float)) or not math.isfinite(duration) or not 0 < duration <= 300:
        raise ValueError("attack.time_limit must be between 0 and 300 seconds")
    if type(waves) is not int or not 1 <= waves <= 20:
        raise ValueError("attack.max_waves must be between 1 and 20")
    retries = settings.get("recovery", {}).get("scan_restart_limit", 3)
    if type(retries) is not int or not 1 <= retries <= 20:
        raise ValueError("recovery.scan_restart_limit must be between 1 and 20")
    for name, values in settings.get("farm", {}).items():
        if name not in ("targets", "goals") or not isinstance(values, list) or len(values) != 3 or any(type(v) is not int or v < 0 for v in values):
            raise ValueError("farm must contain targets/goals with three non-negative integers")
    values = settings.get("vision", {})
    if not isinstance(values, dict):
        raise ValueError("vision settings must be an object")
    allowed = {"layout_backend", "smart_farm_confidence", "smart_farm_iou", "template_threshold", "state_timeout"}
    if set(values) - allowed:
        raise ValueError(f"Unknown vision settings: {sorted(set(values) - allowed)}")
    for name, value in values.items():
        if name == "layout_backend":
            if value not in ("smart_farm", "legacy"):
                raise ValueError("layout_backend must be smart_farm or legacy")
        else:
            limit = 60 if name == "state_timeout" else 1
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 < value <= limit:
                raise ValueError(f"Invalid {name}: {value}")
        setattr(config, name, value)
    return config


@dataclass
class AppConfig:
    model_path: str = "models/best.pt"
    conf: float = 0.5
    # None = auto-detect (use CUDA when available). Set True/False to force.
    gpu: bool | None = None
    max_retries: int = 4
    state_guard_enabled: bool = True
    state_timeout: float = 12.0
    template_threshold: float = 0.85
    layout_backend: str = "smart_farm"  # smart_farm or legacy
    smart_farm_confidence: float = 0.25
    smart_farm_iou: float = 0.45

    # ADB background mode (the only mode). Coordinates from the vision layer
    # are guest pixels; no window focus/visibility is required.
    adb_host: str = "127.0.0.1"
    adb_port: int = 5555
    adb_path: str = ""  # empty = auto-detect (PATH / platform-tools / LDPlayer)

    # YOLO class labels used across the bot
    ATTACK_BTN_HOME: str = "attack_btn_home"
    FIND_BTN: str = "find_btn"
    ATTACK_BTN: str = "attack_btn"

    # Resource text labels (top bar during search)
    GOLD: str = "gold"
    ELIXIR: str = "elixir"
    D_ELIXIR: str = "d_elixir"

    # Base layout labels
    S_GOBLIN: str = "s_goblin"
    ELIXIRS: str = "elixirs"
    NXT_BTN: str = "nxt_btn"
    GOLDS: str = "golds"
    D_ELIXIRS: str = "d_elixirs"

    # Post-battle / surrender labels
    SURR_BTN: str = "surr"
    SURR_CONF: str = "surr_conf"

    # Scan-failure recovery: spots tapped (one each) before retrying
    RETRY_BTN_1: str = "retry_btn_1"
    RETRY_BTN_2: str = "retry_btn_2"
    RETRY_BTN_3: str = "retry_btn_3"

    POST_GOLD: str = "post_gold"
    POST_ELIXIR: str = "post_elixir"
    POST_D_ELIXIR: str = "post_d_elixir"
    RETURN_HOME: str = "return_home"
