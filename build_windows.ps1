[CmdletBinding()]
param([switch]$Clean,[switch]$OneDir)
$ErrorActionPreference='Stop'
$Root=Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root
$Python=Get-Command python -ErrorAction SilentlyContinue
if($Python){$Py='python';$PyArgs=@()}else{$Py='py';$PyArgs=@('-3')}
Write-Host "Using Python: $(& $Py @PyArgs --version)" -ForegroundColor Cyan
if($Clean){Remove-Item -Recurse -Force (Join-Path $Root 'build\pyinstaller'),(Join-Path $Root 'dist') -ErrorAction SilentlyContinue}
& $Py @PyArgs -m pip install --upgrade pip --index-url https://pypi.org/simple --extra-index-url https://pypi.tuna.tsinghua.edu.cn/simple
& $Py @PyArgs -m pip install -r requirements.txt --index-url https://pypi.org/simple --extra-index-url https://pypi.tuna.tsinghua.edu.cn/simple
if($LASTEXITCODE -ne 0){throw 'Dependency installation failed.'}
& $Py @PyArgs -m pytest -q
if($LASTEXITCODE -ne 0){throw 'Tests failed. Packaging was stopped.'}
$Mode=if($OneDir){'--onedir'}else{'--onefile'}
$BuildArgs=@('-m','PyInstaller','--noconfirm','--clean',$Mode,'--windowed','--name','OrganizePro','--workpath',(Join-Path $Root 'build\pyinstaller'),'--distpath',(Join-Path $Root 'dist'),'--add-data',((Join-Path $Root 'assets')+';assets'),'--add-data',((Join-Path $Root 'app\web\frontend')+';app\web\frontend'),'--hidden-import','watchdog.observers.winapi','--hidden-import','pystray._win32','--hidden-import','PIL.Image','main.py')
& $Py @PyArgs @BuildArgs
if($LASTEXITCODE -ne 0){throw 'PyInstaller failed.'}
$Exe=Join-Path $Root 'dist\OrganizePro.exe'
if(-not $OneDir -and -not (Test-Path $Exe)){throw "Expected executable was not created: $Exe"}
Write-Host "Build complete: $Exe" -ForegroundColor Green
