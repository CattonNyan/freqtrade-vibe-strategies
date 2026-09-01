[CmdletBinding()]
param(
    [ValidateRange(30, 3650)]
    [int]$Days = 365,

    [string[]]$Pairs = @("BTC/USDT", "ETH/USDT")
)

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $repositoryRoot

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker를 찾을 수 없습니다. Docker Desktop을 설치하고 다시 실행하세요."
}

$commandArguments = @(
    "compose", "run", "--rm", "freqtrade",
    "download-data",
    "--config", "/freqtrade/user_data/config/backtest.example.json",
    "--days", $Days,
    "--timeframes", "5m", "15m",
    "--pairs"
) + $Pairs

& docker @commandArguments
if ($LASTEXITCODE -ne 0) {
    throw "시장 데이터 다운로드가 종료 코드 $LASTEXITCODE 로 실패했습니다."
}
