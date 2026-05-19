import os
import uuid
from dataclasses import dataclass, asdict
from pathlib import Path

import tomli
import tomli_w

CONFIG_DIR = Path(os.environ.get("EMUSYNC_CONFIG_DIR", str(Path.home() / ".emusync")))
CONFIG_FILE = CONFIG_DIR / "emusync.toml"


@dataclass
class Config:
    server_host: str = ""
    server_port: int = 8765
    data_dir: str = str(Path.home() / ".emusync")
    device_id: str = ""
    device_name: str = ""
    token: str = ""
    is_server: bool = False


def load() -> Config:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if not CONFIG_FILE.exists():
        cfg = Config(
            device_id=str(uuid.uuid4()),
            device_name=os.uname().nodename,
        )
        save(cfg)
        return cfg
    with open(CONFIG_FILE, "rb") as f:
        data = tomli.load(f)
    defaults = asdict(Config())
    return Config(**{k: data.get(k, defaults[k]) for k in defaults})


def save(cfg: Config):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "wb") as f:
        tomli_w.dump(asdict(cfg), f)
