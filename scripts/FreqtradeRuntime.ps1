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
        & docker compose run --rm freqtrade @DockerArguments
    }
    else {
        $nativeExecutable = Join-Path $repositoryRoot ".venv\Scripts\freqtrade.exe"
        if (-not (Test-Path -LiteralPath $nativeExecutable -PathType Leaf)) {
            throw "Freqtrade 실행 환경을 찾을 수 없습니다. Docker Desktop을 설치하거나 requirements-runtime.txt로 .venv를 구성하세요."
        }
        & $nativeExecutable @NativeArguments
    }

    if ($LASTEXITCODE -ne 0) {
        throw "$FailureMessage (종료 코드: $LASTEXITCODE)"
    }
}
