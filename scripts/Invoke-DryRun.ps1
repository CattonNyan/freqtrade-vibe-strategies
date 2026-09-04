<#
.SYNOPSIS
    Freqtrade 전략의 가상 모의투자(Dry-run) 설정을 검증하거나 실행합니다.

.DESCRIPTION
    예제 설정 파일(config/dry-run.example.json)의 dry_run=true 여부 및 API 키/텔레그램 비활성화를 검증합니다.
    기본 실행 시에는 show-config 모드로 설정 유효성만 확인하며, -Start 스위치를 지정해야 실제 가상 거래 봇이 시작됩니다.

.PARAMETER Strategy
    모의투자를 실행할 전략 이름 (VibeRsiStrategy, KoreanStarterStrategy, MultiTimeframeAtrStrategy 중 선택).

.PARAMETER Start
    실제 모의투자(Dry-run trade) 프로세스를 시작하는 스위치. 미지정 시 설정 검증(show-config)만 수행.

.EXAMPLE
    .\scripts\Invoke-DryRun.ps1 -Strategy KoreanStarterStrategy

.EXAMPLE
    .\scripts\Invoke-DryRun.ps1 -Strategy KoreanStarterStrategy -Start
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [ValidateSet("VibeRsiStrategy", "KoreanStarterStrategy", "MultiTimeframeAtrStrategy")]
    [string]$Strategy,

    [switch]$Start
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot "FreqtradeRuntime.ps1")
Initialize-FreqtradeDirectory -RelativePath "user_data/db"

$strategyPath = Join-Path $repositoryRoot "strategies\$Strategy.py"
if (-not (Test-Path -LiteralPath $strategyPath -PathType Leaf)) {
    throw "전략 파일을 찾을 수 없습니다: $strategyPath"
}

$dryRunConfigPath = Join-Path $repositoryRoot "config\dry-run.example.json"
$dryRunConfig = Get-Content -LiteralPath $dryRunConfigPath -Raw | ConvertFrom-Json
if ($dryRunConfig.dry_run -ne $true) {
    throw "dry-run 설정에서 dry_run=true를 확인할 수 없습니다."
}
if ($dryRunConfig.exchange.key -or $dryRunConfig.exchange.secret) {
    throw "예제 dry-run 설정에 거래소 API 키를 저장하지 마세요."
}
if ($dryRunConfig.telegram.enabled -ne $false) {
    throw "예제 dry-run 설정에서 Telegram 외부 알림을 활성화하지 마세요."
}

[string[]]$commonArguments = if ($Start) {
    @("trade", "--strategy", $Strategy)
}
else {
    @("show-config", "--strategy", $Strategy)
}
[string[]]$dockerStrategyArguments = @("--strategy-path", "/freqtrade/user_data/strategies")
[string[]]$nativeStrategyArguments = @("--strategy-path", ".\strategies")

Invoke-FreqtradeCommand `
    -DockerArguments ($commonArguments + @(
        "--config", "/freqtrade/user_data/config/backtest.example.json",
        "--config", "/freqtrade/user_data/config/dry-run.example.json"
    ) + $dockerStrategyArguments) `
    -NativeArguments ($commonArguments + @(
        "--config", ".\config\backtest.example.json",
        "--config", ".\config\dry-run.example.json"
    ) + $nativeStrategyArguments) `
    -FailureMessage "dry-run 설정 검증 또는 실행에 실패했습니다."
