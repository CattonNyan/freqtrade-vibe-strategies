[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [ValidatePattern("^\d{8}-\d{8}$")]
    [string]$Timerange,

    [ValidateSet("VibeRsiStrategy", "KoreanStarterStrategy")]
    [string[]]$Strategies = @("VibeRsiStrategy", "KoreanStarterStrategy"),

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

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker를 찾을 수 없습니다. Docker Desktop을 설치하고 다시 실행하세요."
}

foreach ($strategy in $Strategies) {
    Write-Host "[$strategy] recursive-analysis 실행"
    $recursiveArguments = @(
        "compose", "run", "--rm", "freqtrade",
        "recursive-analysis",
        "--config", "/freqtrade/user_data/config/backtest.example.json",
        "--strategy", $strategy,
        "--strategy-path", "/freqtrade/user_data/strategies",
        "--timerange", $Timerange,
        "--pairs", $Pair,
        "--startup-candle"
    ) + $StartupCandles

    & docker @recursiveArguments
    if ($LASTEXITCODE -ne 0) {
        throw "$strategy recursive-analysis가 종료 코드 $LASTEXITCODE 로 실패했습니다."
    }

    Write-Host "[$strategy] lookahead-analysis 실행"
    $lookaheadResult = "/freqtrade/user_data/backtest_results/lookahead-$strategy-$Timerange.csv"
    $lookaheadArguments = @(
        "compose", "run", "--rm", "freqtrade",
        "lookahead-analysis",
        "--config", "/freqtrade/user_data/config/backtest.example.json",
        "--strategy", $strategy,
        "--strategy-path", "/freqtrade/user_data/strategies",
        "--timerange", $Timerange,
        "--pairs", $Pair,
        "--minimum-trade-amount", $MinimumTradeAmount,
        "--targeted-trade-amount", $TargetedTradeAmount,
        "--lookahead-analysis-exportfilename", $lookaheadResult
    )

    & docker @lookaheadArguments
    if ($LASTEXITCODE -ne 0) {
        throw "$strategy lookahead-analysis가 종료 코드 $LASTEXITCODE 로 실패했습니다."
    }
}
