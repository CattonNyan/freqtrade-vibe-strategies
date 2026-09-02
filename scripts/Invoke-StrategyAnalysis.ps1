<#
.SYNOPSIS
    Freqtrade 전략의 재귀 지표 안정성(recursive-analysis) 및 미래 참조 편향(lookahead-analysis)을 심층 검증합니다.

.DESCRIPTION
    지정된 기간(Timerange) 동안 각 전략에 대해:
    1. recursive-analysis: 초기 캔들 개수(startup_candle_count)에 따른 지표 안정성 검증
    2. lookahead-analysis: 미래 봉 데이터 참조(Lookahead bias) 여부 검증
    결과는 user_data/backtest_results에 CSV 및 로그 형태로 저장됩니다.

.PARAMETER Timerange
    분석 대상 기간 (YYYYMMDD-YYYYMMDD 형식, 예: 20250101-20260101). 최소 5,000봉 이상 권장.

.PARAMETER Strategies
    분석 대상 전략 목록 (기본값: 전체 3종 전략).

.PARAMETER Pair
    분석 대상 거래 페어 (기본값: "BTC/USDT").

.PARAMETER MinimumTradeAmount
    Lookahead 분석에 필요한 최소 거래 횟수 (기본값: 20).

.PARAMETER TargetedTradeAmount
    Lookahead 분석의 목표 거래 횟수 (기본값: 100).

.PARAMETER StartupCandles
    재귀 지표 안정성 테스트용 캔들 수 목록 (기본값: 49, 99, 199, 399, 799, 1599).

.PARAMETER Force
    동일한 이름의 이전 분석 로그 및 CSV 결과 파일 덮어쓰기 허용 스위치.

.EXAMPLE
    .\scripts\Invoke-StrategyAnalysis.ps1 -Timerange 20250101-20260101

.EXAMPLE
    .\scripts\Invoke-StrategyAnalysis.ps1 -Timerange 20250101-20260101 -Strategies @("KoreanStarterStrategy") -Force
#>
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

    [ValidateNotNullOrEmpty()]
    [ValidatePattern("^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+(?::[A-Za-z0-9._-]+)?$")]
    [string]$Pair = "BTC/USDT",

    [ValidateRange(1, 10000)]
    [int]$MinimumTradeAmount = 20,

    [ValidateRange(1, 10000)]
    [int]$TargetedTradeAmount = 100,

    [ValidateRange(2, 4999)]
    [int[]]$StartupCandles = @(49, 99, 199, 399, 799, 1599),

    [switch]$Force
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot "FreqtradeRuntime.ps1")
Assert-ValidTimerange -Timerange $Timerange
Initialize-FreqtradeDirectory -RelativePath "user_data/backtest_results"
if ($MinimumTradeAmount -gt $TargetedTradeAmount) {
    throw "MinimumTradeAmount는 TargetedTradeAmount보다 클 수 없습니다."
}
$normalizedStartupCandles = @($StartupCandles | Sort-Object -Unique)
$pairSlug = $Pair -replace '[/:]', '-'
$requiredTimeframes = foreach ($strategy in $Strategies) {
    switch ($strategy) {
        "VibeRsiStrategy" { "5m" }
        "KoreanStarterStrategy" { "15m" }
        "MultiTimeframeAtrStrategy" { "5m"; "1h" }
    }
}
Assert-MarketDataAvailable -Pairs @($Pair) -Timeframes $requiredTimeframes

foreach ($strategy in $Strategies) {
    $lookaheadName = "lookahead-$strategy-$pairSlug-$Timerange.csv"
    $lookaheadPath = Join-Path $repositoryRoot "user_data/backtest_results/$lookaheadName"
    Initialize-FreqtradeOutputFile -Path $lookaheadPath -Force:$Force
    foreach ($analysisType in ("recursive", "lookahead")) {
        $logName = "$analysisType-$strategy-$pairSlug-$Timerange.log"
        $logPath = Join-Path $repositoryRoot "user_data/backtest_results/$logName"
        Initialize-FreqtradeOutputFile -Path $logPath -Force:$Force
    }
}

foreach ($strategy in $Strategies) {
    $strategyPath = Join-Path $repositoryRoot "strategies\$strategy.py"
    if (-not (Test-Path -LiteralPath $strategyPath -PathType Leaf)) {
        throw "전략 파일을 찾을 수 없습니다: $strategyPath"
    }

    Write-Host "[$strategy] recursive-analysis 실행"
    $recursiveLogName = "recursive-$strategy-$pairSlug-$Timerange.log"
    $recursiveLogPath = Join-Path $repositoryRoot "user_data/backtest_results/$recursiveLogName"
    $recursiveCommonArguments = @(
        "recursive-analysis",
        "--strategy", $strategy,
        "--timerange", $Timerange,
        "--pairs", $Pair,
        "--startup-candle"
    ) + $normalizedStartupCandles

    Invoke-FreqtradeCommand `
        -DockerArguments ($recursiveCommonArguments + @(
            "--config", "/freqtrade/user_data/config/backtest.example.json",
            "--strategy-path", "/freqtrade/user_data/strategies"
        )) `
        -NativeArguments ($recursiveCommonArguments + @(
            "--config", ".\config\backtest.example.json",
            "--strategy-path", ".\strategies"
        )) `
        -FailureMessage "$strategy recursive-analysis에 실패했습니다." `
        -LogPath $recursiveLogPath

    Write-Host "[$strategy] lookahead-analysis 실행"
    $lookaheadName = "lookahead-$strategy-$pairSlug-$Timerange.csv"
    $lookaheadLogName = "lookahead-$strategy-$pairSlug-$Timerange.log"
    $lookaheadLogPath = Join-Path $repositoryRoot "user_data/backtest_results/$lookaheadLogName"
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
        -FailureMessage "$strategy lookahead-analysis에 실패했습니다." `
        -LogPath $lookaheadLogPath
}
