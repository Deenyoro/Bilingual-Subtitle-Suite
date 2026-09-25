# Uploads biss-full.exe straight to the project's Generic Package Registry
# (package "biss", version $env:VERSION) and writes out\links.ndjson for the
# release job, which uploads the small biss.exe itself and creates the
# GitLab Release from both links. Release runs only (v* tag or
# RELEASE_VERSION). Usage, from build-windows-full:
#
#   .\ci\publish-windows.ps1 -File out\biss-full.exe
#
# Why upload from here instead of passing a job artifact to the release job:
# biss-full.exe bundles about 77 MB of Tesseract data on top of the lite
# payload (roughly 100-110 MB in all), over GitLab's default 100 MB maximum
# job artifact size, which this instance does not raise. The instance sets
# no generic package file size limit, so the registry takes it. The upload
# goes through curl.exe (built into Windows 10 1803+), which streams the
# file; Windows PowerShell 5.1's Invoke-WebRequest -InFile would buffer it.
#
# Builds are not reproducible, so uploading a name that already exists in
# this package version would add a second file with a different SHA-256
# under the same name, and the release mirror to GitHub would then fail for
# this tag. This script therefore refuses to publish over an existing file:
# release a new patch version instead. A RELEASE_VERSION re-run works when
# nothing was uploaded yet (for example the first tag pipeline failed before
# this step).
param(
  [Parameter(Mandatory = $true)][string[]]$File
)
$ErrorActionPreference = 'Stop'

if (-not $env:VERSION) { throw "VERSION is not set" }
$tag = "v$env:VERSION"
# The test job already refuses RELEASE_VERSION runs that are not on the tag;
# re-check here because this job publishes before the release job runs.
if ($env:CI_COMMIT_TAG -ne $tag) {
  throw "Refusing to publish ${tag}: this pipeline runs on '$env:CI_COMMIT_TAG' (ref $env:CI_COMMIT_REF_NAME), not the tag $tag"
}

$curl = Join-Path $env:SystemRoot 'System32\curl.exe'
if (-not (Test-Path $curl)) { throw "curl.exe not found at $curl" }

$pkg = "$env:CI_API_V4_URL/projects/$env:CI_PROJECT_ID/packages/generic/biss/$env:VERSION"
$files = foreach ($p in $File) {
  if (-not (Test-Path $p -PathType Leaf)) { throw "$p is missing" }
  Get-Item $p
}

# HEAD on the download URL: 200 = already published, 404 = not yet. Any
# other answer is reported and the upload goes ahead.
foreach ($f in $files) {
  $global:LASTEXITCODE = 0
  $code = & $curl -sS -I -o NUL -w '%{http_code}' -H "JOB-TOKEN: $env:CI_JOB_TOKEN" "$pkg/$($f.Name)"
  if ($code -eq '200') {
    throw "$($f.Name) is already in package biss/$env:VERSION. Builds are not reproducible, so publishing it again would add a second file with a different SHA-256 under the same name (and break the GitHub release mirror if it has copied this release). Release a new patch version instead."
  } elseif ($code -ne '404') {
    Write-Warning "Could not check whether $($f.Name) is already published (HTTP '$code', curl exit $LASTEXITCODE); uploading."
  }
}

$links = foreach ($f in $files) {
  Write-Host ("uploading {0} ({1:N1} MB)" -f $f.Name, ($f.Length / 1MB))
  $global:LASTEXITCODE = 0
  & $curl -fsS --retry 3 -o NUL -H "JOB-TOKEN: $env:CI_JOB_TOKEN" --upload-file $f.FullName "$pkg/$($f.Name)"
  if ($LASTEXITCODE -ne 0) { throw "upload of $($f.Name) failed (curl exit $LASTEXITCODE)" }
  # Link the API download URL (what the release mirror accepts), not the web one.
  [pscustomobject]@{ name = $f.Name; url = "$pkg/$($f.Name)"; link_type = 'package' } | ConvertTo-Json -Compress
}
New-Item -ItemType Directory -Force out | Out-Null
$ndjson = Join-Path (Resolve-Path out).Path 'links.ndjson'
[IO.File]::WriteAllText($ndjson, (($links -join "`n") + "`n"), [Text.Encoding]::ASCII)
Get-Content $ndjson
