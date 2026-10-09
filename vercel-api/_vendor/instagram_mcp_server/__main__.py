"""
Entry point for running the Instagram MCP server as a CLI command.

Usage:
  instagram-mcp                                # stdio (default; Claude Desktop etc.)
  instagram-mcp --transport http               # Streamable HTTP on 127.0.0.1:8000/mcp
  instagram-mcp --transport sse                # legacy SSE on 127.0.0.1:8000/sse
  instagram-mcp --transport http --host 0.0.0.0 --port 8765 --path /ig/mcp

See SETUP_SSE_HTTP.md for client configuration and security notes.
"""
import argparse
import os
import sys


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(
        prog="instagram-mcp",
        description="Instagram Control MCP server — serves stdio by default, or Streamable HTTP / SSE.",
    )
    parser.add_argument(
        "--transport", choices=["stdio", "http", "streamable-http", "sse"], default="stdio",
        help="Transport to serve (default: stdio). Use 'http' for Streamable HTTP, 'sse' for legacy SSE.",
    )
    parser.add_argument("--host", default=None, help="Bind host for http/sse (default 127.0.0.1).")
    parser.add_argument("--port", type=int, default=None, help="Bind port for http/sse (default 8000).")
    parser.add_argument("--path", default=None, help="URL path for http/sse (default /mcp or /sse).")
    return parser.parse_args(argv)


def main():
    args = _parse_args()

    # Ensure the package directory is in sys.path when called as CLI
    pkg_dir = os.path.dirname(os.path.abspath(__file__))
    if pkg_dir not in sys.path:
        sys.path.insert(0, pkg_dir)

    from instagram_mcp_server.mcp_server import mcp

    if args.transport == "stdio":
        mcp.run()
        return

    kwargs = {}
    if args.host:
        kwargs["host"] = args.host
    if args.port:
        kwargs["port"] = args.port
    if args.path:
        kwargs["path"] = args.path
    endpoint = args.path or ("/sse" if args.transport == "sse" else "/mcp")
    print(f"[instagram-mcp] serving {args.transport} on "
          f"http://{args.host or '127.0.0.1'}:{args.port or 8000}{endpoint}", file=sys.stderr)
    mcp.run(transport=args.transport, **kwargs)


if __name__ == "__main__":
    main()
