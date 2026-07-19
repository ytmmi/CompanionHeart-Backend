"""插件基础模型定义"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class PluginServiceConfig:
    """插件服务配置"""
    port: int
    health_check: str = "/health"
    protocol: str = "http"


@dataclass
class PluginAPIConfig:
    """插件API端点配置"""
    synthesize: Optional[str] = None  # TTS
    stream: Optional[str] = None  # TTS
    voices: Optional[str] = None  # TTS
    chat: Optional[str] = None  # LLM
    chat_stream: Optional[str] = None  # LLM
    models: Optional[str] = None  # LLM


@dataclass
class Plugin:
    """插件元数据"""
    name: str
    version: str
    type: str  # tts / llm / asr
    description: str
    author: str
    path: Path
    service: PluginServiceConfig
    api: PluginAPIConfig
    dependencies: list[str] = field(default_factory=list)
    repository: Optional[str] = None

    @classmethod
    def from_yaml(cls, config_path: Path) -> "Plugin":
        """从 plugin.yaml 加载插件元数据"""
        import yaml

        with open(config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        service_data = data.get("service", {})
        api_data = data.get("api", {})

        return cls(
            name=data["name"],
            version=data["version"],
            type=data["type"],
            description=data["description"],
            author=data.get("author", "Unknown"),
            path=config_path.parent,
            service=PluginServiceConfig(
                port=service_data["port"],
                health_check=service_data.get("health_check", "/health"),
                protocol=service_data.get("protocol", "http"),
            ),
            api=PluginAPIConfig(
                synthesize=api_data.get("synthesize"),
                stream=api_data.get("stream"),
                voices=api_data.get("voices"),
                chat=api_data.get("chat"),
                chat_stream=api_data.get("chat_stream"),
                models=api_data.get("models"),
            ),
            dependencies=data.get("dependencies", []),
            repository=data.get("repository"),
        )

    @property
    def base_url(self) -> str:
        """获取插件服务的基础URL"""
        return f"{self.service.protocol}://localhost:{self.service.port}"
