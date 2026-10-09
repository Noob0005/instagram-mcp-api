# Copies the current MCP package into vercel-api\_vendor so the Vercel function
# can import it. Run this after any change to ..\instagram_mcp_server\ and
# before deploying to Vercel.
$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot          # repo root
$src  = Join-Path $root "instagram_mcp_server"
$dst  = Join-Path $PSScriptRoot "_vendor\instagram_mcp_server"

if (-not (Test-Path $src)) { throw "package not found: $src" }
if (Test-Path $dst) { Remove-Item $dst -Recurse -Force }
New-Item -ItemType Directory -Path $dst -Force | Out-Null
Copy-Item (Join-Path $src "*.py") $dst -Force
if (Test-Path (Join-Path $src "py.typed")) { Copy-Item (Join-Path $src "py.typed") $dst -Force }

Write-Host "vendored package -> $dst"
Get-ChildItem $dst | Select-Object -ExpandProperty Name
