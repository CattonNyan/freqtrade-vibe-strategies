<#
.SYNOPSIS
    저장소의 빠른 정적 검사와 PowerShell 동작 테스트를 한 번에 실행합니다.

.DESCRIPTION
    전략 소스 unittest, 전체 PowerShell 스크립트 구문 검사, 공통 런타임 동작 테스트를
    순서대로 실행하며 하나라도 실패하면 0이 아닌 종료 상태로 중단합니다.

.EXAMPLE
    .\scripts\Invoke-Checks.ps1
#>
[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot

$pythonCandidates = @(
    (Join-Path $repositoryRoot ".venv/Scripts/python.exe"),
    (Join-Path $repositoryRoot ".venv/bin/python")
)
$pythonExecutable = $pythonCandidates |
    Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } |
    Select-Object -First 1
if (-not $pythonExecutable) {
    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if ($pythonCommand) {
        $pythonExecutable = $pythonCommand.Source
    }
}
if (-not $pythonExecutable) {
    throw "Python 실행 파일을 찾을 수 없습니다. Python 또는 .venv를 먼저 구성하세요."
}

Push-Location -LiteralPath $repositoryRoot
try {
    & $pythonExecutable -B -m unittest discover -s tests -v
    if ($LASTEXITCODE -ne 0) {
        throw "Python 전략 소스 검사에 실패했습니다. (종료 코드: $LASTEXITCODE)"
    }

    $parseErrors = @()
    Get-ChildItem -LiteralPath (Join-Path $repositoryRoot "scripts") -Filter *.ps1 |
        ForEach-Object {
            $tokens = $null
            $errors = $null
            [void][System.Management.Automation.Language.Parser]::ParseFile(
                $_.FullName,
                [ref]$tokens,
                [ref]$errors
            )
            $parseErrors += $errors
        }
    if ($parseErrors.Count -gt 0) {
        $parseErrors | Format-List
        throw "PowerShell 구문 검사에 실패했습니다."
    }

    & (Join-Path $repositoryRoot "tests/Test-PowerShellScripts.ps1")
    if ($LASTEXITCODE -ne 0) {
        throw "PowerShell 동작 테스트에 실패했습니다. (종료 코드: $LASTEXITCODE)"
    }
}
finally {
    Pop-Location
}

Write-Output "All repository checks passed."
