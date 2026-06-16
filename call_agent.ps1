# call_agent.ps1 — Goi Report Generate Agent dang chay tren GreenNode AgentBase.
#
# Cach chay (mo PowerShell trong thu muc repo):
#   powershell -ExecutionPolicy Bypass -File .\call_agent.ps1
#   powershell -ExecutionPolicy Bypass -File .\call_agent.ps1 -Message "report for July 2026"
#
# Mac dinh tao report thang 6/2026. Goi /invocations mat ~2 phut (chay full pipeline + LLM).

param(
    [string]$Message = "lam report thang 6 nam 2026"
)

$ErrorActionPreference = "Stop"
$url = "https://endpoint-9423e96a-a3b5-4940-84f0-110b8aff6299.agentbase-runtime.aiplatform.vngcloud.vn"

Write-Host ">>> Health check ..." -ForegroundColor Cyan
try {
    Invoke-RestMethod -Uri "$url/health" -TimeoutSec 30 | ConvertTo-Json
} catch {
    Write-Host "Health FAILED: $_" -ForegroundColor Red
}

Write-Host ""
Write-Host ">>> Goi tao report: '$Message'  (doi ~2 phut, dang chay pipeline + LLM) ..." -ForegroundColor Cyan
$body  = (@{ message = $Message } | ConvertTo-Json -Compress)
$bytes = [Text.Encoding]::UTF8.GetBytes($body)   # ep UTF-8 de an toan voi moi input
try {
    $res = Invoke-RestMethod -Uri "$url/invocations" -Method Post `
            -ContentType "application/json" -Body $bytes -TimeoutSec 300
    Write-Host ""
    Write-Host "=== KET QUA ===" -ForegroundColor Green
    $res | ConvertTo-Json -Depth 6
} catch {
    Write-Host "LOI khi goi agent: $_" -ForegroundColor Red
}
