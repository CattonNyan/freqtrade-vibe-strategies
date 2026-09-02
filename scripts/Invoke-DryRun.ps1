[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [ValidateSet("VibeRsiStrategy", "KoreanStarterStrategy", "MultiTimeframeAtrStrategy")]
    [string]$Strategy,

    [switch]$Start
)

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot "FreqtradeRuntime.ps1")

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

[string[]]$commonArguments = if ($Start) {
    @("trade", "--strategy", $Strategy)
}
else {
    @("show-config")
}
[string[]]$dockerStrategyArguments = if ($Start) {
    @("--strategy-path", "/freqtrade/user_data/strategies")
} else {
    @()
}
[string[]]$nativeStrategyArguments = if ($Start) {
    @("--strategy-path", ".\strategies")
} else {
    @()
}

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
