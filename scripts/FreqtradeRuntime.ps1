function Assert-ValidTimerange {
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
