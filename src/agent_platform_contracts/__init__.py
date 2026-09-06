"""B0 Agent Platform Contracts v0.2.0."""

from .assets_api import asset_path
from .models import COMMON_MODELS, RESOURCE_MODELS

__all__ = ["COMMON_MODELS", "RESOURCE_MODELS", "asset_path"]
__version__ = "0.2.0"
