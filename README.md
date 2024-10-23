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
wget -P ~/faugus-launcher https://github.com/Faugus/faugus-launcher/releases/download/v1.1-1/faugus-launcher_1.1-1_amd64.deb
wget -P ~/faugus-launcher https://github.com/Faugus/faugus-launcher/releases/download/v1.1-1/python3-umu-launcher_1.1.3-1_amd64.deb
wget -P ~/faugus-launcher https://github.com/Faugus/faugus-launcher/releases/download/v1.1-1/umu-launcher_1.1.3-1_all.deb
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
<img src=https://github.com/user-attachments/assets/d59e945a-0f60-4b1f-9044-f3c277ab1bd1/><br>
### Add/Edit game
<img src=https://github.com/user-attachments/assets/cf70c8e4-6b59-4ce6-9958-93b5b80ea244/>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;<img src=https://github.com/user-attachments/assets/0bbb79ff-447c-4d7f-a788-32ea5251770b/><br>
### Settings
<img src=https://github.com/user-attachments/assets/b80813a6-5c2c-4ad8-9546-a652351ae6b0/><br>
### GE-Proton Manager
<img src=https://github.com/user-attachments/assets/0ba08924-9556-4939-9881-6910ea6240a1/><br>
### Create shortcut from .exe
<img src=https://github.com/user-attachments/assets/080c37b0-5ad0-4192-b4f2-f1bdd08dcb75/><br>

## Light theme
### Main window
<img src=https://github.com/user-attachments/assets/19186863-52b7-4773-99ac-cdcc574b97f0/><br>
### Add/Edit game
<img src=https://github.com/user-attachments/assets/3f1c6328-ef2f-48ca-a0c5-9d9847ddf478/>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;<img src=https://github.com/user-attachments/assets/f818721e-447a-4e0d-aec5-111892a3de9e/><br>
### Settings
<img src=https://github.com/user-attachments/assets/85410483-32ea-4d66-b046-9f6ecb002588/><br>
### GE-Proton Manager
<img src=https://github.com/user-attachments/assets/acfa98d9-dcf6-4c50-8ba8-2ab6f41cadb9/><br>
### Create shortcut from .exe
<img src=https://github.com/user-attachments/assets/4d5feb01-0667-4c57-8285-cbfb3bc97c93/>
