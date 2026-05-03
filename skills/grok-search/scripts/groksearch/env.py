import os
from pathlib import Path
from typing import Optional


def load_dotenv(env_path: Optional[Path] = None) -> bool:
    search_paths = []
    if env_path:
        search_paths.append(env_path)
    else:
        script_dir = Path(__file__).resolve().parent.parent
        search_paths.append(Path.cwd() / ".env")
        search_paths.append(script_dir / ".env")
        search_paths.append(script_dir.parent / ".env")

    for path in search_paths:
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith("#"):
                            continue
                        if "=" not in line:
                            continue
                        key, _, value = line.partition("=")
                        key = key.strip()
                        value = value.strip()
                        if (value.startswith('"') and value.endswith('"')) or (
                            value.startswith("'") and value.endswith("'")
                        ):
                            value = value[1:-1]
                        if key and key not in os.environ:
                            os.environ[key] = value
                return True
            except IOError:
                continue
    return False
