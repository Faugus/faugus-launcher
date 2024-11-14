# Faugus Launcher
A simple and lightweight app for running Windows games using [UMU-Launcher](https://github.com/Open-Wine-Components/umu-launcher)

### Support the project
<a href='https://ko-fi.com/K3K210EMDU' target='_blank'><img src=https://github.com/Faugus/faugus-launcher/blob/main/ko-fi.png width="155" height="35"/></a>&nbsp;&nbsp;
<a href='https://www.paypal.com/donate/?business=57PP9DVD3VWAN&no_recurring=0&currency_code=USD' target='_blank'><img src=https://github.com/Faugus/faugus-launcher/blob/main/paypal.png width="155" height="35"/></a>

# Installation
### Arch-based distributions (AUR)
```
yay -S --noconfirm faugus-launcher-git
```
```
# Optional tools
sudo pacman -S --noconfirm mangohud
sudo pacman -S --noconfirm gamemode
yay -S --noconfirm sc-controller
```

### Fedora-based distributions (Copr)
```
sudo dnf -y copr enable faugus/faugus-launcher
sudo dnf -y install faugus-launcher
```
```
# Optional tools
sudo dnf -y install mangohud
sudo dnf -y install gamemode
sudo dnf -y install sc-controller
```

### Debian-based distributions
```
sudo dpkg --add-architecture i386
sudo apt update
sudo apt install -y wget
mkdir -p ~/faugus-launcher
wget -P ~/faugus-launcher https://github.com/Faugus/faugus-launcher/releases/download/v1.1-12/faugus-launcher_1.1-12_amd64.deb
wget -P ~/faugus-launcher https://github.com/Faugus/faugus-launcher/releases/download/v1.1-12/python3-umu-launcher_1.1.4-1_amd64.deb
wget -P ~/faugus-launcher https://github.com/Faugus/faugus-launcher/releases/download/v1.1-12/umu-launcher_1.1.4-1_all.deb
sudo apt install -y ~/faugus-launcher/*.deb
sudo rm -r ~/faugus-launcher
```
```
# Optional tools
sudo apt -y install mangohud
sudo apt -y install gamemode
```
ATTENTION: If you get the following message when trying to run something
```
pressure-vessel-wrap[2264]: E: Child process exited with code 1: bwrap: setting up uid map: Permission denied
```
It's the AppArmor preventing umu-launcher from working properly. <a href='https://gist.github.com/Faugus/8d3caa3ce93eb1ff90409f3c3dbabe0f' target='_blank'>FIX

### Flatpak (EXPERIMENTAL)
Download <a href="https://github.com/Faugus/faugus-launcher/releases/download/v1.1-12/faugus-launcher-0.1.8.flatpak">faugus-launcher-0.1.8.flatpak</a> and run:
```
flatpak remote-add --if-not-exists flathub https://flathub.org/repo/flathub.flatpakrepo
flatpak install faugus-launcher-0.1.8.flatpak
```
```
# Optional tools
flatpak install org.freedesktop.Platform.VulkanLayer.MangoHud//23.08
```
ATTENTION: Gamescope is not working yet!

# Usage
[![YouTube](http://i.ytimg.com/vi/Ay6C2f55Pc8/hqdefault.jpg)](https://www.youtube.com/watch?v=Ay6C2f55Pc8)

# Information
### Default prefixes location
```
~/.config/faugus-launcher/prefixes/
```

### Runners location
```
~/.local/share/Steam/compatibilitytools.d/
```

### Shortcut locations
For Desktop Environments that support icons on the Desktop
```
~/Desktop/
```
For Application Launchers
```
~/.local/share/applications/
```

### Using SC Controller with Faugus Launcher
Save the SC Controller profile at
```
~/.config/faugus-launcher/controller.sccprofile
```
https://github.com/Faugus/faugus-launcher/assets/112667550/04f4f009-4b5a-4642-857f-21e3eb666074

# Screenshots
## Dark theme
### Main window
<img src=https://github.com/user-attachments/assets/46db5689-30a6-41ab-9a22-8206bfabc682/><br>
### Add/Edit game
<img src=https://github.com/user-attachments/assets/cf70c8e4-6b59-4ce6-9958-93b5b80ea244/>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;<img src=https://github.com/user-attachments/assets/69d5a53c-380f-4b57-a8b1-63313e0d7905/><br>
### Settings
<img src=https://github.com/user-attachments/assets/956c087c-68b1-4ee5-9cf8-4c6ba7ec9a26/><br>
### GE-Proton Manager
<img src=https://github.com/user-attachments/assets/4b250388-b6df-4af0-982f-9da9f06dc1af/><br>
### Create shortcut from .exe
<img src=https://github.com/user-attachments/assets/080c37b0-5ad0-4192-b4f2-f1bdd08dcb75/><br>

## Light theme
### Main window
<img src=https://github.com/user-attachments/assets/31776ca4-0d2c-4e4f-ace9-a796fa7c81b6/><br>
### Add/Edit game
<img src=https://github.com/user-attachments/assets/3f1c6328-ef2f-48ca-a0c5-9d9847ddf478/>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;<img src=https://github.com/user-attachments/assets/b46b757c-405e-4f73-9c37-b333f47238b0/><br>
### Settings
<img src=https://github.com/user-attachments/assets/79c2372a-5dd0-4f3b-af78-4dba90b186ed/><br>
### GE-Proton Manager
<img src=https://github.com/user-attachments/assets/1e38d572-d1df-48fd-bafb-26310c1c9932/><br>
### Create shortcut from .exe
<img src=https://github.com/user-attachments/assets/4d5feb01-0667-4c57-8285-cbfb3bc97c93/>
