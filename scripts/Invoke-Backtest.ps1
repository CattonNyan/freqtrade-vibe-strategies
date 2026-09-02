[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [ValidateSet("VibeRsiStrategy", "KoreanStarterStrategy", "MultiTimeframeAtrStrategy")]
    [string]$Strategy,

    [Parameter(Mandatory)]
    [ValidatePattern("^\d{8}-\d{8}$")]
    [string]$Timerange,

    [ValidateNotNullOrEmpty()]
    [ValidatePattern("^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+(?::[A-Za-z0-9._-]+)?$")]
    [string[]]$Pairs = @("BTC/USDT", "ETH/USDT"),

    [switch]$Force
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot "FreqtradeRuntime.ps1")
Assert-ValidTimerange -Timerange $Timerange
Initialize-FreqtradeDirectory -RelativePath "user_data/backtest_results"

$strategyPath = Join-Path $repositoryRoot "strategies\$Strategy.py"
if (-not (Test-Path -LiteralPath $strategyPath -PathType Leaf)) {
    throw "전략 파일을 찾을 수 없습니다: $strategyPath"
}

$normalizedPairs = @($Pairs | Sort-Object -Unique)
$pairSlug = ($normalizedPairs | ForEach-Object { $_ -replace '[/:]', '-' }) -join "_"
$resultName = "{0}-{1}-{2}.json" -f $Strategy, $pairSlug, $Timerange
$resultPath = Join-Path $repositoryRoot "user_data/backtest_results/$resultName"
Initialize-FreqtradeOutputFile -Path $resultPath -Force:$Force
$commonArguments = @(
    "backtesting",
    "--strategy", $Strategy,
    "--timerange", $Timerange,
    "--cache", "none",
    "--export", "trades",
    "--pairs"
) + $normalizedPairs

Invoke-FreqtradeCommand `
    -DockerArguments ($commonArguments + @(
        "--config", "/freqtrade/user_data/config/backtest.example.json",
        "--strategy-path", "/freqtrade/user_data/strategies",
        "--export-filename", "/freqtrade/user_data/backtest_results/$resultName"
    )) `
    -NativeArguments ($commonArguments + @(
        "--config", ".\config\backtest.example.json",
        "--strategy-path", ".\strategies",
        "--export-filename", ".\user_data\backtest_results\$resultName"
    )) `
    -FailureMessage "백테스트에 실패했습니다."
