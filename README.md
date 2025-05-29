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

### Fedora / Nobara (Copr)
```
sudo dnf -y copr enable faugus/faugus-launcher
sudo dnf -y install faugus-launcher
```

### Bazzite (Copr)
```
sudo dnf5 -y copr enable faugus/faugus-launcher
sudo rpm-ostree -y install faugus-launcher
```
Restart your system.

### Ubuntu / Mint / KDE Neon
```
sudo dpkg --add-architecture i386
sudo apt update
sudo apt install -y wget
mkdir -p ~/faugus-launcher
wget -P ~/faugus-launcher https://github.com/Faugus/faugus-launcher/releases/download/1.5.9/faugus-launcher_1.5.9-2_all.deb
wget -P ~/faugus-launcher https://github.com/Open-Wine-Components/umu-launcher/releases/download/1.2.6/python3-umu-launcher_1.2.6-1_amd64_ubuntu-noble.deb
wget -P ~/faugus-launcher https://github.com/Open-Wine-Components/umu-launcher/releases/download/1.2.6/umu-launcher_1.2.6-1_all_ubuntu-noble.deb
sudo apt install -y ~/faugus-launcher/*.deb
sudo rm -r ~/faugus-launcher
```

### Debian 13
```
sudo dpkg --add-architecture i386
sudo apt update
sudo apt install -y wget
mkdir -p ~/faugus-launcher
wget -P ~/faugus-launcher https://github.com/Faugus/faugus-launcher/releases/download/1.5.9/faugus-launcher_1.5.9-2_all.deb
wget -P ~/faugus-launcher https://github.com/Open-Wine-Components/umu-launcher/releases/download/1.2.6/python3-umu-launcher_1.2.6-1_amd64_debian-13.deb
wget -P ~/faugus-launcher https://github.com/Open-Wine-Components/umu-launcher/releases/download/1.2.6/umu-launcher_1.2.6-1_all_debian-13.deb
sudo apt install -y ~/faugus-launcher/*.deb
sudo rm -r ~/faugus-launcher
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
If you want to use native builds like proton-cachyos or proton-ge-custom, please symlink them to the user folder.
```
ln -s /usr/share/steam/compatibilitytools.d/proton-cachyos ~/.local/share/Steam/compatibilitytools.d/
ln -s /usr/share/steam/compatibilitytools.d/proton-ge-custom ~/.local/share/Steam/compatibilitytools.d/
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
<img src=https://github.com/user-attachments/assets/5d7285f1-9202-44d4-8161-fff89ba73d0b/><br><br>
<img src=https://github.com/user-attachments/assets/3b9f147a-ae05-493b-9f35-cf588269c354/><br><br>
<img src=https://github.com/user-attachments/assets/c2b82cd8-83fd-47ab-8cb9-2da127799b5d/><br>

### Add/Edit game
<img src=https://github.com/user-attachments/assets/4ec6edfc-b47b-4420-8b99-1d19e900c1df/>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;<img src=https://github.com/user-attachments/assets/fe6a45e1-fafb-4957-aff0-111a934042c8/><br>
### Settings
<img src=https://github.com/user-attachments/assets/037f3a4b-2688-417e-9419-c0032485746a/><br>
### GE-Proton Manager
<img src=https://github.com/user-attachments/assets/50635aa3-8f6a-4846-a4e4-8cb8f5ca05a5/><br>
### Create shortcut from .exe file
<img src=https://github.com/user-attachments/assets/8b824dbc-49f8-45ec-b3d0-7480d8c4be81/><br>
