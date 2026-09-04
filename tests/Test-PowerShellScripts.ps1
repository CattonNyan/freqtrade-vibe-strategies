[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
. (Join-Path $repositoryRoot "scripts/FreqtradeRuntime.ps1")

Assert-ValidTimerange -Timerange "20250101-20260101"
$caughtMessage = $null
try {
    Assert-ValidTimerange -Timerange "20260101-20250101"
}
catch {
    $caughtMessage = $_.Exception.Message
}
if (-not $caughtMessage) {
    throw "A reversed timerange was not rejected."
}

$caughtMessage = $null
try {
    Assert-ValidTimerange -Timerange "20250101/20260101"
}
catch {
    $caughtMessage = $_.Exception.Message
}
if (-not $caughtMessage -or $caughtMessage -notmatch "YYYYMMDD-YYYYMMDD") {
    throw "A malformed timerange did not produce the expected format error: $caughtMessage"
}

$caughtMessage = $null
try {
    & (Join-Path $repositoryRoot "scripts/Get-MarketData.ps1") -Pairs "BTC-USDT"
}
catch {
    $caughtMessage = $_.Exception.Message
}
if (-not $caughtMessage) {
    throw "A malformed pair was not rejected."
}

$emptyDataDirectory = Join-Path $repositoryRoot "user_data/data/binance"
$emptyDataFile = Join-Path $emptyDataDirectory "CODEXEMPTY_USDT-5m.feather"
[void](New-Item -ItemType Directory -Path $emptyDataDirectory -Force)
[void](New-Item -ItemType File -Path $emptyDataFile -Force)
try {
    $caughtMessage = $null
    try {
        Assert-MarketDataAvailable `
            -Pairs "CODEXEMPTY/USDT" `
            -Timeframes "5m" `
            -Exchange "binance"
    }
    catch {
        $caughtMessage = $_.Exception.Message
    }
    if (-not $caughtMessage -or $caughtMessage -notmatch "CODEXEMPTY/USDT 5m") {
        throw "An empty market data file was accepted: $caughtMessage"
    }
}
finally {
    Remove-Item -LiteralPath $emptyDataFile -Force
}

$caughtMessage = $null
try {
    & (Join-Path $repositoryRoot "scripts/Invoke-StrategyAnalysis.ps1") `
        -Timerange "20250101-20260101" `
        -MinimumTradeAmount 101 `
        -TargetedTradeAmount 100
}
catch {
    $caughtMessage = $_.Exception.Message
}
if (-not $caughtMessage -or $caughtMessage -notmatch "MinimumTradeAmount") {
    throw "Invalid sample bounds were not rejected: $caughtMessage"
}

$guardFile = [IO.Path]::GetTempFileName()
try {
    $caughtMessage = $null
    try {
        Initialize-FreqtradeOutputFile -Path $guardFile
    }
    catch {
        $caughtMessage = $_.Exception.Message
    }
    if (-not $caughtMessage -or $caughtMessage -notmatch "-Force") {
        throw "An existing output file was not protected: $caughtMessage"
    }
    Initialize-FreqtradeOutputFile -Path $guardFile -Force
    if (Test-Path -LiteralPath $guardFile) {
        throw "-Force did not remove the existing output file."
    }
}
finally {
    if (Test-Path -LiteralPath $guardFile) {
        Remove-Item -LiteralPath $guardFile -Force
    }
}

$originalLocation = (Get-Location).Path
$caughtMessage = $null
try {
    & (Join-Path $repositoryRoot "scripts/Invoke-Backtest.ps1") `
        -Strategy "VibeRsiStrategy" `
        -Timerange "20260101-20250101"
}
catch {
    $caughtMessage = $_.Exception.Message
}
if (-not $caughtMessage) {
    throw "The backtest script accepted a reversed timerange."
}
if ((Get-Location).Path -ne $originalLocation) {
    throw "The caller working directory was not restored."
}

$scriptsWithHelp = @(
    "scripts/Get-MarketData.ps1",
    "scripts/Invoke-Backtest.ps1",
    "scripts/Invoke-DryRun.ps1",
    "scripts/Invoke-StrategyAnalysis.ps1",
    "scripts/FreqtradeRuntime.ps1"
)
foreach ($scriptRelative in $scriptsWithHelp) {
    $scriptFullPath = Join-Path $repositoryRoot $scriptRelative
    $content = Get-Content -LiteralPath $scriptFullPath -Raw
    if ($content -notmatch "\.SYNOPSIS") {
        throw "Script $scriptRelative is missing a .SYNOPSIS comment-based help block."
    }
}

Write-Output "PowerShell behavior tests passed."
