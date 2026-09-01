[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [ValidateSet("VibeRsiStrategy", "KoreanStarterStrategy")]
    [string]$Strategy,

    [Parameter(Mandatory)]
    [ValidatePattern("^\d{8}-\d{8}$")]
    [string]$Timerange
)

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $repositoryRoot

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker를 찾을 수 없습니다. Docker Desktop을 설치하고 다시 실행하세요."
}

$resultName = "{0}-{1}.json" -f $Strategy, $Timerange
$commandArguments = @(
    "compose", "run", "--rm", "freqtrade",
    "backtesting",
    "--config", "/freqtrade/user_data/config/backtest.example.json",
    "--strategy", $Strategy,
    "--strategy-path", "/freqtrade/user_data/strategies",
    "--timerange", $Timerange,
    "--cache", "none",
    "--export", "trades",
    "--export-filename", "/freqtrade/user_data/backtest_results/$resultName"
)

& docker @commandArguments
if ($LASTEXITCODE -ne 0) {
    throw "백테스트가 종료 코드 $LASTEXITCODE 로 실패했습니다."
}
