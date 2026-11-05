<#
.SYNOPSIS
    Fixify local development launcher (Windows PowerShell 5.1+ and PowerShell 7).

.DESCRIPTION
    .\fixify.ps1              interactive menu
    .\fixify.ps1 start        start the whole local stack (with health checks)
    .\fixify.ps1 stop         stop it (database data is always kept)
    .\fixify.ps1 --help       all commands

    A thin wrapper: the launcher itself is scripts/launcher/fixify.py (standard-library Python),
    shared with fixify.sh so both platforms behave the same.
#>
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$launcher = Join-Path $root 'scripts\launcher\fixify.py'

# Prefer the API virtual environment (Python 3.12+); fall back to a system Python so that
# 'status' and '--help' still work before the virtual environment exists.
$candidates = @(
    @{ Exe = (Join-Path $root 'services\api\.venv\Scripts\python.exe'); Args = @() },
    @{ Exe = 'py'; Args = @('-3') },
    @{ Exe = 'python'; Args = @() },
    @{ Exe = 'python3'; Args = @() }
)
$python = $null
foreach ($candidate in $candidates) {
    $exe = $candidate.Exe
    if ((Test-Path $exe) -or (Get-Command $exe -ErrorAction SilentlyContinue)) {
        try {
            & $exe @($candidate.Args + @('-c', 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)')) *> $null
            if ($LASTEXITCODE -eq 0) { $python = $candidate; break }
        } catch { }
    }
}
if (-not $python) {
    Write-Host '[XX] Python 3.12+ was not found.' -ForegroundColor Red
    Write-Host '     Install it from https://www.python.org/downloads/ and create the API virtual environment:'
    Write-Host '     cd services\api; python -m venv .venv; .\.venv\Scripts\python.exe -m pip install -e ".[dev]"'
    exit 1
}

$env:FIXIFY_WRAPPER = 'ps1'
$env:PYTHONIOENCODING = 'utf-8'
# Box-drawing logo and status symbols need a UTF-8 console; this only affects this window.
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }

# 'Stop' would turn any stderr line from a child (Alembic and uvicorn log to stderr) into a
# terminating error in Windows PowerShell 5.1. The launcher reports failures itself.
$ErrorActionPreference = 'Continue'
& $python.Exe @($python.Args + @($launcher) + $args)
exit $LASTEXITCODE
