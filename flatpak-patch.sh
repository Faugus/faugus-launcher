#!/bin/bash

TARGET_DIR="."

LAUNCHER_FILE="${TARGET_DIR}/faugus_launcher.py"

sed -i 's|Exec=faugus-launcher --hide|Exec=flatpak run io.github.Faugus.faugus_launcher --hide|g' "$LAUNCHER_FILE"
sed -i 's|Exec={faugus_run} "{command}"|Exec=flatpak run --command={faugus_run} io.github.Faugus.faugus_launcher "{command}"|g' "$LAUNCHER_FILE"
sed -i 's|game_info\["Exe"\] = f'"'"'"{faugus_run}"'"'"'|game_info["Exe"] = f'"'"'"flatpak-spawn"'"'"'|g' "$LAUNCHER_FILE"
sed -i 's|game_info\["LaunchOptions"\] = f'"'"'"{command}"'"'"'|game_info["LaunchOptions"] = f'"'"'--host flatpak run --command=/app/bin/faugus-run io.github.Faugus.faugus_launcher "{command}"'"'"'|g' "$LAUNCHER_FILE"
sed -i 's|"LaunchOptions": f'"'"'"{command}"'"'"',|"LaunchOptions": f'"'"'--host flatpak run --command=/app/bin/faugus-run io.github.Faugus.faugus_launcher "{command}"'"'"',|g' "$LAUNCHER_FILE"
sed -i 's|grid_miscellaneous.attach(self.checkbox_close_after_launch, 0, 6, 1, 1)|#grid_miscellaneous.attach(self.checkbox_close_after_launch, 0, 6, 1, 1)|g' "$LAUNCHER_FILE"
sed -i 's|Icon=faugus-launcher|Icon=io.github.Faugus.faugus_launcher|g' "$LAUNCHER_FILE"

for desktop_file in faugus-launcher.desktop faugus-run.desktop faugus-proton-manager.desktop faugus-shortcut.desktop; do
    FILE_PATH="${TARGET_DIR}/${desktop_file}"
    if [ -f "$FILE_PATH" ]; then
        sed -i 's|Icon=faugus-launcher|Icon=io.github.Faugus.faugus_launcher|g' "$FILE_PATH"
    fi
done

for file in faugus_launcher.py faugus_run.py faugus_proton_manager.py; do
    FILE_PATH="${TARGET_DIR}/${file}"
    if [ -f "$FILE_PATH" ]; then
        sed -i 's|faugus-launcher.png|io.github.Faugus.faugus_launcher.png|g' "$FILE_PATH"
    fi
done
