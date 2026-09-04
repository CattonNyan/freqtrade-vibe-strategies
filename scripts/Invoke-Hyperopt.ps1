<#
.SYNOPSIS
    Freqtrade 전략의 하이퍼옵트(Hyperopt) 파라미터 최적화를 자동화합니다.

.DESCRIPTION
    전략별 필수 타임프레임 데이터 유효성을 사전에 검증하고, 지정된 탐색 공간(Spaces),
    손실 함수(Loss function), 에포크 수에 따라 하이퍼옵트를 실행합니다.
    실행 로그는 user_data/hyperopt_results 디렉터리에 보관됩니다.

.PARAMETER Strategy
    최적화를 수행할 전략 이름 (VibeRsiStrategy, KoreanStarterStrategy, MultiTimeframeAtrStrategy 중 선택).

.PARAMETER Timerange
    최적화 대상 기간 (YYYYMMDD-YYYYMMDD 형식, 예: 20250101-20260101).

.PARAMETER Pairs
    최적화 대상 거래 페어 목록 (기본값: @("BTC/USDT", "ETH/USDT")).

.PARAMETER Epochs
    하이퍼옵트 탐색 에포크 횟수 (기본값: 100, 최소: 1, 최대: 100000).

.PARAMETER Spaces
    최적화할 파라미터 공간 (기본값: @("buy", "sell"), 선택: all, buy, sell, roi, stoploss, trailing).

.PARAMETER HyperoptLoss
    하이퍼옵트 손실 평가 함수 클래스명 (기본값: "ShortTradeDurHyperOptLoss").

.PARAMETER Force
    동일한 이름의 이전 하이퍼옵트 로그 파일 덮어쓰기 허용 스위치.

.EXAMPLE
    .\scripts\Invoke-Hyperopt.ps1 -Strategy VibeRsiStrategy -Timerange 20250101-20260101

.EXAMPLE
    .\scripts\Invoke-Hyperopt.ps1 -Strategy KoreanStarterStrategy -Timerange 20250101-20260101 -Epochs 200 -Spaces @("buy", "sell", "roi") -Force
#>
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

    [ValidateRange(1, 100000)]
    [int]$Epochs = 100,

    [ValidateSet("all", "buy", "sell", "roi", "stoploss", "trailing")]
    [string[]]$Spaces = @("buy", "sell"),

    [ValidateNotNullOrEmpty()]
    [string]$HyperoptLoss = "ShortTradeDurHyperOptLoss",

    [switch]$Force
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot "FreqtradeRuntime.ps1")
Assert-ValidTimerange -Timerange $Timerange
Initialize-FreqtradeDirectory -RelativePath "user_data/hyperopt_results"

$strategyPath = Join-Path $repositoryRoot "strategies\$Strategy.py"
if (-not (Test-Path -LiteralPath $strategyPath -PathType Leaf)) {
    throw "전략 파일을 찾을 수 없습니다: $strategyPath"
}

$normalizedPairs = @($Pairs | Sort-Object -Unique)
$normalizedSpaces = @($Spaces | Sort-Object -Unique)
$requiredTimeframes = switch ($Strategy) {
    "VibeRsiStrategy" { @("5m") }
    "KoreanStarterStrategy" { @("15m") }
    "MultiTimeframeAtrStrategy" { @("5m", "1h") }
}

$backtestConfigPath = Join-Path $repositoryRoot "config/backtest.example.json"
$exchangeName = (Get-Content -LiteralPath $backtestConfigPath -Raw | ConvertFrom-Json).exchange.name
Assert-MarketDataAvailable `
    -Pairs $normalizedPairs `
    -Timeframes $requiredTimeframes `
    -Exchange $exchangeName

$pairSlug = if ($normalizedPairs.Count -gt 3) {
    "{0}_{1}_and_{2}_more" -f ($normalizedPairs[0] -replace '[/:]', '-'), ($normalizedPairs[1] -replace '[/:]', '-'), ($normalizedPairs.Count - 2)
}
else {
    ($normalizedPairs | ForEach-Object { $_ -replace '[/:]', '-' }) -join "_"
}

$logName = "hyperopt-$Strategy-$pairSlug-$Timerange.log"
$logPath = Join-Path $repositoryRoot "user_data/hyperopt_results/$logName"
Initialize-FreqtradeOutputFile -Path $logPath -Force:$Force

$commonArguments = @(
    "hyperopt",
    "--strategy", $Strategy,
    "--timerange", $Timerange,
    "--epochs", $Epochs,
    "--hyperopt-loss", $HyperoptLoss,
    "--spaces"
) + $normalizedSpaces + @(
    "--pairs"
) + $normalizedPairs

Write-Host "[*] [$Strategy] 하이퍼옵트 최적화 시작 (기간: $Timerange, 에포크: $Epochs, 공간: $($normalizedSpaces -join ','))"

Invoke-FreqtradeCommand `
    -DockerArguments ($commonArguments + @(
        "--config", "/freqtrade/user_data/config/backtest.example.json",
        "--strategy-path", "/freqtrade/user_data/strategies"
    )) `
    -NativeArguments ($commonArguments + @(
        "--config", ".\config\backtest.example.json",
        "--strategy-path", ".\strategies"
    )) `
    -FailureMessage "$Strategy 하이퍼옵트 최적화에 실패했습니다." `
    -LogPath $logPath

Write-Host "[+] [$Strategy] 하이퍼옵트 완료. (로그: user_data/hyperopt_results/$logName)"
