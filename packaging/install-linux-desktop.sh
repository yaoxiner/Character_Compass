#!/usr/bin/env bash
set -euo pipefail

source_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
data_home="${XDG_DATA_HOME:-$HOME/.local/share}"
install_dir="$data_home/character-compass"
apps_dir="$data_home/applications"

if [[ "$source_dir" != "$install_dir" ]]; then
  mkdir -p "$data_home"
  stage_dir="$(mktemp -d "$data_home/.character-compass-update.XXXXXX")"
  trap 'rm -rf -- "$stage_dir"' EXIT
  cp -a "$source_dir"/. "$stage_dir"/
  if [[ -e "$install_dir" ]]; then
    previous_dir="$(mktemp -d "$data_home/character-compass.previous.XXXXXX")"
    rmdir "$previous_dir"
    mv "$install_dir" "$previous_dir"
    if ! mv "$stage_dir" "$install_dir"; then
      mv "$previous_dir" "$install_dir"
      exit 1
    fi
    printf '旧版本保留在 %s\n' "$previous_dir"
  else
    mv "$stage_dir" "$install_dir"
  fi
fi
mkdir -p "$apps_dir"
cat > "$apps_dir/character-compass.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Character Compass
Comment=长篇小说创作室
Exec="$install_dir/CharacterCompass"
Icon=$install_dir/_internal/web/assets/icon.png
Terminal=false
Categories=Office;Utility;
EOF
chmod +x "$apps_dir/character-compass.desktop"
desktop_dir="$(xdg-user-dir DESKTOP 2>/dev/null || true)"
if [[ -z "$desktop_dir" && -d "$HOME/Desktop" ]]; then
  desktop_dir="$HOME/Desktop"
fi
if [[ -n "$desktop_dir" && -d "$desktop_dir" ]]; then
  cp "$apps_dir/character-compass.desktop" "$desktop_dir/Character Compass.desktop"
  chmod +x "$desktop_dir/Character Compass.desktop"
  if command -v gio >/dev/null 2>&1; then
    gio set "$desktop_dir/Character Compass.desktop" metadata::trusted true >/dev/null 2>&1 || true
  fi
fi
printf 'Character Compass 已安装到 %s\n' "$install_dir"
printf '现在可从应用菜单或桌面图标启动。\n'
