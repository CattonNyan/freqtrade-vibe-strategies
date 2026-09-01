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

function Invoke-FreqtradeCommand {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string[]]$DockerArguments,

        [Parameter(Mandatory)]
        [string[]]$NativeArguments,

        [Parameter(Mandatory)]
        [string]$FailureMessage
    )

    $repositoryRoot = Split-Path -Parent $PSScriptRoot
    if (Get-Command docker -ErrorAction SilentlyContinue) {
        $dockerArgs = @($DockerArguments)
        & docker compose run --rm freqtrade @dockerArgs
    }
    else {
        $nativeExecutable = Join-Path $repositoryRoot ".venv\Scripts\freqtrade.exe"
        if (-not (Test-Path -LiteralPath $nativeExecutable -PathType Leaf)) {
            throw "Freqtrade 실행 환경을 찾을 수 없습니다. Docker Desktop을 설치하거나 requirements-runtime.txt로 .venv를 구성하세요."
        }
        $nativeArgs = @($NativeArguments)
        & $nativeExecutable @nativeArgs
    }

    if ($LASTEXITCODE -ne 0) {
        throw "$FailureMessage (종료 코드: $LASTEXITCODE)"
    }
}
