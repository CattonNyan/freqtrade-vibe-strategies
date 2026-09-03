<#
.SYNOPSIS
    Freqtrade Vibe Strategies 공통 실행 런타임 및 안전 가드 모듈.

.DESCRIPTION
    Docker 환경 감지, 가상환경(.venv) 실행 파일 탐색, 입력 기간 검증,
    시장 데이터 유효성 확인 및 Freqtrade 프로세스 실행 공통 헬퍼를 제공합니다.
#>

function Assert-ValidTimerange {
    <#
    .SYNOPSIS
        YYYYMMDD-YYYYMMDD 형식의 기간 문자열 유효성 및 시작일/종료일 순서를 검증합니다.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$Timerange
    )

    $parts = $Timerange -split "-", 2
    try {
        $startDate = [datetime]::ParseExact(
            $parts[0],
            "yyyyMMdd",
            [Globalization.CultureInfo]::InvariantCulture
        )
        $endDate = [datetime]::ParseExact(
            $parts[1],
            "yyyyMMdd",
            [Globalization.CultureInfo]::InvariantCulture
        )
    }
    catch {
        throw "Timerange에 유효하지 않은 날짜가 있습니다: $Timerange"
    }

    if ($startDate -ge $endDate) {
        throw "Timerange 시작일은 종료일보다 이전이어야 합니다: $Timerange"
    }
}

function Initialize-FreqtradeDirectory {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$RelativePath
    )

    $repositoryRoot = Split-Path -Parent $PSScriptRoot
    $directoryPath = Join-Path $repositoryRoot $RelativePath
    [void](New-Item -ItemType Directory -Path $directoryPath -Force)
}

function Initialize-FreqtradeOutputFile {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$Path,

        [switch]$Force
    )

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        return
    }
    if (-not $Force) {
        throw "결과 파일이 이미 존재합니다. 덮어쓰려면 -Force를 지정하세요: $Path"
    }
    Remove-Item -LiteralPath $Path -Force
}

function Assert-MarketDataAvailable {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string[]]$Pairs,

        [Parameter(Mandatory)]
        [string[]]$Timeframes
    )

    $repositoryRoot = Split-Path -Parent $PSScriptRoot
    $dataRoot = Join-Path $repositoryRoot "user_data/data"
    if (-not (Test-Path -LiteralPath $dataRoot -PathType Container)) {
        throw "시장 데이터 디렉터리가 없습니다. Get-MarketData.ps1을 먼저 실행하세요."
    }
    $missingData = @()
    foreach ($pair in ($Pairs | Sort-Object -Unique)) {
        $pairSlug = $pair -replace '[/:]', '_'
        foreach ($timeframe in ($Timeframes | Sort-Object -Unique)) {
            $pattern = "$pairSlug-$timeframe.*"
            $dataFile = Get-ChildItem -LiteralPath $dataRoot -Recurse -File -Filter $pattern |
                Select-Object -First 1
            if (-not $dataFile) {
                $missingData += "$pair $timeframe"
            }
        }
    }

    if ($missingData.Count -gt 0) {
        throw "시장 데이터가 없습니다: $($missingData -join ', '). Get-MarketData.ps1을 먼저 실행하세요."
    }
}

function Invoke-FreqtradeCommand {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string[]]$DockerArguments,

        [Parameter(Mandatory)]
        [string[]]$NativeArguments,

        [Parameter(Mandatory)]
        [string]$FailureMessage,

        [string]$LogPath
    )

    $repositoryRoot = Split-Path -Parent $PSScriptRoot
    Push-Location -LiteralPath $repositoryRoot
    try {
        $dockerReady = $false
        if (Get-Command docker -ErrorAction SilentlyContinue) {
            & docker info --format "{{.ServerVersion}}" *> $null
            $dockerEngineReady = $LASTEXITCODE -eq 0
            if ($dockerEngineReady) {
                & docker compose version *> $null
                $dockerReady = $LASTEXITCODE -eq 0
            }
        }

        if ($dockerReady) {
            $dockerArgs = @($DockerArguments)
            if ($LogPath) {
                & docker compose run --rm freqtrade @dockerArgs 2>&1 |
                    Tee-Object -FilePath $LogPath
            }
            else {
                & docker compose run --rm freqtrade @dockerArgs
            }
        }
        else {
            $nativeCandidates = @(
                (Join-Path $repositoryRoot ".venv/Scripts/freqtrade.exe"),
                (Join-Path $repositoryRoot ".venv/bin/freqtrade")
            )
            $nativeExecutable = $nativeCandidates |
                Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } |
                Select-Object -First 1
            if (-not $nativeExecutable) {
                throw "Freqtrade 실행 환경을 찾을 수 없습니다. Docker 엔진을 시작하거나 requirements-runtime.txt로 .venv를 구성하세요."
            }
            $nativeArgs = @($NativeArguments)
            if ($LogPath) {
                & $nativeExecutable @nativeArgs 2>&1 | Tee-Object -FilePath $LogPath
            }
            else {
                & $nativeExecutable @nativeArgs
            }
        }
        $exitCode = $LASTEXITCODE
    }
    finally {
        Pop-Location
    }

    if ($exitCode -ne 0) {
        throw "$FailureMessage (종료 코드: $exitCode)"
    }
}
