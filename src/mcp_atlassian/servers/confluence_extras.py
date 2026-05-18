"""Additional Confluence FastMCP tool definitions.

This module extends ``servers/confluence.py`` with tools that surface
existing capabilities of :class:`PagesMixin` which were not yet exposed
through the MCP layer.

Tools defined here register themselves on the same ``confluence_mcp``
FastMCP instance via decorator. The import order in
:mod:`mcp_atlassian.servers.__init__` ensures this module is imported
before the parent ``main`` server mounts ``confluence_mcp``, so the new
tools are part of the mounted sub-MCP.
"""

import json
import logging
from typing import Annotated

from fastmcp import Context
from pydantic import BeforeValidator, Field

from mcp_atlassian.servers.confluence import confluence_mcp
from mcp_atlassian.servers.dependencies import get_confluence_fetcher

logger = logging.getLogger(__name__)


@confluence_mcp.tool(
    tags={"confluence", "read", "toolset:confluence_pages"},
    annotations={"title": "Get Page Ancestors", "readOnlyHint": True},
)
async def get_page_ancestors(
    ctx: Context,
    page_id: Annotated[
        str,
        Field(
            description=(
                "Confluence page ID (numeric ID, can be found in the page URL). "
                "Returns the full ancestor chain ordered from the space root "
                "(first element) to the immediate parent (last element)."
            ),
        ),
        BeforeValidator(lambda x: str(x)),
    ],
) -> str:
    """Get the ancestors (parent chain) of a Confluence page.

    Returns the full ancestor chain ordered from the space root (first
    element) to the immediate parent (last element). Useful for
    determining a page's location in a structured space (for example
    classifying pages by their CRBG section, auditing where a page
    lives, or reconstructing breadcrumbs).

    Args:
        ctx: The FastMCP context.
        page_id: The ID of the page whose ancestors to retrieve.

    Returns:
        JSON string with ``page_id``, ``count``, ``parent_id``
        (immediate parent, or ``null`` if the page is already at the
        space root), and the ``ancestors`` list.
    """
    confluence_fetcher = await get_confluence_fetcher(ctx)
    try:
        ancestors = confluence_fetcher.get_page_ancestors(page_id)
        ancestor_list = [page.to_simplified_dict() for page in ancestors]
        parent_id = ancestor_list[-1].get("id") if ancestor_list else None
        result = {
            "page_id": page_id,
            "count": len(ancestor_list),
            "parent_id": parent_id,
            "ancestors": ancestor_list,
        }
    except Exception as e:
        logger.error(
            f"Error getting ancestors for page ID {page_id}: {e}",
            exc_info=True,
        )
        result = {"error": f"Failed to get page ancestors: {e}"}

    return json.dumps(result, indent=2, ensure_ascii=False)
