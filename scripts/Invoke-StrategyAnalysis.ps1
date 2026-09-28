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

.PARAMETER AdvancedQuantMetrics
    Freqtrade 백테스트 JSON 결과가 있는 경우 궤양지수(Ulcer Index), 마틴 비율, 트레이드 기대값 등 심층 퀀트 위험 분석 리포트를 함께 생성합니다.

.PARAMETER QuantJson
    Freqtrade 백테스트 JSON 결과가 있는 경우 궤양지수(Ulcer Index), 손익비, 페어별 성과를 담은 정형 JSON 리포트(quant-analysis.json)를 자동 생성합니다.

.PARAMETER QuantCsv
    Freqtrade 백테스트 JSON 결과가 있는 경우 전략별 퀀트 지표(MDD, 궤양지수, 버크 비율, 스털링 비율 등)를 담은 CSV 리포트(quant-analysis.csv)를 자동 생성합니다.

.PARAMETER QuantHtml
    Freqtrade 백테스트 JSON 결과가 있는 경우 전략별 퀀트 지표, 청산 사유, 페어별 성과를 담은 시각화 HTML 리포트(quant-analysis.html)를 자동 생성합니다.

.PARAMETER QuantSortBy
    퀀트 분석 시 청산 태그 및 페어별 분석 테이블 정렬 기준 (trades, profit, win_rate, pf 중 선택).

.PARAMETER QuantMinTrades
    퀀트 분석 시 청산 태그 및 페어별 분석 테이블에 포함할 최소 거래수 필터 (기본값: 1, 최소: 1, 최대: 10000).

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

    [switch]$Force,

    [switch]$AdvancedQuantMetrics,

    [switch]$QuantJson,

    [switch]$QuantCsv,

    [switch]$QuantHtml,

    [ValidateSet("trades", "profit", "win_rate", "pf")]
    [string]$QuantSortBy,

    [ValidateRange(1, 10000)]
    [int]$QuantMinTrades = 1
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
$normalizedStrategies = @($Strategies | Select-Object -Unique)
$pairSlug = $Pair -replace '[/:]', '-'
$requiredTimeframes = foreach ($strategy in $normalizedStrategies) {
    switch ($strategy) {
        "VibeRsiStrategy" { "5m" }
        "KoreanStarterStrategy" { "15m" }
        "MultiTimeframeAtrStrategy" { "5m"; "1h" }
    }
}
$backtestConfigPath = Join-Path $repositoryRoot "config/backtest.example.json"
$exchangeName = (Get-Content -LiteralPath $backtestConfigPath -Raw | ConvertFrom-Json).exchange.name
Assert-MarketDataAvailable `
    -Pairs @($Pair) `
    -Timeframes $requiredTimeframes `
    -Exchange $exchangeName

foreach ($strategy in $normalizedStrategies) {
    $lookaheadName = "lookahead-$strategy-$pairSlug-$Timerange.csv"
    $lookaheadPath = Join-Path $repositoryRoot "user_data/backtest_results/$lookaheadName"
    Initialize-FreqtradeOutputFile -Path $lookaheadPath -Force:$Force
    foreach ($analysisType in ("recursive", "lookahead")) {
        $logName = "$analysisType-$strategy-$pairSlug-$Timerange.log"
        $logPath = Join-Path $repositoryRoot "user_data/backtest_results/$logName"
        Initialize-FreqtradeOutputFile -Path $logPath -Force:$Force
    }
}

foreach ($strategy in $normalizedStrategies) {
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

if ($AdvancedQuantMetrics -or $QuantJson -or $QuantCsv -or $QuantHtml) {
    Write-Host "[*] 퀀트 심층 하방 리스크 분석(Ulcer Index & Expectancy) 리포트 생성 중..."
    $analyzerScript = Join-Path $PSScriptRoot "analyze_backtest_results.py"
    $resultsDir = Join-Path $repositoryRoot "user_data/backtest_results"
    $latestJson = Get-ChildItem -Path $resultsDir -Filter "*.json" -File -Recurse -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if ($null -ne $latestJson) {
        $pythonExe = if (Test-Path "$repositoryRoot/.venv/Scripts/python.exe") { "$repositoryRoot/.venv/Scripts/python.exe" } else { "python" }
        $analyzerArgs = @($analyzerScript, $latestJson.FullName)
        $reportPath = Join-Path $resultsDir "quant-analysis-$Timerange.md"
        $quantJsonPath = Join-Path $resultsDir "quant-analysis-$Timerange.json"
        $quantCsvPath = Join-Path $resultsDir "quant-analysis-$Timerange.csv"
        $quantHtmlPath = Join-Path $resultsDir "quant-analysis-$Timerange.html"

        if ($AdvancedQuantMetrics) {
            $analyzerArgs += @("-o", $reportPath)
        }
        if ($QuantJson) {
            $analyzerArgs += @("-j", $quantJsonPath)
        }
        if ($QuantCsv) {
            $analyzerArgs += @("-c", $quantCsvPath)
        }
        if ($QuantHtml) {
            $analyzerArgs += @("-H", $quantHtmlPath)
        }
        if ($QuantSortBy) {
            $analyzerArgs += @("--sort-by", $QuantSortBy)
        }
        if ($QuantMinTrades -gt 1) {
            $analyzerArgs += @("--min-trades", [string]$QuantMinTrades)
        }

        & $pythonExe @analyzerArgs
        if ($AdvancedQuantMetrics) {
            Write-Host "[+] 퀀트 심층 리포트 저장 완료: $reportPath"
        }
        if ($QuantJson) {
            Write-Host "[+] 퀀트 JSON 저장 완료: $quantJsonPath"
        }
        if ($QuantCsv) {
            Write-Host "[+] 퀀트 CSV 저장 완료: $quantCsvPath"
        }
        if ($QuantHtml) {
            Write-Host "[+] 퀀트 HTML 저장 완료: $quantHtmlPath"
        }
    } else {
        Write-Host "[!] 백테스트 JSON 결과 파일이 없어 퀀트 분석 생략 (먼저 Invoke-Backtest.ps1 실행 권장)"
    }
}

Write-Host "[+] 모든 전략의 recursive 및 lookahead 분석이 완료되었습니다."
Write-Host "[*] 결과 파일 위치: user_data/backtest_results/ (세부 통과 기준은 docs/VALIDATION.md 참조)"
