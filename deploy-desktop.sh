#!/bin/bash

KIO_DIR="$HOME/.local/share/kio/servicemenus"
mkdir -p "$KIO_DIR"
if [ -f "plug.desktop" ]; then
    cp "plug.desktop" "$KIO_DIR/"
    chmod +x "$KIO_DIR/plug.desktop"
    echo "[+] Файл plug.desktop установлен в $KIO_DIR"
else
    echo "[!] Файл plug.desktop не найден в текущей папке"
fi
