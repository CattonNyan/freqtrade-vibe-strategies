[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [ValidateSet("VibeRsiStrategy", "KoreanStarterStrategy", "MultiTimeframeAtrStrategy")]
    [string]$Strategy,

    [Parameter(Mandatory)]
    [ValidatePattern("^\d{8}-\d{8}$")]
    [string]$Timerange
)

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $repositoryRoot
. (Join-Path $PSScriptRoot "FreqtradeRuntime.ps1")

$resultName = "{0}-{1}.json" -f $Strategy, $Timerange
$commonArguments = @(
    "backtesting",
    "--strategy", $Strategy,
    "--timerange", $Timerange,
    "--cache", "none",
    "--export", "trades"
)

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
