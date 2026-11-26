@echo off
setlocal
set "MUSICRECO_ROOT=%~dp0"
powershell.exe -NoProfile -Command ^
  "$ErrorActionPreference='Stop'; $root=$env:MUSICRECO_ROOT; $parts=Join-Path $root 'windows-app'; $manifest=Get-Content -LiteralPath (Join-Path $parts 'manifest.json') -Raw | ConvertFrom-Json; $exe=Join-Path $root 'MusicRecommendation.exe';" ^
  "function Digest($path) { $hash=[Security.Cryptography.SHA256]::Create(); $stream=[IO.File]::OpenRead($path); try { [BitConverter]::ToString($hash.ComputeHash($stream)).Replace('-','') } finally { $stream.Dispose(); $hash.Dispose() } };" ^
  "if (!(Test-Path -LiteralPath $exe -PathType Leaf) -or (Digest $exe) -ne $manifest.sha256) {" ^
  "  $tmp=Join-Path $root ('musicreco-'+[Guid]::NewGuid().ToString('N')+'.tmp');" ^
  "  try { $out=[IO.File]::Open($tmp,[IO.FileMode]::CreateNew); try {" ^
  "    foreach ($part in $manifest.parts) { if ($part.file -notmatch '^part-[0-9]{3}\.bin$') { throw 'Invalid app part name' }; $path=Join-Path $parts $part.file; if ((Digest $path) -ne $part.sha256) { throw ('Invalid app part: '+$part.file) }; $inputFile=[IO.File]::OpenRead($path); try { $inputFile.CopyTo($out) } finally { $inputFile.Dispose() } }" ^
  "  } finally { $out.Dispose() }; if ((Get-Item -LiteralPath $tmp).Length -ne $manifest.bytes -or (Digest $tmp) -ne $manifest.sha256) { throw 'Invalid assembled application' }; Move-Item -LiteralPath $tmp -Destination $exe -Force }" ^
  "  finally { if (Test-Path -LiteralPath $tmp) { Remove-Item -LiteralPath $tmp } }" ^
  "}; & $exe; exit $LASTEXITCODE"
if errorlevel 1 pause
