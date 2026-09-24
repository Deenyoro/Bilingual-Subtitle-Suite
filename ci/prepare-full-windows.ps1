# Lays out third_party\pgsrip_install\ for the FULL build, the way the
# GitHub Actions release workflow does, so build.py bundles it:
#   tessdata\{eng,chi_sim,chi_tra,jpn,kor}.traineddata
#   pgsrip\          (the PGSRip Python package)
#   pgsrip_config.json
# Run after ci\tools-windows.ps1 has been dot-sourced (it provides
# Get-VerifiedDownload and the shared download cache). Usage:
#   .\ci\prepare-full-windows.ps1 -Python .\.venv-ci\Scripts\python.exe
param([Parameter(Mandatory = $true)][string]$Python)
$ErrorActionPreference = 'Stop'

if (-not (Get-Command Get-VerifiedDownload -ErrorAction SilentlyContinue)) {
  throw "Get-VerifiedDownload is not defined: dot-source ci\tools-windows.ps1 first"
}

$Root = Split-Path -Parent $PSScriptRoot
$Install = Join-Path $Root 'third_party\pgsrip_install'
$Tessdata = Join-Path $Install 'tessdata'
New-Item -ItemType Directory -Force $Tessdata | Out-Null

# ---- tessdata -------------------------------------------------------------
# The GitHub workflow fetches these from tesseract-ocr/tessdata's main
# branch; the files there are byte-identical to the 4.1.0 tag (same size and
# blob), so pin the tag and each file's SHA-256. The files are cached in the
# runner's download cache (about 180 MB), not fetched on every build.
$TessdataRef = '4.1.0'
$TessdataSha256 = [ordered]@{
  'eng'     = 'daa0c97d651c19fba3b25e81317cd697e9908c8208090c94c3905381c23fc047'
  'chi_sim' = 'fc05d89ab31d8b4e226910f16a8bcbf78e43bae3e2580bb5feefd052efdab363'
  'chi_tra' = '559067dc0f7c94788884742129d66a0117dde7f4ff12b263d92147173497db14'
  'jpn'     = '6f416b902d129d8cc28e99c33244034b1cf52549e8560f6320b06d317852159a'
  'kor'     = '9520bfe9e3cfc38d4a808e036b0287c88a1d37fb80b9a0a23928ddccdd20595b'
}
foreach ($lang in $TessdataSha256.Keys) {
  $file = Get-VerifiedDownload "https://github.com/tesseract-ocr/tessdata/raw/$TessdataRef/$lang.traineddata" `
                               "tessdata-$TessdataRef-$lang.traineddata" $TessdataSha256[$lang]
  Copy-Item $file (Join-Path $Tessdata "$lang.traineddata") -Force
}
Get-ChildItem $Tessdata -Filter *.traineddata | ForEach-Object {
  Write-Host ("  {0,-24} {1,8:N1} MB" -f $_.Name, ($_.Length / 1MB))
}

# ---- pgsrip_config.json ---------------------------------------------------
# Same content as the GitHub workflow writes. UTF-8 without a BOM: the
# wrapper reads it with the default (ANSI) encoding on Windows.
$config = @'
{
  "installation_type": "bundled",
  "tessdata_path": "tessdata",
  "version": "ci-build"
}
'@
[IO.File]::WriteAllText((Join-Path $Install 'pgsrip_config.json'), $config + "`n", (New-Object Text.UTF8Encoding($false)))

# ---- PGSRip package -------------------------------------------------------
# The GitHub workflow pip-installs pgsrip into the build environment and
# copies the package folder; build.py bundles only that folder (as data).
# Here the pinned, hash-checked package goes into a staging folder instead,
# so the build environment matches the lite build's.
$staging = Join-Path $Root '.ci-pgsrip'
& $Python -m pip install -q --no-deps --require-hashes --target $staging -r (Join-Path $PSScriptRoot 'requirements-pgsrip.txt')
if ($LASTEXITCODE -ne 0) { throw "pip install pgsrip failed (exit $LASTEXITCODE)" }
$pkg = Join-Path $staging 'pgsrip'
if (-not (Test-Path (Join-Path $pkg '__init__.py'))) { throw "pgsrip package not found in $staging" }
$dst = Join-Path $Install 'pgsrip'
New-Item -ItemType Directory -Force $dst | Out-Null
Copy-Item (Join-Path $pkg '*') $dst -Recurse -Force
Write-Host "PGSRip package copied from $pkg"
