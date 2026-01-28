"""Configuration file tools with structured output."""
from typing import Optional, Type, Dict, Any
import json
import yaml
from pathlib import Path
from pydantic import BaseModel, Field

try:
    from serena.tools.base import BaseTool
except ImportError:
    class BaseTool:
        pass


class ReadConfigInput(BaseModel):
    path: str = Field(..., description="Path to configuration file")
    format: Optional[str] = Field(None, description="Format (json, yaml). Auto-detected if None")


class ReadConfigTool(BaseTool):
    name = "read_config"
    description = "Read a configuration file (JSON/YAML) into a dictionary"
    args_schema: Type[BaseModel] = ReadConfigInput

    def _execute(self, path: str, format: Optional[str]) -> Dict[str, Any]:
        """Internal method returning structured data."""
        file_path = Path(path)
        if not file_path.exists():
            return {
                "error": {
                    "code": "FILE_NOT_FOUND",
                    "message": f"File not found at {path}"
                }
            }

        try:
            content = file_path.read_text(encoding='utf-8')
            fmt = format.lower() if format else file_path.suffix.lstrip('.')

            if fmt in ['json']:
                data = json.loads(content)
            elif fmt in ['yaml', 'yml']:
                data = yaml.safe_load(content)
            else:
                return {
                    "error": {
                        "code": "UNSUPPORTED_FORMAT",
                        "message": f"Unsupported format {fmt}. Use json or yaml."
                    }
                }

            return {"config": data}
        except Exception as e:
            return {
                "error": {
                    "code": "PARSE_ERROR",
                    "message": str(e)
                }
            }

    def _run(self, path: str, format: Optional[str] = None) -> str:
        """BaseTool-compatible method returning JSON string."""
        result = self._execute(path, format)
        return json.dumps(result, indent=2, ensure_ascii=False)


class UpdateConfigInput(BaseModel):
    path: str = Field(..., description="Path to configuration file")
    key: str = Field(..., description="Dot-notation key to update (e.g. 'server.port')")
    value: str = Field(..., description="New value (parsed as JSON if possible)")


class UpdateConfigTool(BaseTool):
    name = "update_config"
    description = "Update a specific key in a configuration file"
    args_schema: Type[BaseModel] = UpdateConfigInput

    def _set_nested(self, data: Dict, key: str, value: Any):
        """Set nested dictionary value using dot notation."""
        parts = key.split('.')
        current = data
        for part in parts[:-1]:
            if part not in current:
                current[part] = {}
            current = current[part]
            if not isinstance(current, dict):
                raise ValueError(f"Cannot traverse path {key}: {part} is not a dict")
        current[parts[-1]] = value

    def _parse_value(self, value_str: str) -> Any:
        """Parse value string as JSON or return as string."""
        try:
            return json.loads(value_str)
        except:
            return value_str

    def _execute(self, path: str, key: str, value: str) -> Dict[str, Any]:
        """Internal method returning structured data."""
        file_path = Path(path)
        if not file_path.exists():
            return {
                "error": {
                    "code": "FILE_NOT_FOUND",
                    "message": f"File not found at {path}"
                }
            }

        try:
            content = file_path.read_text(encoding='utf-8')
            fmt = file_path.suffix.lstrip('.').lower()

            if fmt == 'json':
                data = json.loads(content)
            elif fmt in ['yaml', 'yml']:
                data = yaml.safe_load(content) or {}
            else:
                return {
                    "error": {
                        "code": "UNSUPPORTED_FORMAT",
                        "message": f"Unsupported format {fmt}"
                    }
                }

            parsed_value = self._parse_value(value)
            self._set_nested(data, key, parsed_value)

            if fmt == 'json':
                new_content = json.dumps(data, indent=2, ensure_ascii=False)
            else:
                new_content = yaml.safe_dump(data, allow_unicode=True)

            file_path.write_text(new_content, encoding='utf-8')
            return {"message": "Config updated successfully", "key": key, "value": parsed_value}

        except Exception as e:
            return {
                "error": {
                    "code": "UPDATE_ERROR",
                    "message": str(e)
                }
            }

    def _run(self, path: str, key: str, value: str) -> str:
        """BaseTool-compatible method returning JSON string."""
        result = self._execute(path, key, value)
        return json.dumps(result, ensure_ascii=False)
