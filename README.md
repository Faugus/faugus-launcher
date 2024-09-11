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
wget -P ~/faugus-launcher https://github.com/Faugus/faugus-launcher/releases/download/v1.0-64/faugus-launcher_1.0-64_amd64.deb
wget -P ~/faugus-launcher https://github.com/Faugus/faugus-launcher/releases/download/v1.0-55/python3-umu-launcher_1.0-1.20240823.9b12f90_all.deb
wget -P ~/faugus-launcher https://github.com/Faugus/faugus-launcher/releases/download/v1.0-55/umu-launcher_1.0-1.20240823.9b12f90_all.deb
sudo apt install -y ~/faugus-launcher/*.deb
sudo rm -r ~/faugus-launcher
```
```
# Optional tools
sudo apt -y install mangohud
sudo apt -y install gamemode
```

# Usage
[![YouTube](http://i.ytimg.com/vi/Ay6C2f55Pc8/hqdefault.jpg)](https://www.youtube.com/watch?v=Ay6C2f55Pc8)


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
## Dark theme
### Main window
<img src=https://github.com/user-attachments/assets/31e535df-380d-4e3c-8626-0baf478dc072/><br>
### Add/Edit game
<img src=https://github.com/user-attachments/assets/7bef8540-861a-4971-b8db-968c37b69743/>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;<img src=https://github.com/user-attachments/assets/c5fbfb89-05f0-4649-b209-8a614011a3af/><br>
### Settings
<img src=https://github.com/user-attachments/assets/229867a7-35fe-4000-99dd-ec8081d41f7f/><br>
### Create shortcut from .exe
<img src=https://github.com/user-attachments/assets/5284eb26-8e87-4fc8-b795-9aed07c2f1e7/><br>


## Light theme
### Main window
<img src=https://github.com/user-attachments/assets/2ec59e62-8df6-446a-afec-08a36023ac4a/><br>
### Add/Edit game
<img src=https://github.com/user-attachments/assets/025e1654-7db4-4709-8175-91b85b3de59d/>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;<img src=https://github.com/user-attachments/assets/43f59ea5-2988-4350-9e67-0ad4cff8ae3f/><br>
### Settings
<img src=https://github.com/user-attachments/assets/56a9d912-a1b9-4ac8-a251-83a6b046bd2e/><br>
### Create shortcut from .exe
<img src=https://github.com/user-attachments/assets/6b425cc6-05ba-46da-b01e-882ea3985d72/>
