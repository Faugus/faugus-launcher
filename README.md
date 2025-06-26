# Faugus Launcher
A simple and lightweight app for running Windows games using [UMU-Launcher](https://github.com/Open-Wine-Components/umu-launcher)

### Support the project
<a href='https://ko-fi.com/K3K210EMDU' target='_blank'><img src=https://github.com/Faugus/faugus-launcher/blob/main/assets/ko-fi.png width="155" height="35"/></a>&nbsp;&nbsp;
<a href='https://www.paypal.com/donate/?business=57PP9DVD3VWAN&no_recurring=0&currency_code=USD' target='_blank'><img src=https://github.com/Faugus/faugus-launcher/blob/main/assets/paypal.png width="155" height="35"/></a>

# Installation
## Arch-based distributions (AUR)
```
yay -S --noconfirm faugus-launcher
```

## Fedora / Nobara (Copr)
```
sudo dnf -y copr enable faugus/faugus-launcher
sudo dnf -y install faugus-launcher
```

## Bazzite (Copr)
[Flatpak](#flatpak) is the preferred app format for Bazzite. Use of rpm-ostree is heavily discouraged.
```
sudo dnf5 -y copr enable faugus/faugus-launcher
sudo rpm-ostree -y install faugus-launcher
```
Restart your system.

## Debian-based distributions
### PPA (Ubuntu, Mint, KDE Neon...)
```
sudo dpkg --add-architecture i386
sudo add-apt-repository -y ppa:faugus/faugus-launcher
sudo apt update
sudo apt install -y faugus-launcher
```
### .deb package
```
sudo dpkg --add-architecture i386
sudo apt update
sudo apt install -y wget
mkdir -p ~/faugus-launcher
wget -P ~/faugus-launcher https://github.com/Faugus/faugus-launcher/releases/download/1.7.1/faugus-launcher_1.7.1-1_all.deb
sudo apt install -y ~/faugus-launcher/*.deb
sudo rm -r ~/faugus-launcher
```

## openSUSE (Packaged by [ToRRent1812](https://github.com/ToRRent1812))
### Tumbleweed:
```
sudo zypper addrepo https://download.opensuse.org/repositories/home:/Rabbit95/openSUSE_Tumbleweed/ home:Rabbit95
sudo zypper --gpg-auto-import-keys install -y faugus-launcher
```
### Slowroll:
```
sudo zypper addrepo https://download.opensuse.org/repositories/home:/Rabbit95/openSUSE_Slowroll/ home:Rabbit95
sudo zypper --gpg-auto-import-keys install -y faugus-launcher
```

<a id="flatpak"></a>
## [Flatpak](https://flathub.org/apps/io.github.Faugus.faugus-launcher)
### Installation:
```
flatpak install flathub io.github.Faugus.faugus-launcher
```
### Running:
```
flatpak run io.github.Faugus.faugus-launcher
```
### Steam Flatpak integration
Allow Faugus Launcher to detect Steam users:
```
flatpak --user override io.github.Faugus.faugus-launcher --filesystem=~/.var/app/com.valvesoftware.Steam/.steam/steam/userdata/
```
Allow Steam to run Faugus Launcher's shortcuts:
```
flatpak --user override com.valvesoftware.Steam --talk-name=org.freedesktop.Flatpak
```
Allow Steam to see the game's icon:
```
flatpak --user override com.valvesoftware.Steam --filesystem=~/.var/app/io.github.Faugus.faugus-launcher/config/faugus-launcher/
```
### Known issues:
- The 'stop' button won't close games/apps
- Gamescope doesn't work
- It may not use the system theme in some DEs. Workaround: give it access to GTK config files:
```
flatpak --user override io.github.Faugus.faugus-launcher --filesystem=xdg-config/gtk-3.0:ro
```

## Build from source
```
meson setup builddir --prefix=/usr
cd builddir
ninja
sudo ninja install
```
### Dependencies:
```
meson ninja pygobject requests pillow filelock vdf psutil umu-launcher imagemagick icoextract libayatana-appindicator
```

# Usage
[![YouTube](http://i.ytimg.com/vi/Ay6C2f55Pc8/hqdefault.jpg)](https://www.youtube.com/watch?v=Ay6C2f55Pc8)

# Information
### Default prefixes location
```
~/Faugus/
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
<img src=https://github.com/user-attachments/assets/62738021-45f7-495c-85ff-8c0a740285d4/><br>
### Add/Edit game
<img src=https://github.com/user-attachments/assets/4ec6edfc-b47b-4420-8b99-1d19e900c1df/>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;<img src=https://github.com/user-attachments/assets/fe6a45e1-fafb-4957-aff0-111a934042c8/><br>
### Settings
<img src=https://github.com/user-attachments/assets/e92d764a-0407-434b-b7cc-70ebe34167c3/><br>
### GE-Proton Manager
<img src=https://github.com/user-attachments/assets/50635aa3-8f6a-4846-a4e4-8cb8f5ca05a5/><br>
### Create shortcut from .exe file
<img src=https://github.com/user-attachments/assets/8b824dbc-49f8-45ec-b3d0-7480d8c4be81/><br>
