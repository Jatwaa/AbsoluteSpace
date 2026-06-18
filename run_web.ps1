# AbsoluteSpace — start the multiplayer web stack (backend + frontend).
# Usage:  ./run_web.ps1      (from the repo root)
# Opens two terminals: FastAPI game server (:8000) and Vite dev server (:5173).

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot

Write-Host "Starting AbsoluteSpace web stack..." -ForegroundColor Cyan

# Backend — FastAPI game server
Start-Process pwsh -ArgumentList @(
    "-NoExit", "-Command",
    "cd '$root'; Write-Host 'BACKEND :8000' -ForegroundColor Green; python -m backend.run"
)

# Frontend — Vite dev server (proxies /api and /ws to :8000)
Start-Process pwsh -ArgumentList @(
    "-NoExit", "-Command",
    "cd '$root/frontend'; Write-Host 'FRONTEND :5173' -ForegroundColor Green; npm run dev"
)

Start-Sleep -Seconds 5
Write-Host "`nOpen http://localhost:5173 in your browser." -ForegroundColor Yellow
Write-Host "Open it in multiple windows/tabs to test multiplayer chat + shared game state." -ForegroundColor Yellow
