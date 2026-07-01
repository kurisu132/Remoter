#!/bin/bash
# OrangePi 上执行一次，为 VLink 创建桌面启动图标和开机自启配置。
# 用法：bash scripts/install_desktop.sh
set -e

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
UV_BIN="$HOME/.local/bin/uv"

if [ ! -f "$UV_BIN" ]; then
    echo "警告: uv 未在 $UV_BIN 找到，请确认 uv 已安装"
    echo "      安装命令: curl -LsSf https://astral.sh/uv/install.sh | sh"
    exit 1
fi

DESKTOP_CONTENT="[Desktop Entry]
Type=Application
Name=VLink 监控
Name[zh_CN]=VLink 监控
Comment=RTSP Camera Monitor with PTZ Control
Exec=$UV_BIN run --project $PROJECT_DIR python -m gui.main_window
WorkingDirectory=$PROJECT_DIR
Icon=camera-web
Terminal=false
Categories=Video;Monitor;
StartupNotify=false"

# 安装到应用菜单
mkdir -p "$HOME/.local/share/applications"
printf '%s\n' "$DESKTOP_CONTENT" > "$HOME/.local/share/applications/vlink.desktop"
chmod +x "$HOME/.local/share/applications/vlink.desktop"
echo "✓ 应用菜单图标已安装: ~/.local/share/applications/vlink.desktop"

# 安装到桌面（若 ~/Desktop 存在）
if [ -d "$HOME/Desktop" ]; then
    cp "$HOME/.local/share/applications/vlink.desktop" "$HOME/Desktop/vlink.desktop"
    chmod +x "$HOME/Desktop/vlink.desktop"
    echo "✓ 桌面快捷方式已创建: ~/Desktop/vlink.desktop"
fi

# 开机自启（XDG autostart，登录桌面后自动启动）
mkdir -p "$HOME/.config/autostart"
cp "$HOME/.local/share/applications/vlink.desktop" "$HOME/.config/autostart/vlink.desktop"
echo "✓ 开机自启已配置: ~/.config/autostart/vlink.desktop"

echo ""
echo "安装完成。重新登录后即可在应用菜单或桌面启动 VLink 监控。"
echo "取消自启: rm ~/.config/autostart/vlink.desktop"
