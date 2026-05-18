"""Unit tests for the additional Confluence FastMCP tools."""

import json
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastmcp import Client, FastMCP
from fastmcp.client import FastMCPTransport
from starlette.requests import Request

from src.mcp_atlassian.confluence import ConfluenceFetcher
from src.mcp_atlassian.confluence.config import ConfluenceConfig
from src.mcp_atlassian.models.confluence.page import ConfluencePage
from src.mcp_atlassian.servers.context import MainAppContext
from src.mcp_atlassian.servers.main import AtlassianMCP
from src.mcp_atlassian.utils.oauth import OAuthConfig

logger = logging.getLogger(__name__)


@pytest.fixture
def mock_confluence_fetcher():
    """Create a mocked ConfluenceFetcher with ancestors configured."""
    mock_fetcher = MagicMock(spec=ConfluenceFetcher)

    mock_parent = MagicMock(spec=ConfluencePage)
    mock_parent.to_simplified_dict.return_value = {
        "id": "111",
        "title": "Parent Page",
        "url": "https://example.atlassian.net/wiki/spaces/TEST/pages/111/Parent+Page",
    }
    mock_grandparent = MagicMock(spec=ConfluencePage)
    mock_grandparent.to_simplified_dict.return_value = {
        "id": "100",
        "title": "Space Root",
        "url": "https://example.atlassian.net/wiki/spaces/TEST/pages/100/Space+Root",
    }
    # Atlassian REST API returns ancestors ordered space-root -> immediate parent
    mock_fetcher.get_page_ancestors.return_value = [mock_grandparent, mock_parent]

    mock_config = MagicMock()
    mock_config.url = "https://mock.atlassian.net/wiki"
    mock_fetcher.config = mock_config
    return mock_fetcher


@pytest.fixture
def mock_base_confluence_config():
    """Create a mock base ConfluenceConfig for MainAppContext."""
    mock_oauth_config = OAuthConfig(
        client_id="server_client_id",
        client_secret="server_client_secret",
        redirect_uri="http://localhost",
        scope="read:confluence",
        cloud_id="mock_cloud_id",
    )
    return ConfluenceConfig(
        url="https://mock.atlassian.net/wiki",
        auth_type="oauth",
        oauth_config=mock_oauth_config,
    )


@pytest.fixture
def test_confluence_mcp(mock_confluence_fetcher, mock_base_confluence_config):
    """Create a test FastMCP instance with just the get_page_ancestors tool."""
    from src.mcp_atlassian.servers.confluence_extras import get_page_ancestors

    @asynccontextmanager
    async def test_lifespan(app: FastMCP) -> AsyncGenerator[MainAppContext, None]:
        try:
            yield MainAppContext(
                full_confluence_config=mock_base_confluence_config, read_only=False
            )
        finally:
            pass

    test_mcp = AtlassianMCP(
        "TestConfluenceExtras",
        instructions="Test Confluence Extras MCP Server",
        lifespan=test_lifespan,
    )

    confluence_sub_mcp = FastMCP(name="TestConfluenceExtrasSubMCP")
    confluence_sub_mcp.add_tool(get_page_ancestors)

    test_mcp.mount(confluence_sub_mcp, prefix="confluence")
    return test_mcp


@pytest.fixture
async def client(test_confluence_mcp, mock_confluence_fetcher):
    """Create a FastMCP client with a mocked Confluence fetcher."""
    with (
        patch(
            "src.mcp_atlassian.servers.confluence_extras.get_confluence_fetcher",
            AsyncMock(return_value=mock_confluence_fetcher),
        ),
        patch(
            "src.mcp_atlassian.servers.dependencies.get_http_request",
            MagicMock(spec=Request, state=MagicMock()),
        ),
    ):
        client_instance = Client(transport=FastMCPTransport(test_confluence_mcp))
        async with client_instance as connected_client:
            yield connected_client


@pytest.mark.anyio
async def test_get_page_ancestors_returns_full_chain(client, mock_confluence_fetcher):
    """Tool returns the ancestor chain with immediate parent as last element."""
    response = await client.call_tool(
        "confluence_get_page_ancestors", {"page_id": "999"}
    )

    mock_confluence_fetcher.get_page_ancestors.assert_called_once_with("999")

    result = json.loads(response.content[0].text)
    assert result["page_id"] == "999"
    assert result["count"] == 2
    assert result["parent_id"] == "111"  # last element of ancestors is immediate parent
    assert [a["id"] for a in result["ancestors"]] == ["100", "111"]
    assert result["ancestors"][-1]["title"] == "Parent Page"


@pytest.mark.anyio
async def test_get_page_ancestors_empty_for_space_root(client, mock_confluence_fetcher):
    """When a page is at the space root, parent_id is null and ancestors is empty."""
    mock_confluence_fetcher.get_page_ancestors.return_value = []

    response = await client.call_tool(
        "confluence_get_page_ancestors", {"page_id": "root-page"}
    )

    result = json.loads(response.content[0].text)
    assert result["page_id"] == "root-page"
    assert result["count"] == 0
    assert result["parent_id"] is None
    assert result["ancestors"] == []


@pytest.mark.anyio
async def test_get_page_ancestors_handles_numeric_page_id(
    client, mock_confluence_fetcher
):
    """Numeric page_id should be coerced to string by BeforeValidator."""
    response = await client.call_tool(
        "confluence_get_page_ancestors", {"page_id": 12345}
    )

    mock_confluence_fetcher.get_page_ancestors.assert_called_once_with("12345")
    result = json.loads(response.content[0].text)
    assert result["page_id"] == "12345"


@pytest.mark.anyio
async def test_get_page_ancestors_reports_errors(client, mock_confluence_fetcher):
    """When the underlying fetcher raises, the tool returns an ``error`` field."""
    mock_confluence_fetcher.get_page_ancestors.side_effect = RuntimeError("boom")

    response = await client.call_tool(
        "confluence_get_page_ancestors", {"page_id": "999"}
    )

    result = json.loads(response.content[0].text)
    assert "error" in result
    assert "boom" in result["error"]
