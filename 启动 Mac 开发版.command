#!/bin/zsh
set -e
cd -- "$(dirname -- "$0")"
if [[ ! -x .venv-mac/bin/python ]]; then
    echo "正在创建 Mac 开发环境…"
    python3 -m venv .venv-mac
fi
if ! .venv-mac/bin/python -c 'import PySide6, AppKit, Quartz, ApplicationServices' 2>/dev/null; then
    .venv-mac/bin/python -m pip install -r requirements.txt
fi
exec .venv-mac/bin/python run.py --data-dir .runtime/mac-user "$@"
