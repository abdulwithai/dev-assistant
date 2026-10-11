"""Platform registry. Adapters are imported lazily so one broken adapter can't block the others."""
import importlib
from typing import Type

from autopost.platforms.base import Platform

REGISTRY = {
    "youtube": "autopost.platforms.youtube:YouTube",
    "instagram": "autopost.platforms.instagram:Instagram",
    "linkedin": "autopost.platforms.linkedin:LinkedIn",
    "tiktok": "autopost.platforms.tiktok:TikTok",
}


def get_platform_class(name: str) -> Type[Platform]:
    module_name, cls_name = REGISTRY[name].split(":")
    return getattr(importlib.import_module(module_name), cls_name)
