"""Tools Sage can choose to use: search, literature, providers, goals, Age Well and more.

Each tool is a small class with a typed input model. See tools/base.py and tools/README.md.
"""

from engine.settings import Settings
from tools.base import ToolRegistry


def build_registry(settings: Settings) -> ToolRegistry:
    """Every tool Sage can use, in one place. Add a line here when a tool is ready, e.g.

        registry.register(LiteratureSearch())

    A tool whose key isn't configured can be skipped here so Sage never offers it.
    """
    registry = ToolRegistry()
    return registry
