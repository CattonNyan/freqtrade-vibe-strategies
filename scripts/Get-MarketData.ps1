[CmdletBinding()]
param(
    [ValidateRange(30, 3650)]
    [int]$Days = 365,

    [ValidateNotNullOrEmpty()]
    [ValidatePattern("^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+(?::[A-Za-z0-9._-]+)?$")]
    [string[]]$Pairs = @("BTC/USDT", "ETH/USDT")
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot "FreqtradeRuntime.ps1")
Initialize-FreqtradeDirectory -RelativePath "user_data/data"

$commonArguments = @(
    "download-data",
    "--days", $Days,
    "--timeframes", "5m", "15m", "1h",
    "--pairs"
) + $Pairs

Invoke-FreqtradeCommand `
    -DockerArguments ($commonArguments + @("--config", "/freqtrade/user_data/config/backtest.example.json")) `
    -NativeArguments ($commonArguments + @("--config", ".\config\backtest.example.json")) `
    -FailureMessage "시장 데이터 다운로드에 실패했습니다."
