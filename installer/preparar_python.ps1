# Arma la carpeta build/python: Python "embeddable" para Windows con todas las dependencias del bot ya instaladas.
# Lo usa el flujo de GitHub Actions antes de compilar el instalador.
$ErrorActionPreference = "Stop"
$ver = "3.12.10"
$raiz = Split-Path -Parent $PSScriptRoot
$build = Join-Path $raiz "build"
$dst = Join-Path $build "python"
New-Item -ItemType Directory -Force -Path $build | Out-Null
if (Test-Path $dst) { Remove-Item -Recurse -Force $dst }

$zip = Join-Path $build "python-embed.zip"
Invoke-WebRequest "https://www.python.org/ftp/python/$ver/python-$ver-embed-amd64.zip" -OutFile $zip
Expand-Archive $zip -DestinationPath $dst

# Habilita site-packages y agrega la carpeta de la app (la de arriba de python) a la ruta de módulos
$pth = Get-ChildItem $dst -Filter "python*._pth" | Select-Object -First 1
$base = [System.IO.Path]::GetFileNameWithoutExtension($pth.Name)
Set-Content -Encoding ascii $pth.FullName "$base.zip`r`n.`r`n..`r`nimport site`r`n"

$getpip = Join-Path $build "get-pip.py"
Invoke-WebRequest "https://bootstrap.pypa.io/get-pip.py" -OutFile $getpip
& "$dst\python.exe" $getpip --no-warn-script-location
if ($LASTEXITCODE -ne 0) { throw "get-pip falló" }
& "$dst\python.exe" -m pip install --no-warn-script-location --disable-pip-version-check -r (Join-Path $raiz "requirements.txt")
if ($LASTEXITCODE -ne 0) { throw "pip install falló" }
& "$dst\python.exe" -c "import PySide6.QtWidgets, ccxt, cryptography; print('dependencias OK')"
if ($LASTEXITCODE -ne 0) { throw "faltan dependencias" }

# Limpieza: cachés y archivos que no hacen falta para correr
Get-ChildItem $dst -Recurse -Directory -Filter "__pycache__" | Remove-Item -Recurse -Force
Remove-Item $zip, $getpip
