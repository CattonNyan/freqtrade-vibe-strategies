<#
.SYNOPSIS
    Freqtrade 전략 백테스트에 필요한 과거 시장 데이터를 거래소로부터 다운로드합니다.

.DESCRIPTION
    지정된 일수(Days) 동안의 5m, 15m, 1h 캔들 데이터를 자동으로 내려받아 user_data/data 디렉터리에 저장합니다.
    Docker 또는 로컬 가상환경(.venv)의 Freqtrade 런타임을 자동으로 감지하여 실행합니다.

.PARAMETER Days
    다운로드할 과거 데이터 기간 (일 단위, 기본값: 365, 최소: 30, 최대: 3650).

.PARAMETER Pairs
    다운로드할 거래 페어 목록 (기본값: @("BTC/USDT", "ETH/USDT")).

.EXAMPLE
    .\scripts\Get-MarketData.ps1 -Days 180

.EXAMPLE
    .\scripts\Get-MarketData.ps1 -Days 365 -Pairs @("BTC/USDT", "ETH/USDT", "SOL/USDT")
#>
[CmdletBinding()]
param(
    [ValidateRange(30, 3650)]
    [int]$Days = 365,

    [ValidateNotNullOrEmpty()]
    [ValidatePattern("^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+(?::[A-Za-z0-9._-]+)?$")]
    [string[]]$Pairs = @("BTC/USDT", "ETH/USDT"),

    [ValidateNotNullOrEmpty()]
    [string[]]$Timeframes = @("5m", "15m", "1h")
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot "FreqtradeRuntime.ps1")
Initialize-FreqtradeDirectory -RelativePath "user_data/data"
$normalizedPairs = @($Pairs | Sort-Object -Unique)
$normalizedTimeframes = @($Timeframes | Sort-Object -Unique)

$commonArguments = @(
    "download-data",
    "--days", $Days,
    "--timeframes"
) + $normalizedTimeframes + @(
    "--pairs"
) + $normalizedPairs

Write-Host "[*] 시장 데이터 다운로드 시작 (기간: ${Days}일, 대상: $($normalizedPairs -join ', '))"

Invoke-FreqtradeCommand `
    -DockerArguments ($commonArguments + @("--config", "/freqtrade/user_data/config/backtest.example.json")) `
    -NativeArguments ($commonArguments + @("--config", ".\config\backtest.example.json")) `
    -FailureMessage "시장 데이터 다운로드에 실패했습니다."

Write-Host "[+] 시장 데이터 다운로드가 완료되었습니다. (저장 위치: user_data/data)"
