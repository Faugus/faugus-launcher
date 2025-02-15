# Faugus Launcher
A simple and lightweight app for running Windows games using [UMU-Launcher](https://github.com/Open-Wine-Components/umu-launcher)

### Support the project
<a href='https://ko-fi.com/K3K210EMDU' target='_blank'><img src=https://github.com/Faugus/faugus-launcher/blob/main/assets/ko-fi.png width="155" height="35"/></a>&nbsp;&nbsp;
<a href='https://www.paypal.com/donate/?business=57PP9DVD3VWAN&no_recurring=0&currency_code=USD' target='_blank'><img src=https://github.com/Faugus/faugus-launcher/blob/main/assets/paypal.png width="155" height="35"/></a>

# Installation
### Arch-based distributions (AUR)
```
yay -S --noconfirm faugus-launcher
```
```
# Optional tools
sudo pacman -S --noconfirm mangohud
sudo pacman -S --noconfirm gamemode
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
```

### Ubuntu / Mint / KDE Neon
```
sudo dpkg --add-architecture i386
sudo apt update
sudo apt install -y wget
mkdir -p ~/faugus-launcher
wget -P ~/faugus-launcher https://github.com/Faugus/faugus-launcher/releases/download/1.3.1/faugus-launcher_1.3.1-1_amd64.deb
wget -P ~/faugus-launcher https://github.com/Open-Wine-Components/umu-launcher/releases/download/1.2.3/python3-umu-launcher_1.2.3-1_amd64_ubuntu-noble.deb
wget -P ~/faugus-launcher https://github.com/Open-Wine-Components/umu-launcher/releases/download/1.2.3/umu-launcher_1.2.3-1_all_ubuntu-noble.deb
sudo apt install -y ~/faugus-launcher/*.deb
sudo rm -r ~/faugus-launcher
```
```
# Optional tools
sudo apt -y install mangohud
sudo apt -y install gamemode
```

### Debian 12
```
sudo dpkg --add-architecture i386
sudo apt update
sudo apt install -y wget
mkdir -p ~/faugus-launcher
wget -P ~/faugus-launcher https://github.com/Faugus/faugus-launcher/releases/download/1.3.1/faugus-launcher_1.3.1-1_amd64.deb
wget -P ~/faugus-launcher https://github.com/Open-Wine-Components/umu-launcher/releases/download/1.2.3/python3-umu-launcher_1.2.3-1_amd64_debian-12.deb
wget -P ~/faugus-launcher https://github.com/Open-Wine-Components/umu-launcher/releases/download/1.2.3/umu-launcher_1.2.3-1_all_debian-12.deb
sudo apt install -y ~/faugus-launcher/*.deb
sudo rm -r ~/faugus-launcher
```
```
# Optional tools
sudo apt -y install mangohud
sudo apt -y install gamemode
```

### openSUSE (Packaged by [ToRRent1812](https://github.com/ToRRent1812))
```
# Tumbleweed
sudo zypper addrepo https://download.opensuse.org/repositories/home:/Rabbit95/openSUSE_Tumbleweed/ home:Rabbit95
sudo zypper --gpg-auto-import-keys install -y faugus-launcher
```
```
# Slowroll
sudo zypper addrepo https://download.opensuse.org/repositories/home:/Rabbit95/openSUSE_Slowroll/ home:Rabbit95
sudo zypper --gpg-auto-import-keys install -y faugus-launcher
```
```
# Optional tools
sudo zypper install -y mangohud
```

### Flatpak (EXPERIMENTAL)
Download <a href="https://github.com/Faugus/faugus-launcher/releases/download/1.3.1/faugus-launcher-0.3.1-1.flatpak">faugus-launcher-0.3.1-1.flatpak</a> and run:
```
flatpak remote-add --if-not-exists flathub https://flathub.org/repo/flathub.flatpakrepo
flatpak install faugus-launcher-0.3.1-1.flatpak
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

# Screenshots
### Main window
<img src=https://github.com/user-attachments/assets/6f6fdd3e-857d-4aa2-b7b2-0238bc39125a/><br><br>
<img src=https://github.com/user-attachments/assets/eb988923-4f0c-4c89-97fb-f9106c90620d/><br><br>
<img src=https://github.com/user-attachments/assets/19b42740-92fa-4fae-befc-13296c97d029/><br>
### Add/Edit game
<img src=https://github.com/user-attachments/assets/93a69aa1-6248-42ec-8191-cbf297cc525f/>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;<img src=https://github.com/user-attachments/assets/cd929bf9-4a6b-461e-9aa6-0e701da679c4/><br>
### Settings
<img src=https://github.com/user-attachments/assets/ce53a552-50d5-4e8b-88b2-c67ab41b2007/><br>

### GE-Proton Manager
<img src=https://github.com/user-attachments/assets/c46f90ac-7713-46bf-8795-33d3917fb48e/><br>
### Create shortcut from .exe
<img src=https://github.com/user-attachments/assets/828aac17-6aa5-4d29-a908-dbbc8a5604d5/><br>
