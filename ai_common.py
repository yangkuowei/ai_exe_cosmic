from typing import TypeVar, Any, Optional
from dataclasses import dataclass
import logging
import os
from pathlib import Path
# 配置基础日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

T = TypeVar('T')

class AIError(Exception):
    """Base exception for AI operations"""
    def __init__(self, message: str, max_retries: int = None):
        super().__init__(message)
        self.max_retries = max_retries

class ValidationError(AIError):
    """Data validation failed after max retries"""

class ConfigurationError(AIError):
    """Invalid configuration detected"""

@dataclass
class ModelConfig:
    """AI模型通用配置类"""
    provider: str
    base_url: str
    model_name: str
    api_key: Optional[str] = None
    temperature: float = 1.3
    max_tokens: int = 8192
    timeout: float = 30.0
    max_retries: int = 3

    def validate(self) -> None:
        """验证配置有效性"""
        errors = []
        if not self.base_url:
            errors.append(f"{self.provider}配置缺少base_url")
        if not self.model_name:
            errors.append(f"{self.provider}配置缺少model_name")
            
        if self.temperature < 0 or self.temperature > 2:
            errors.append("temperature必须在0~2之间")
            
        if errors:
            raise ConfigurationError("\n".join(errors))


def load_model_config(provider: str = None, config_dir: str = None,model_name :str = None) -> ModelConfig:
    """加载指定供应商的模型配置

    Args:
        provider: 服务商名称 (可选)
        config_dir: 配置文件目录路径 (可选)

    Returns:
        ModelConfig: 验证通过的配置对象

    Raises:
        ConfigurationError: 配置加载或验证失败时抛出
    """
    import yaml
    from typing import cast

    try:
        # 动态获取配置文件路径
        base_dir = Path(config_dir) if config_dir else Path(__file__).parent
        config_path = base_dir / "configs/model_providers.yaml"

        if not config_path.exists():
            raise ConfigurationError(f"配置文件不存在: {config_path}")

        with open(config_path, encoding='utf-8') as f:
            config_data = yaml.safe_load(f) or {}

        # 获取默认提供商
        default_provider = config_data.get('default_provider', 'aliyun')
        selected_provider = provider.lower() if provider else default_provider

        # 获取提供商配置
        provider_config = config_data.get('providers', {}).get(selected_provider)
        if not provider_config:
            available = ', '.join(config_data.get('providers', {}).keys())
            raise ConfigurationError(
                f"不支持的供应商: {selected_provider}，可用供应商: {available}"
            )

        # 类型安全的配置获取
        env_mapping = cast(dict, provider_config.get('env_mapping', {}))
        base_url = os.getenv(
            env_mapping.get('base_url', ''),
            provider_config.get('base_url', '')
        )
        if model_name == None:
            model_name = os.getenv(
                env_mapping.get('model_name', ''),
                provider_config.get('model_name', '')
            )
        api_key = os.getenv(env_mapping.get('api_key', ''))

        # 构建配置对象
        config = ModelConfig(
            provider=selected_provider,
            base_url=base_url,
            model_name=model_name,
            api_key=api_key,
            temperature=provider_config.get('temperature', 0.1),
            max_tokens=provider_config.get('max_tokens', 8000),
            timeout=provider_config.get('timeout', 60.0),
            max_retries=provider_config.get('max_chat_count', 3)
        )

        config.validate()
        return config

    except yaml.YAMLError as ye:
        raise ConfigurationError(f"配置文件解析失败: {str(ye)}") from ye
    except IOError as ioe:
        raise ConfigurationError(f"配置文件读取失败: {str(ioe)}") from ioe
