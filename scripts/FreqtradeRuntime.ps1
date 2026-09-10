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

    if ($Timerange -notmatch "^\d{8}-\d{8}$") {
        throw "Timerange 형식은 YYYYMMDD-YYYYMMDD여야 합니다: $Timerange"
    }

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

function Get-PairSlug {
    <#
    .SYNOPSIS
        거래 페어 목록을 안전한 파일명/디렉터리명 문자열(Slug)로 변환합니다.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string[]]$Pairs
    )

    $normalized = @($Pairs | Sort-Object -Unique)
    if ($normalized.Count -gt 3) {
        return "{0}_{1}_and_{2}_more" -f ($normalized[0] -replace '[/:]', '-'), ($normalized[1] -replace '[/:]', '-'), ($normalized.Count - 2)
    }
    return ($normalized | ForEach-Object { $_ -replace '[/:]', '-' }) -join "_"
}

function Initialize-FreqtradeDirectory {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$RelativePath
    )

    $repositoryRoot = Split-Path -Parent $PSScriptRoot
    if ([IO.Path]::IsPathRooted($RelativePath)) {
        throw "생성 경로는 저장소 기준 상대 경로여야 합니다: $RelativePath"
    }
    $directoryPath = [IO.Path]::GetFullPath((Join-Path $repositoryRoot $RelativePath))
    $userDataRoot = [IO.Path]::GetFullPath((Join-Path $repositoryRoot "user_data"))
    $userDataPrefix = $userDataRoot.TrimEnd([IO.Path]::DirectorySeparatorChar) +
        [IO.Path]::DirectorySeparatorChar
    if (-not ($directoryPath.Equals($userDataRoot, [StringComparison]::OrdinalIgnoreCase) -or
        $directoryPath.StartsWith($userDataPrefix, [StringComparison]::OrdinalIgnoreCase))) {
        throw "생성 경로는 user_data 디렉터리 안에 있어야 합니다: $RelativePath"
    }
    [void](New-Item -ItemType Directory -Path $directoryPath -Force)
}

function Initialize-FreqtradeOutputFile {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$Path,

        [switch]$Force
    )

    $repositoryRoot = Split-Path -Parent $PSScriptRoot
    $resolvedPath = [IO.Path]::GetFullPath($Path)
    $userDataRoot = [IO.Path]::GetFullPath((Join-Path $repositoryRoot "user_data"))
    $userDataPrefix = $userDataRoot.TrimEnd([IO.Path]::DirectorySeparatorChar) +
        [IO.Path]::DirectorySeparatorChar
    if (-not $resolvedPath.StartsWith(
        $userDataPrefix,
        [StringComparison]::OrdinalIgnoreCase
    )) {
        throw "결과 파일 경로는 user_data 디렉터리 안에 있어야 합니다: $Path"
    }

    $parentDirectory = Split-Path -Parent $resolvedPath
    if ($parentDirectory -and -not (Test-Path -LiteralPath $parentDirectory)) {
        [void](New-Item -ItemType Directory -Path $parentDirectory -Force)
    }
    if (Test-Path -LiteralPath $resolvedPath -PathType Container) {
        throw "결과 파일 경로가 디렉터리를 가리킵니다: $Path"
    }
    if (-not (Test-Path -LiteralPath $resolvedPath -PathType Leaf)) {
        return
    }
    if (-not $Force) {
        throw "결과 파일이 이미 존재합니다. 덮어쓰려면 -Force를 지정하세요: $Path"
    }
    Remove-Item -LiteralPath $resolvedPath -Force
}

function Assert-MarketDataAvailable {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [ValidateNotNullOrEmpty()]
        [ValidatePattern("^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+(?::[A-Za-z0-9._-]+)?$")]
        [string[]]$Pairs,

        [Parameter(Mandatory)]
        [ValidateNotNullOrEmpty()]
        [ValidatePattern("^\d+[mhdwM]$")]
        [string[]]$Timeframes,

        [Parameter(Mandatory)]
        [ValidatePattern("^[A-Za-z0-9._-]+$")]
        [string]$Exchange
    )

    $repositoryRoot = Split-Path -Parent $PSScriptRoot
    $dataRoot = Join-Path $repositoryRoot "user_data/data/$Exchange"
    if (-not (Test-Path -LiteralPath $dataRoot -PathType Container)) {
        throw "시장 데이터 디렉터리가 없습니다. Get-MarketData.ps1을 먼저 실행하세요."
    }
    $supportedExtensions = @(".feather", ".json", ".gz", ".h5", ".parquet")
    $missingData = @()
    foreach ($pair in ($Pairs | Sort-Object -Unique)) {
        $pairSlug = $pair -replace '[/ :.@$+]', '_'
        foreach ($timeframe in ($Timeframes | Sort-Object -Unique)) {
            $pattern = "$pairSlug-$timeframe.*"
            $dataFile = Get-ChildItem -LiteralPath $dataRoot -Recurse -File -Filter $pattern |
                Where-Object { $_.Length -gt 0 } |
                Where-Object { $supportedExtensions -contains $_.Extension } |
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

function Test-DockerRuntimeAvailable {
    [CmdletBinding()]
    param()

    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        return $false
    }

    # Docker writes connection failures to stderr. Under the entry scripts'
    # Stop preference, PowerShell 5.1 turns that probe into a terminating error
    # before the native .venv fallback can run, so silence only these probes.
    $previousErrorActionPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "SilentlyContinue"
        & docker info --format "{{.ServerVersion}}" *> $null
        if ($LASTEXITCODE -ne 0) {
            return $false
        }
        & docker compose version *> $null
        return $LASTEXITCODE -eq 0
    }
    finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }
}

function Invoke-FreqtradeCommand {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [ValidateNotNull()]
        [string[]]$DockerArguments,

        [Parameter(Mandatory)]
        [ValidateNotNull()]
        [string[]]$NativeArguments,

        [Parameter(Mandatory)]
        [string]$FailureMessage,

        [string]$LogPath
    )

    if ($DockerArguments.Count -eq 0 -or $NativeArguments.Count -eq 0) {
        throw "Freqtrade 실행 인수는 비어 있을 수 없습니다."
    }
    if ([string]::IsNullOrWhiteSpace($FailureMessage)) {
        throw "실패 메시지는 비어 있을 수 없습니다."
    }

    $repositoryRoot = Split-Path -Parent $PSScriptRoot
    if ($LogPath) {
        $resolvedLogPath = [IO.Path]::GetFullPath($LogPath)
        $userDataRoot = [IO.Path]::GetFullPath((Join-Path $repositoryRoot "user_data"))
        $userDataPrefix = $userDataRoot.TrimEnd([IO.Path]::DirectorySeparatorChar) +
            [IO.Path]::DirectorySeparatorChar
        if (-not $resolvedLogPath.StartsWith(
            $userDataPrefix,
            [StringComparison]::OrdinalIgnoreCase
        )) {
            throw "로그 파일 경로는 user_data 디렉터리 안에 있어야 합니다: $LogPath"
        }
        $parentDirectory = Split-Path -Parent $resolvedLogPath
        if ($parentDirectory -and -not (Test-Path -LiteralPath $parentDirectory)) {
            [void](New-Item -ItemType Directory -Path $parentDirectory -Force)
        }
        $LogPath = $resolvedLogPath
    }
    Push-Location -LiteralPath $repositoryRoot
    try {
        $dockerReady = Test-DockerRuntimeAvailable

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
        if ($LogPath -and (Test-Path -LiteralPath $LogPath -PathType Leaf)) {
            $recentLines = Get-Content -LiteralPath $LogPath -Tail 15 -ErrorAction SilentlyContinue
            if ($recentLines) {
                Write-Warning ("최근 로그 요약 ({0}):" -f $LogPath)
                $recentLines | ForEach-Object { Write-Warning "  $_" }
            }
        }
        throw "$FailureMessage (종료 코드: $exitCode)"
    }
}
