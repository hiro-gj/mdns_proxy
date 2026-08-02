#!/bin/bash

# mDNS-Proxy-Ubuntu-Uninstaller.sh
# mDNS Proxyの自動アンインストールスクリプト (Ubuntu向け)

set -e

# 変数定義
INSTALL_DIR="/opt/mdns_proxy"
SERVICE_FILE="/etc/systemd/system/mdns_proxy.service"
SERVICE_NAME="mdns_proxy.service"

echo "=== mDNS Proxy Uninstaller ==="

# サービスが稼働しているか、または有効化されているかを確認し、停止・無効化
echo "[1/3] systemd サービスの停止と無効化..."
if systemctl is-active --quiet "$SERVICE_NAME"; then
    echo "サービス $SERVICE_NAME を停止しています..."
    sudo systemctl stop "$SERVICE_NAME"
fi

if systemctl is-enabled --quiet "$SERVICE_NAME" 2>/dev/null; then
    echo "サービス $SERVICE_NAME を無効化しています..."
    sudo systemctl disable "$SERVICE_NAME"
fi

# systemd サービスファイルの削除
if [ -f "$SERVICE_FILE" ]; then
    echo "サービスファイルを削除しています: $SERVICE_FILE"
    sudo rm -f "$SERVICE_FILE"
fi

# systemd デーモンのリロード
echo "[2/3] systemd デーモンのリロード..."
sudo systemctl daemon-reload
sudo systemctl reset-failed

# インストールディレクトリの削除 (データベース、設定ファイル、ログもすべて削除されます)
echo "[3/3] インストールディレクトリ（データベース、設定、ログを含む）の削除..."
if [ -d "$INSTALL_DIR" ]; then
    echo "ディレクトリおよび格納されているDB/設定/ログファイルを完全に削除しています: $INSTALL_DIR"
    sudo rm -rf "$INSTALL_DIR"
fi

# /etc/mdns.allow の削除および /etc/nsswitch.conf の復元
MDNS_ALLOW="/etc/mdns.allow"
if [ -f "$MDNS_ALLOW" ]; then
    echo "/etc/mdns.allow を削除しています..."
    sudo rm -f "$MDNS_ALLOW"
fi

NSSWITCH="/etc/nsswitch.conf"
if [ -f "$NSSWITCH" ]; then
    if grep -q "mdns4 " "$NSSWITCH" || grep -q "mdns4$" "$NSSWITCH"; then
        echo "$NSSWITCH の hosts 設定を mdns4_minimal [NOTFOUND=return] へ復元しています..."
        sudo sed -i 's/mdns4/mdns4_minimal \[NOTFOUND=return\]/g' "$NSSWITCH"
    fi
fi

echo "=== アンインストール完了 ==="
echo "mDNS Proxy は正常に削除されました。"