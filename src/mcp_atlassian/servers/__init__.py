"""MCP Atlassian Servers Package."""

# Import ``confluence`` first so the ``confluence_mcp`` FastMCP instance
# is initialised, then import ``confluence_extras`` so the additional
# tools register themselves on that instance before ``main`` mounts it.
from . import confluence as _confluence  # noqa: F401
from . import confluence_extras as _confluence_extras  # noqa: F401
from .main import main_mcp

__all__ = ["main_mcp"]
