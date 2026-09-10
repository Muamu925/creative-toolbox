$ErrorActionPreference = 'Stop'
$taskRoot = $PSScriptRoot
$taskPython = Join-Path $taskRoot '.venv\Scripts\pythonw.exe'
if (-not (Test-Path -LiteralPath $taskPython)) {
    throw '请先按 README 创建虚拟环境并安装依赖。'
}
Start-Process -FilePath $taskPython -ArgumentList @('run.py', '--data-dir', '.runtime\user') -WorkingDirectory $taskRoot -WindowStyle Hidden
