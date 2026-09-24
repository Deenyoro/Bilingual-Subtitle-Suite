# Smoke-checks a built biss exe on the Windows runner, like the GitHub
# workflow's "Verify ... executable" steps (--version and --help must run),
# plus a size floor (catches a bundle that silently lost its data) and, for
# release builds, that the exe reports the release's version. Usage:
#   .\ci\check-exe.ps1 -Exe dist\biss.exe -MinMB 10 -Version $env:VERSION
param(
  [Parameter(Mandatory = $true)][string]$Exe,
  [Parameter(Mandatory = $true)][int]$MinMB,
  [string]$Version = ''
)
$ErrorActionPreference = 'Stop'

$item = Get-Item $Exe -ErrorAction SilentlyContinue
if (-not $item) { throw "$Exe was not produced" }
$mb = [math]::Round($item.Length / 1MB, 1)
if ($item.Length -lt ($MinMB * 1MB)) { throw "$Exe is $mb MB (< $MinMB MB); the bundle is incomplete" }
Write-Host "$Exe : $mb MB"

# stdout only: under 'Stop', PowerShell 5.1 turns redirected stderr lines into errors.
$out = & $item.FullName --version | Out-String
if ($LASTEXITCODE -ne 0) { throw "$Exe --version failed (exit $LASTEXITCODE): $out" }
Write-Host "--version: $($out.Trim())"
# Untagged 0.0.0-<sha> builds keep whatever utils/constants.py says.
if ($Version -and -not $Version.StartsWith('0.0.0-')) {
  $reported = ($out.Trim() -split '\s+')[-1]
  if ($reported -ne $Version) {
    throw "$Exe reports version '$reported' but this release is ${Version}: bump APP_VERSION in utils/constants.py"
  }
}

& $item.FullName --help | Out-Host
if ($LASTEXITCODE -ne 0) { throw "$Exe --help failed (exit $LASTEXITCODE)" }
