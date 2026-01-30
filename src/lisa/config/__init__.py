"""Configuration loading for prompts and schemas."""

from lisa.config.prompts import get_prompts, load_prompts
from lisa.config.schemas import get_schemas, load_schemas

__all__ = ["load_prompts", "get_prompts", "load_schemas", "get_schemas"]
