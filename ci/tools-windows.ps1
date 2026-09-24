# Toolchain bootstrap for the Windows GitLab runner (shell executor).
# Dot-source from before_script. Installs, once per machine, into the
# runner's per-machine tools directory (no admin, no winget needed):
#   - CPython 3.11 (NuGet package) + Tcl/Tk from python.org's tcltk.msi
# and puts it on PATH for the job. Later jobs find it already present.
# Every download is pinned and SHA-256 checked; a download that fails the
# check is moved aside to <name>.bad-<timestamp> (never deleted) and fetched
# once more. No other existing file in the tools dir is modified, moved or
# removed; other projects' python-<ver> / python-<ver>-tk dirs are left
# alone (this one is python-3.11.9-tk).
#
# Adapted from CameraMeasurementTool's ci/tools-windows.ps1 (same tools dir,
# same download cache and Get-VerifiedDownload); this app needs no Inno
# Setup, and ci/prepare-full-windows.ps1 reuses Get-VerifiedDownload for
# the tessdata files of the full build.
$ErrorActionPreference = 'Stop'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

# Python 3.11 to match the GitHub Actions release build
# (.github/workflows/release.yml). 3.11.9 is the last 3.11 release with
# Windows binaries: both the NuGet package and python.org's tcltk.msi stop
# there (later 3.11.x are source-only security releases).
$PythonVersion      = '3.11.9'
$PythonNupkgSha256  = '9283876d58c017e0e846f95b490da3bca0fc0a6ee1134b2870677cfb7eec3c67'
$TclTkMsiSha256     = 'c8845743fb77abec0f01faa823bf3300e2113ef344758fc36360fee3dd71a8a8'

$Tools = Join-Path $env:ProgramData 'gitlab-runner-tools'
$Downloads = Join-Path $Tools 'downloads'
New-Item -ItemType Directory -Force $Tools, $Downloads | Out-Null

# Download $Url to $Downloads\$Name (reused if already there) and fail unless
# its SHA-256 matches. A cached copy that fails the check (truncated or
# corrupt) is moved aside to <name>.bad-<timestamp> (kept for inspection,
# never deleted) and downloaded once more; only a second mismatch fails.
# Returns the local path.
function Get-VerifiedDownload([string]$Url, [string]$Name, [string]$Sha256) {
  $out = Join-Path $Downloads $Name
  foreach ($attempt in 1, 2) {
    if (-not (Test-Path $out)) {
      Write-Host "Downloading $Url"
      Invoke-WebRequest $Url -OutFile "$out.part" -UseBasicParsing
      Move-Item "$out.part" $out -Force
    }
    $actual = (Get-FileHash -Algorithm SHA256 $out).Hash
    if ($actual -eq $Sha256.ToUpperInvariant()) { return $out }
    if ($attempt -eq 2) {
      throw "SHA-256 mismatch for ${Name} after a fresh download: expected $Sha256, got $actual"
    }
    $bad = "$out.bad-$(Get-Date -Format 'yyyyMMddHHmmss')"
    Move-Item $out $bad
    Write-Warning "SHA-256 mismatch for ${Name} (got $actual, expected $Sha256); moved aside to $bad (not deleted), downloading once more"
  }
}

# ---- Python + Tk ---------------------------------------------------------
# python.org's bundle installer will not run under the runner service, so
# use the NuGet package: the same CPython as a plain zip, with pip. The
# NuGet package has NO Tcl/Tk/tkinter, and this is a Tkinter app, so add Tk
# from python.org's own per-component MSI for the SAME version. `msiexec /a`
# is an administrative extract: it unpacks the files into TARGETDIR and
# installs/registers nothing. Layout of the 3.11.9 tcltk.msi (verified by
# extracting it on Linux) and where each part goes:
#   DLLs\_tkinter.pyd, tcl86t.dll, tk86t.dll            -> <python>\DLLs\
#   Lib\tkinter\                                        -> <python>\Lib\tkinter\
#   tcl\  (tcl8.6, tk8.6, tcl8, tix8.4.3, reg1.3, dde1.4) -> <python>\tcl\
# (Unlike 3.12's, this MSI has no zlib1.dll. Lib\idlelib, Lib\turtledemo,
# libs\ and the Start-menu entry are skipped.)
$python = Join-Path $Tools "python-$PythonVersion-tk"
$pythonReady = ((Test-Path (Join-Path $python 'python.exe')) -and
                (Test-Path (Join-Path $python 'DLLs\_tkinter.pyd')) -and
                (Test-Path (Join-Path $python 'Lib\tkinter\__init__.py')) -and
                (Test-Path (Join-Path $python 'tcl\tk8.6')))
if (-not $pythonReady) {
  Write-Host "Installing Python $PythonVersion with Tcl/Tk into $python"
  $pkg = Get-VerifiedDownload "https://www.nuget.org/api/v2/package/python/$PythonVersion" `
                              "python.$PythonVersion.nupkg.zip" $PythonNupkgSha256
  $nuget = Join-Path $Tools "staging\python-$PythonVersion-nuget"
  Expand-Archive $pkg -DestinationPath $nuget -Force
  New-Item -ItemType Directory -Force $python | Out-Null
  Copy-Item (Join-Path $nuget 'tools\*') $python -Recurse -Force

  $msi = Get-VerifiedDownload "https://www.python.org/ftp/python/$PythonVersion/amd64/tcltk.msi" `
                              "tcltk-$PythonVersion-amd64.msi" $TclTkMsiSha256
  $tk = Join-Path $Tools "staging\tcltk-$PythonVersion"
  New-Item -ItemType Directory -Force $tk | Out-Null
  $p = Start-Process msiexec.exe -Wait -PassThru -ArgumentList @(
    '/a', "`"$msi`"", '/qn', "TARGETDIR=`"$tk`"")
  if ($p.ExitCode -ne 0) { throw "msiexec /a tcltk.msi failed (exit $($p.ExitCode))" }
  foreach ($f in '_tkinter.pyd', 'tcl86t.dll', 'tk86t.dll') {
    $src = Join-Path $tk "DLLs\$f"
    if (-not (Test-Path $src)) { throw "tcltk.msi extract is missing DLLs\$f" }
    Copy-Item $src (Join-Path $python 'DLLs') -Force
  }
  foreach ($d in 'Lib\tkinter', 'tcl') {
    $src = Join-Path $tk $d
    if (-not (Test-Path $src)) { throw "tcltk.msi extract is missing $d" }
    $dst = Join-Path $python $d
    New-Item -ItemType Directory -Force $dst | Out-Null
    Copy-Item (Join-Path $src '*') $dst -Recurse -Force
  }
}

$env:PATH = "$python;$python\Scripts;$env:PATH"
$env:PIP_CACHE_DIR = Join-Path $Tools 'pip-cache'
$env:PIP_DISABLE_PIP_VERSION_CHECK = '1'

# Gate: this is a Tkinter app; refuse to build with a Python that lacks Tk 8.6.
$tkv = & (Join-Path $python 'python.exe') -c "import tkinter; tkinter.Tcl(); print(tkinter.TkVersion)"
if ($LASTEXITCODE -ne 0 -or "$tkv".Trim() -ne '8.6') { throw "tkinter check failed: got '$tkv' (need 8.6)" }

Write-Host ("python {0} (Tk {1})" -f (& python --version), "$tkv".Trim())
