#!/usr/bin/env bash
#
# termux-mcp 一键安装脚本（面向零基础用户）
#
# 用法（在 Termux 中）：
#   方法 A（推荐，先看内容再执行）：
#     curl -L -o install.sh https://raw.githubusercontent.com/lxy426329/Termux-MCP/main/scripts/install.sh
#     bash install.sh
#   方法 B（一行命令）：
#     curl -fsSL https://raw.githubusercontent.com/lxy426329/Termux-MCP/main/scripts/install.sh | bash
#
# 脚本是幂等的：重复运行不会破坏已有配置。
# 不会把 token 打印到日志，不会上传任何 secret。
#
set -euo pipefail

STEP="初始化"
fail() {
  echo ""
  echo "=================================================="
  echo " 安装失败于步骤: $STEP"
  echo " 错误信息: $1"
  echo "=================================================="
  echo ""
  echo "请把上面的错误信息发给维护者，或查看 README 的 Troubleshooting 章节。"
  exit 1
}

log() { echo "==> $1"; }
ok()  { echo "    OK: $1"; }

# ── 1. 检查 Termux 环境 ─────────────────────────────────────────────────────
STEP="检查 Termux 环境"
if [ -z "${PREFIX:-}" ] || [[ "$PREFIX" != /data/data/com.termux* ]]; then
  fail "看起来不是在 Termux 中运行。请在 Android 手机的 Termux 应用里运行本脚本。"
fi
ok "Termux 环境 ($PREFIX)"

# ── 2. 更新软件包列表 ───────────────────────────────────────────────────────
STEP="更新软件包列表 (pkg update)"
log "更新软件包列表..."
pkg update -y >/dev/null 2>&1 || fail "pkg update 失败，请检查网络后重试"
ok "pkg update"

# ── 3. 安装系统依赖 ─────────────────────────────────────────────────────────
STEP="安装系统依赖"
log "安装 python / git / openssh ..."
pkg install -y python git openssh >/dev/null 2>&1 || fail "pkg install 失败"
ok "python git openssh"

# ── 4. 检查 Python / pip ────────────────────────────────────────────────────
STEP="检查 Python"
command -v python >/dev/null 2>&1 || fail "python 未安装"
PY_VER="$(python --version 2>&1)"
ok "$PY_VER"
command -v pip >/dev/null 2>&1 || fail "pip 未安装"
ok "pip"

# ── 5. 安装项目（含 mcp SDK + uvicorn，由 pyproject.toml 声明）──────────────
STEP="安装项目"
if [ -f pyproject.toml ]; then
  log "在当前目录安装项目..."
  pip install . >/dev/null 2>&1 || fail "pip install . 失败"
  ok "pip install ."
else
  log "未找到项目文件，从 GitHub 克隆..."
  git clone --depth 1 https://github.com/lxy426329/Termux-MCP.git termux-mcp || fail "git clone 失败"
  cd termux-mcp
  pip install . >/dev/null 2>&1 || fail "pip install . 失败"
  ok "pip install ."
fi

# ── 6. 验证 MCP SDK（必须 >=1.28 且 <2）────────────────────────────────────
STEP="检查 MCP SDK"
MCP_VER="$(python -c 'import importlib.metadata as m; print(m.version("mcp"))' 2>/dev/null || true)"
if [ -z "$MCP_VER" ]; then
  fail "MCP SDK 未安装（pip install . 应已自动安装）"
fi
if [[ "$MCP_VER" == 2.* ]]; then
  fail "检测到 MCP SDK $MCP_VER（2.x 不兼容）。请运行: pip install 'mcp>=1.28,<2'"
fi
ok "mcp $MCP_VER"

# ── 7. 验证 uvicorn ─────────────────────────────────────────────────────────
STEP="检查 uvicorn"
UVI_VER="$(python -c 'import importlib.metadata as m; print(m.version("uvicorn"))' 2>/dev/null || true)"
if [ -z "$UVI_VER" ]; then
  fail "uvicorn 未安装（pip install . 应已自动安装）"
fi
ok "uvicorn $UVI_VER"

# ── 8. 检查可选 tunnel 依赖 ─────────────────────────────────────────────────
STEP="检查 tunnel 依赖"
if command -v ssh >/dev/null 2>&1; then
  ok "ssh（pinggy / localhost.run 可用）"
else
  echo "    WARN: ssh 未安装（可选）— 需要公网隧道时运行: pkg install openssh"
fi
if command -v cloudflared >/dev/null 2>&1; then
  ok "cloudflared（cloudflare 隧道可用）"
else
  echo "    WARN: cloudflared 未安装（可选）— 需要时运行: pkg install cloudflared"
fi

# ── 9. 创建必要目录 ─────────────────────────────────────────────────────────
STEP="创建目录"
mkdir -p ~/.config/termux-mcp
mkdir -p ~/.local/state/termux-mcp
ok "~/.config/termux-mcp  ~/.local/state/termux-mcp"

# ── 10/11. 配置 + 首次生成随机 AUTH TOKEN ──────────────────────────────────
STEP="生成配置"
CONFIG="$HOME/.config/termux-mcp/config.env"
if [ ! -f "$CONFIG" ]; then
  log "首次运行：生成随机 AUTH TOKEN ..."
  TOKEN="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
  {
    echo "# termux-mcp configuration (auto-generated)"
    echo "# 此文件包含密钥，权限已设为 600。"
    echo "TERMUX_MCP_AUTH_TOKEN=$TOKEN"
  } > "$CONFIG"
  chmod 600 "$CONFIG"
  ok "已生成 token 并保存到 $CONFIG（权限 600）"
else
  ok "配置文件已存在，跳过生成"
fi

# ── 12. 文件权限 ────────────────────────────────────────────────────────────
STEP="设置权限"
chmod 600 "$CONFIG" 2>/dev/null || true
ok "config.env 权限 600"

# ── 13. 自检 ────────────────────────────────────────────────────────────────
STEP="自检"
log "运行自检 (termux-mcp doctor) ..."
termux-mcp doctor || true

# ── 14. 成功信息 ────────────────────────────────────────────────────────────
echo ""
echo "=================================================="
echo " 安装完成！"
echo "=================================================="
echo ""
echo "接下来你要做的："
echo "  1. 启动（含公网隧道）:   termux-mcp start"
echo "     只启动本地（无隧道）: termux-mcp start --no-tunnel"
echo "  2. 查看状态:             termux-mcp status"
echo "  3. 查看日志:             termux-mcp logs"
echo "  4. 停止:                 termux-mcp stop"
echo "  5. 查看 token:           termux-mcp token --show"
echo ""
echo "把 start 输出的 MCP public URL 填进你的 MCP 客户端，"
echo "Authorization 头填: Bearer <你的 token>"
echo ""