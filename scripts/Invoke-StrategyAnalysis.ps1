[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [ValidatePattern("^\d{8}-\d{8}$")]
    [string]$Timerange,

    [ValidateSet("VibeRsiStrategy", "KoreanStarterStrategy", "MultiTimeframeAtrStrategy")]
    [string[]]$Strategies = @(
        "VibeRsiStrategy",
        "KoreanStarterStrategy",
        "MultiTimeframeAtrStrategy"
    ),

    [string]$Pair = "BTC/USDT",

    [ValidateRange(1, 10000)]
    [int]$MinimumTradeAmount = 20,

    [ValidateRange(1, 10000)]
    [int]$TargetedTradeAmount = 100,

    [ValidateRange(2, 4999)]
    [int[]]$StartupCandles = @(49, 99, 199, 399, 799, 1599)
)

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $repositoryRoot
. (Join-Path $PSScriptRoot "FreqtradeRuntime.ps1")

foreach ($strategy in $Strategies) {
    Write-Host "[$strategy] recursive-analysis 실행"
    $recursiveCommonArguments = @(
        "recursive-analysis",
        "--strategy", $strategy,
        "--timerange", $Timerange,
        "--pairs", $Pair,
        "--startup-candle"
    ) + $StartupCandles

    Invoke-FreqtradeCommand `
        -DockerArguments ($recursiveCommonArguments + @(
            "--config", "/freqtrade/user_data/config/backtest.example.json",
            "--strategy-path", "/freqtrade/user_data/strategies"
        )) `
        -NativeArguments ($recursiveCommonArguments + @(
            "--config", ".\config\backtest.example.json",
            "--strategy-path", ".\strategies"
        )) `
        -FailureMessage "$strategy recursive-analysis에 실패했습니다."

    Write-Host "[$strategy] lookahead-analysis 실행"
    $lookaheadName = "lookahead-$strategy-$Timerange.csv"
    $lookaheadCommonArguments = @(
        "lookahead-analysis",
        "--strategy", $strategy,
        "--timerange", $Timerange,
        "--pairs", $Pair,
        "--minimum-trade-amount", $MinimumTradeAmount,
        "--targeted-trade-amount", $TargetedTradeAmount
    )

    Invoke-FreqtradeCommand `
        -DockerArguments ($lookaheadCommonArguments + @(
            "--config", "/freqtrade/user_data/config/backtest.example.json",
            "--config", "/freqtrade/user_data/config/lookahead.json",
            "--strategy-path", "/freqtrade/user_data/strategies",
            "--lookahead-analysis-exportfilename", "/freqtrade/user_data/backtest_results/$lookaheadName"
        )) `
        -NativeArguments ($lookaheadCommonArguments + @(
            "--config", ".\config\backtest.example.json",
            "--config", ".\config\lookahead.json",
            "--strategy-path", ".\strategies",
            "--lookahead-analysis-exportfilename", ".\user_data\backtest_results\$lookaheadName"
        )) `
        -FailureMessage "$strategy lookahead-analysis에 실패했습니다."
}
