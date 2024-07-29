# Faugus Launcher
A simple and lightweight app for running Windows games using [UMU-Launcher/UMU-Proton](https://github.com/Open-Wine-Components/umu-launcher)

### Support the project
<a href='https://ko-fi.com/K3K210EMDU' target='_blank'><img src=https://github.com/Faugus/faugus-launcher/blob/main/ko-fi.png width="155" height="35"/></a>&nbsp;&nbsp;
<a href='https://www.paypal.com/donate/?business=57PP9DVD3VWAN&amount=5&no_recurring=0&currency_code=USD' target='_blank'><img src=https://github.com/Faugus/faugus-launcher/blob/main/paypal.png width="155" height="35"/></a>

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

### Debian-based distributions (Experimental)
AppArmor may prevent umu-launcher from working properly. <a href='https://gist.github.com/Faugus/8d3caa3ce93eb1ff90409f3c3dbabe0f' target='_blank'>FIX
```
sudo apt install -y wget
mkdir -p ~/faugus-launcher
wget -P ~/faugus-launcher https://github.com/Faugus/faugus-launcher/releases/download/v1.0-48/faugus-launcher_1.0-48_amd64.deb
wget -P ~/faugus-launcher https://github.com/Faugus/faugus-launcher/releases/download/v1.0-48/python3-umu-launcher_1.0-2_all.deb
wget -P ~/faugus-launcher https://github.com/Faugus/faugus-launcher/releases/download/v1.0-48/umu-launcher_1.0-2_all.deb
sudo apt install -y ~/faugus-launcher/*.deb
sudo rm -r ~/faugus-launcher
```
```
# Optional tools
sudo apt -y install mangohud
sudo apt -y install gamemode
```

# Information
### Default prefix location
```
~/.config/faugus-launcher/prefixes/
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
<p align="center">
  <img src=https://github.com/Faugus/faugus-launcher/assets/112667550/2555a761-c12a-48cb-8888-5f007bb71031/><br>
  <img src=https://github.com/Faugus/faugus-launcher/assets/112667550/cfc9a0a9-8999-4473-ac00-f0fb44b2095c/><br>
  <img src=https://github.com/Faugus/faugus-launcher/assets/112667550/e09130c7-9b46-4a9a-bf8c-9f215a5b3d24/>
  <img src=https://github.com/Faugus/faugus-launcher/assets/112667550/3fe492ef-7fe3-472e-8e54-ee475a51c38c/>
</p>
<p align="center">
<img src=https://github.com/Faugus/faugus-launcher/assets/112667550/a2c5993b-5a67-46a4-9ba4-31ddc1c69377/><br><br>
<img src=https://github.com/Faugus/faugus-launcher/assets/112667550/7b00bcf6-1db8-4c2e-9208-ac9f843f2a49/><br><br>
<img src=https://github.com/Faugus/faugus-launcher/assets/112667550/d5b0368c-1986-46dd-aa2d-67e5c7ad2433/>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;
<img src=https://github.com/Faugus/faugus-launcher/assets/112667550/5979a28b-b057-4ca9-b758-bf869a32d217/>
</p>
