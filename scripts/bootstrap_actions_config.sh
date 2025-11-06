#!/usr/bin/env bash
set -euo pipefail
cd ../
# 要求：已安装 gh，并 gh auth login 过
REPO="$(gh repo view --json nameWithOwner -q .nameWithOwner 2>/dev/null || true)"
[ -z "${REPO}" ] && { echo "请在仓库根目录执行，或先 gh repo clone 再进入目录"; exit 1; }

# 导入 Variables
if [ -f actions.vars ]; then
  echo "==> 设置 Repository Variables"
  grep -v '^\s*$' actions.vars | grep -v '^\s*#' | while IFS='=' read -r k v; do
    gh variable set "$k" -b "$v" --repo "$REPO"
  done
else
  echo "actions.vars 不存在，跳过 Variables"
fi

# 导入 Secrets
if [ -f actions.secrets.env ]; then
  echo "==> 设置 Repository Secrets"
  grep -v '^\s*$' actions.secrets.env | grep -v '^\s*#' | while IFS='=' read -r k v; do
    gh secret set "$k" -b "$v" --repo "$REPO"
  done
else
  echo "actions.secrets.env 不存在，跳过 Secrets"
fi

echo "==> 当前 Variables："
gh variable list --repo "$REPO" || true
echo "==> 当前 Secrets："
gh secret list --repo "$REPO" || true
