<#
.SYNOPSIS
    지정된 Freqtrade 전략과 기간에 대해 안전하고 재현 가능한 백테스트를 실행합니다.

.DESCRIPTION
    전략별 필수 타임프레임 데이터가 user_data/data에 존재하는지 사전에 검증하고,
    백테스트 결과를 user_data/backtest_results의 전략·페어·기간별 디렉터리에 보관합니다.
    기존 결과 디렉터리가 있을 경우 덮어쓰기를 방지하며, -Force 지정 시에만 교체합니다.

.PARAMETER Strategy
    백테스트를 수행할 전략 이름 (VibeRsiStrategy, KoreanStarterStrategy, MultiTimeframeAtrStrategy 중 선택).

.PARAMETER Timerange
    백테스트 대상 기간 (YYYYMMDD-YYYYMMDD 형식, 예: 20250101-20260101).

.PARAMETER Pairs
    백테스트 대상 거래 페어 목록 (기본값: @("BTC/USDT", "ETH/USDT")).

.PARAMETER Force
    동일한 전략·페어·기간의 이전 백테스트 결과 디렉터리를 교체하는 스위치.

.EXAMPLE
    .\scripts\Invoke-Backtest.ps1 -Strategy KoreanStarterStrategy -Timerange 20250101-20260101

.EXAMPLE
    .\scripts\Invoke-Backtest.ps1 -Strategy VibeRsiStrategy -Timerange 20250101-20260101 -Pairs @("BTC/USDT") -Force
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
$requiredTimeframes = switch ($Strategy) {
    "VibeRsiStrategy" { @("5m") }
    "KoreanStarterStrategy" { @("15m") }
    "MultiTimeframeAtrStrategy" { @("5m", "1h") }
}
Assert-MarketDataAvailable -Pairs $normalizedPairs -Timeframes $requiredTimeframes
$pairSlug = ($normalizedPairs | ForEach-Object { $_ -replace '[/:]', '-' }) -join "_"
$resultDirectoryName = "{0}-{1}-{2}" -f $Strategy, $pairSlug, $Timerange
$resultPath = Join-Path $repositoryRoot "user_data/backtest_results/$resultDirectoryName"
if (Test-Path -LiteralPath $resultPath) {
    if (-not $Force) {
        throw "백테스트 결과 디렉터리가 이미 존재합니다. 교체하려면 -Force를 지정하세요: $resultPath"
    }
    Remove-Item -LiteralPath $resultPath -Recurse -Force
}
[void](New-Item -ItemType Directory -Path $resultPath)
$resultNotes = "strategy=$Strategy; pairs=$($normalizedPairs -join ','); timerange=$Timerange"
$commonArguments = @(
    "backtesting",
    "--strategy", $Strategy,
    "--timerange", $Timerange,
    "--cache", "none",
    "--export", "trades",
    "--notes", $resultNotes,
    "--pairs"
) + $normalizedPairs

Invoke-FreqtradeCommand `
    -DockerArguments ($commonArguments + @(
        "--config", "/freqtrade/user_data/config/backtest.example.json",
        "--strategy-path", "/freqtrade/user_data/strategies",
        "--backtest-directory", "/freqtrade/user_data/backtest_results/$resultDirectoryName"
    )) `
    -NativeArguments ($commonArguments + @(
        "--config", ".\config\backtest.example.json",
        "--strategy-path", ".\strategies",
        "--backtest-directory", ".\user_data\backtest_results\$resultDirectoryName"
    )) `
    -FailureMessage "백테스트에 실패했습니다."
