# Faugus Launcher
A simple and lightweight app for running Windows games using [UMU-Launcher](https://github.com/Open-Wine-Components/umu-launcher)

### Support the project
<a href='https://ko-fi.com/K3K210EMDU' target='_blank'><img src=https://github.com/Faugus/faugus-launcher/blob/main/assets/ko-fi.png width="155" height="35"/></a>&nbsp;&nbsp;
<a href='https://www.paypal.com/donate/?business=57PP9DVD3VWAN&no_recurring=0&currency_code=USD' target='_blank'><img src=https://github.com/Faugus/faugus-launcher/blob/main/assets/paypal.png width="155" height="35"/></a>

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
wget -P ~/faugus-launcher https://github.com/Faugus/faugus-launcher/releases/download/1.2.5/faugus-launcher_1.2.5-1_amd64.deb
wget -P ~/faugus-launcher https://github.com/Faugus/faugus-launcher/releases/download/1.2.5/python3-umu-launcher_1.1.4-1_amd64.deb
wget -P ~/faugus-launcher https://github.com/Faugus/faugus-launcher/releases/download/1.2.5/umu-launcher_1.1.4-1_all.deb
sudo apt install -y ~/faugus-launcher/*.deb
sudo rm -r ~/faugus-launcher
```
```
# Optional tools
sudo apt -y install mangohud
sudo apt -y install gamemode
```

### Flatpak (EXPERIMENTAL)
Download <a href="https://github.com/Faugus/faugus-launcher/releases/download/1.2.5/faugus-launcher-0.2.5-1.flatpak">faugus-launcher-0.2.5-1.flatpak</a> and run:
```
flatpak remote-add --if-not-exists flathub https://flathub.org/repo/flathub.flatpakrepo
flatpak install faugus-launcher-0.2.5-1.flatpak
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
<img src=https://github.com/user-attachments/assets/72b6790e-ce02-4405-aa3d-fa2b3720107c/><br><br>
<img src=https://github.com/user-attachments/assets/958cd1cb-2917-421e-a28a-0cdca0d60c85/><br><br>
<img src=https://github.com/user-attachments/assets/3578ef62-fb00-4147-8978-5c2bcb8e7099/><br>
### Add/Edit game
<img src=https://github.com/user-attachments/assets/a6d30723-6120-4c75-9f13-d183696f8b3f/>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;<img src=https://github.com/user-attachments/assets/449b3b01-2fd0-47c7-b5b1-eb2759fd5139/><br>
### Settings
<img src=https://github.com/user-attachments/assets/2a7dfc31-1f79-48b7-bba6-dbb28006de68/><br>
### GE-Proton Manager
<img src=https://github.com/user-attachments/assets/4b250388-b6df-4af0-982f-9da9f06dc1af/><br>
### Create shortcut from .exe
<img src=https://github.com/user-attachments/assets/f5a65466-b610-42e4-831e-ab3b696c6ab5/><br>
