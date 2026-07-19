# Faugus
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
wget -P ~/faugus-launcher https://github.com/Faugus/faugus-launcher/releases/download/2.0.0/faugus-launcher_2.0.0-1_all.deb
sudo apt install -y ~/faugus-launcher/*.deb
sudo rm -r ~/faugus-launcher
```

## [Flatpak](https://flathub.org/apps/io.github.Faugus.faugus-launcher)
### Installation:
```
flatpak install flathub io.github.Faugus.faugus-launcher
```
### Running:
```
flatpak run io.github.Faugus.faugus-launcher
```
### MangoHud installation:
```
flatpak install org.freedesktop.Platform.VulkanLayer.MangoHud/x86_64/25.08
```
### Important permissions:
```
# Allow Faugus Launcher to detect Steam users and games
sudo flatpak override io.github.Faugus.faugus-launcher --filesystem=~/.var/app/com.valvesoftware.Steam/
sudo flatpak override io.github.Faugus.faugus-launcher --talk-name=org.freedesktop.Flatpak

# Allow Steam to run Faugus Launcher shortcuts
sudo flatpak override com.valvesoftware.Steam --talk-name=org.freedesktop.Flatpak

# Allow Steam to see Faugus Launcher games icons
sudo flatpak override com.valvesoftware.Steam --filesystem=~/.var/app/io.github.Faugus.faugus-launcher/config/faugus-launcher/
sudo flatpak override com.valvesoftware.Steam --filesystem=~/.config/faugus-launcher/
```
### Known issue:
- Gamescope doesn't work

## Build from source
```
meson setup builddir --prefix=/usr
cd builddir
ninja
sudo ninja install
```
### Dependencies:
```
meson ninja pygobject requests pillow vdf psutil dbus-python gtk4 libadwaita libmanette icoextract
```

## Translations
[![Translation status](https://hosted.weblate.org/widget/faugus-launcher/faugus-launcher/svg-badge.svg)](https://hosted.weblate.org/engage/faugus-launcher/)

Translations are managed on [Weblate](https://hosted.weblate.org/projects/faugus-launcher/faugus-launcher/) — Sign in, pick your language, and translate directly in the browser.

# Usage
[![YouTube](http://i.ytimg.com/vi/Ay6C2f55Pc8/hqdefault.jpg)](https://www.youtube.com/watch?v=Ay6C2f55Pc8)

# Information
### Default prefixes location
```
~/Faugus/
```

### Protons location
```
~/.local/share/Steam/compatibilitytools.d/
```

### Gamepad mapping
| Action        | Playstation | Xbox     |
|---------------|-------------|----------|
| Confirm       | Cross       | A        |
| Cancel        | Circle      | B        |
| Game menu     | Triangle    | Y        |
| Kill          | Square      | X        |
| Add game/app  | L1          | LB       |
| Settings      | R1          | RB       |
| Power options | Options     | Menu     |

# Screenshots

<details>
<summary><b>Main window</b></summary>
<br>

**List**
<img src=screenshots/main-list.png/>

**Grid**
<img src=screenshots/main-grid.png/>

**Covers**
<img src=screenshots/main-covers.png/>

**SteamGridDB**
<img src=screenshots/main-steamgriddb.png/>

</details>

<details>
<summary><b>Add/Edit game</b></summary>
<br>
<img src=screenshots/add-main.png/>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;<img src=screenshots/add-tool.png/>
<br><br>
<img src=screenshots/launch-settings.png/>
</details>

<details>
<summary><b>Settings</b></summary>
<br>
<img src=screenshots/settings.png/>
</details>

<details>
<summary><b>Proton Manager</b></summary>
<br>
<img src=screenshots/proton-manager.png/>
</details>
