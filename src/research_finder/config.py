from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

load_dotenv()

DEFAULT_CONFIG_PATH = Path(__file__).parent.parent.parent / "config.yaml"


def load_config(config_path: Path | None = None) -> dict[str, Any]:
    """Load configuration from YAML file with env var overrides."""
    path = config_path or DEFAULT_CONFIG_PATH
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with open(path) as f:
        config = yaml.safe_load(f)

    # Resolve API keys from env vars
    if "llm" in config and "api_key_env" in config["llm"]:
        env_var = config["llm"]["api_key_env"]
        config["llm"]["api_key"] = os.environ.get(env_var, "")

    return config
