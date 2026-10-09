"""Compatibility shim - the real wrapper lives in
instagram_mcp_server/instagram_client.py (the installed package).
"""

from instagram_mcp_server.instagram_client import InstagramClientWrapper, logger  # noqa: F401

__all__ = ["InstagramClientWrapper", "logger"]
