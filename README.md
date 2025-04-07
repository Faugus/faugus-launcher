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

### Fedora / Nobara (Copr)
```
sudo dnf -y copr enable faugus/faugus-launcher
sudo dnf -y install faugus-launcher
```
```
# Optional tools
sudo dnf -y install mangohud
sudo dnf -y install gamemode
```

### Bazzite (Copr)
```
sudo tee /etc/yum.repos.d/faugus-launcher.repo > /dev/null <<EOF
[faugus-launcher]
name=Copr repo for faugus-launcher owned by faugus
baseurl=https://download.copr.fedorainfracloud.org/results/faugus/faugus-launcher/fedora-$releasever-$basearch/
type=rpm-md
skip_if_unavailable=True
gpgcheck=1
gpgkey=https://download.copr.fedorainfracloud.org/results/faugus/faugus-launcher/pubkey.gpg
repo_gpgcheck=0
enabled=1
enabled_metadata=1
EOF
sudo rpm-ostree install faugus-launcher
```
Restart your system.

### Ubuntu / Mint / KDE Neon
```
sudo dpkg --add-architecture i386
sudo apt update
sudo apt install -y wget
mkdir -p ~/faugus-launcher
wget -P ~/faugus-launcher https://github.com/Faugus/faugus-launcher/releases/download/1.3.7/faugus-launcher_1.3.7-1_amd64.deb
wget -P ~/faugus-launcher https://github.com/Open-Wine-Components/umu-launcher/releases/download/1.2.6/python3-umu-launcher_1.2.6-1_amd64_ubuntu-noble.deb
wget -P ~/faugus-launcher https://github.com/Open-Wine-Components/umu-launcher/releases/download/1.2.6/umu-launcher_1.2.6-1_all_ubuntu-noble.deb
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
wget -P ~/faugus-launcher https://github.com/Faugus/faugus-launcher/releases/download/1.4.1/faugus-launcher_1.4.1-1_amd64.deb
wget -P ~/faugus-launcher https://github.com/Open-Wine-Components/umu-launcher/releases/download/1.2.6/python3-umu-launcher_1.2.6-1_amd64_debian-12.deb
wget -P ~/faugus-launcher https://github.com/Open-Wine-Components/umu-launcher/releases/download/1.2.6/umu-launcher_1.2.6-1_all_debian-12.deb
sudo apt install -y ~/faugus-launcher/*.deb
sudo rm -r ~/faugus-launcher
```
```
# Optional tools
sudo apt -y install mangohud
sudo apt -y install gamemode
```

### Debian 13
```
sudo dpkg --add-architecture i386
sudo apt update
sudo apt install -y wget
mkdir -p ~/faugus-launcher
wget -P ~/faugus-launcher https://github.com/Faugus/faugus-launcher/releases/download/1.4.1/faugus-launcher_1.4.1-1_amd64.deb
wget -P ~/faugus-launcher https://github.com/Open-Wine-Components/umu-launcher/releases/download/1.2.6/python3-umu-launcher_1.2.6-1_amd64_debian-13.deb
wget -P ~/faugus-launcher https://github.com/Open-Wine-Components/umu-launcher/releases/download/1.2.6/umu-launcher_1.2.6-1_all_debian-13.deb
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
<img src=https://github.com/user-attachments/assets/89c41b52-ec4e-4f00-99ea-22d5c462e19b/>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;<img src=https://github.com/user-attachments/assets/cd929bf9-4a6b-461e-9aa6-0e701da679c4/><br>
### Settings
<img src=https://github.com/user-attachments/assets/f511e810-6006-4ce9-b028-f0f66beca3b5/><br>
### GE-Proton Manager
<img src=https://github.com/user-attachments/assets/c46f90ac-7713-46bf-8795-33d3917fb48e/><br>
### Create shortcut from .exe
<img src=https://github.com/user-attachments/assets/cdc7cdf6-a67c-4405-b94f-566e0a20f5e6/><br>
