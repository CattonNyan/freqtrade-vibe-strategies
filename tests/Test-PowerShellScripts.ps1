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

$caughtMessage = $null
try {
    & (Join-Path $repositoryRoot "scripts/Get-MarketData.ps1") -Timeframes "fast"
}
catch {
    $caughtMessage = $_.Exception.Message
}
if (-not $caughtMessage) {
    throw "A malformed timeframe was not rejected."
}

$caughtMessage = $null
try {
    Assert-MarketDataAvailable `
        -Pairs "BTC-USDT" `
        -Timeframes "5m" `
        -Exchange "binance"
}
catch {
    $caughtMessage = $_.Exception.Message
}
if (-not $caughtMessage) {
    throw "The shared market data preflight accepted a malformed pair."
}

$caughtMessage = $null
try {
    Assert-MarketDataAvailable `
        -Pairs "BTC/USDT" `
        -Timeframes "hourly" `
        -Exchange "binance"
}
catch {
    $caughtMessage = $_.Exception.Message
}
if (-not $caughtMessage) {
    throw "The shared market data preflight accepted a malformed timeframe."
}

$caughtMessage = $null
try {
    Invoke-FreqtradeCommand `
        -DockerArguments @() `
        -NativeArguments @("--version") `
        -FailureMessage "runtime failed"
}
catch {
    $caughtMessage = $_.Exception.Message
}
if (-not $caughtMessage) {
    throw "The runtime accepted an empty argument list."
}

$caughtMessage = $null
try {
    Invoke-FreqtradeCommand `
        -DockerArguments @("--version") `
        -NativeArguments @("--version") `
        -FailureMessage "runtime failed" `
        -LogPath (Join-Path ([IO.Path]::GetTempPath()) "freqtrade-$PID.log")
}
catch {
    $caughtMessage = $_.Exception.Message
}
if (-not $caughtMessage -or $caughtMessage -notmatch "user_data") {
    throw "The runtime accepted a log path outside user_data: $caughtMessage"
}

$caughtMessage = $null
try {
    Initialize-FreqtradeDirectory -RelativePath "../outside-repository"
}
catch {
    $caughtMessage = $_.Exception.Message
}
if (-not $caughtMessage -or $caughtMessage -notmatch "user_data") {
    throw "A directory outside user_data was accepted: $caughtMessage"
}

$nestedOutputDirectory = Join-Path $repositoryRoot "user_data/test-output-helper-$PID"
$nestedOutputFile = Join-Path $nestedOutputDirectory "nested/result.log"
try {
    Initialize-FreqtradeOutputFile -Path $nestedOutputFile
    if (-not (Test-Path -LiteralPath (Split-Path -Parent $nestedOutputFile))) {
        throw "The output helper did not create the parent directory."
    }
}
finally {
    if (Test-Path -LiteralPath $nestedOutputDirectory) {
        Remove-Item -LiteralPath $nestedOutputDirectory -Recurse -Force
    }
}

$emptyDataDirectory = Join-Path $repositoryRoot "user_data/data/binance"
$emptyDataFile = Join-Path $emptyDataDirectory "CODEXEMPTY_USDT-5m.feather"
try {
    [void](New-Item -ItemType Directory -Path $emptyDataDirectory -Force)
    [void](New-Item -ItemType File -Path $emptyDataFile -Force)
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
    if (Test-Path -LiteralPath $emptyDataFile) {
        Remove-Item -LiteralPath $emptyDataFile -Force
    }
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

$caughtMessage = $null
try {
    & (Join-Path $repositoryRoot "scripts/Invoke-Hyperopt.ps1") `
        -Strategy "VibeRsiStrategy" `
        -Timerange "20250101-20260101" `
        -Spaces @("all", "buy")
}
catch {
    $caughtMessage = $_.Exception.Message
}
if (-not $caughtMessage -or $caughtMessage -notmatch "all") {
    throw "Conflicting hyperopt spaces were not rejected: $caughtMessage"
}

$caughtMessage = $null
try {
    & (Join-Path $repositoryRoot "scripts/Invoke-Hyperopt.ps1") `
        -Strategy "VibeRsiStrategy" `
        -Timerange "20250101-20260101" `
        -HyperoptLoss "Invalid Loss"
}
catch {
    $caughtMessage = $_.Exception.Message
}
if (-not $caughtMessage) {
    throw "A malformed hyperopt loss class name was not rejected."
}

$guardFile = Join-Path $repositoryRoot "user_data/test-output-guard-$PID.tmp"
try {
    Set-Content -LiteralPath $guardFile -Value "existing"
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

$outsideOutput = Join-Path ([IO.Path]::GetTempPath()) "freqtrade-output-$PID.log"
$caughtMessage = $null
try {
    Initialize-FreqtradeOutputFile -Path $outsideOutput -Force
}
catch {
    $caughtMessage = $_.Exception.Message
}
if (-not $caughtMessage -or $caughtMessage -notmatch "user_data") {
    throw "An output path outside user_data was accepted: $caughtMessage"
}

$directoryOutput = Join-Path $repositoryRoot "user_data/test-directory-output-$PID"
try {
    [void](New-Item -ItemType Directory -Path $directoryOutput -Force)
    $caughtMessage = $null
    try {
        Initialize-FreqtradeOutputFile -Path $directoryOutput
    }
    catch {
        $caughtMessage = $_.Exception.Message
    }
    if (-not $caughtMessage) {
        throw "A directory was accepted as an output file: $caughtMessage"
    }
}
finally {
    if (Test-Path -LiteralPath $directoryOutput) {
        Remove-Item -LiteralPath $directoryOutput -Recurse -Force
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
    "scripts/Invoke-Checks.ps1",
    "scripts/Invoke-DryRun.ps1",
    "scripts/Invoke-Hyperopt.ps1",
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
