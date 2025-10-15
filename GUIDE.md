
# User Guide
This guide is for all the users new to Faugus Launcher or to Linux gaming in general. We will cover everything necessary to help you get up and running your favorite PC games on Linux.

## Basic Terms
There are few terms and concepts that you should be familiar with before getting started with gaming on Linux. Linux is not Windows and works very differently, there are certain things you need to keep in mind.

**WINE:** 
- An amazing program (technically a compatibility layer) that allows running Windows programs on Mac & Linux. In most simple terms you think of it as a program that can execute `.exe` files or `.bat` files that we see on Windows.

- Wine is still in constant development and has seen good results for running general Windows applications. But sadly it isn't that great at running video games.

**PROTON:** 
- Proton is another program (compatibility layer) based on Wine for running Windows PC games on Linux. It is created by Valve (creators of Steam) and this is what Steam uses in the background to run Windows games on Linux gracefully.

- Proton-GE is a seperate project based on Proton created by user GloriousEggroll. It provides additional fixes, improvements and compatibility enhancements for old as well as new games. It is generally recommended to use Proton-GE for every game you play on Linux unless you have a good reason not to.

**PROTON/WINE PREFIX:** 
- A Wine Prefix or a Proton Prefix is essentially a large folder that mimics a Windows system with its own `C:/` drive, program files, registry files, various dependencies and more. By default, every single game you install in Linux would be in its own Wine Prefix.

- The reason for this is to "sandbox" and "isolate" each game so that if something goes wrong in one "Windows system", all your other games would be unaffected. It also allows you to safely make changes to a specific Prefix without worrying about it affecting more than one game.

**WINETRICKS:**
- Winetricks is a helper program for Wine/Proton to manage or configure various settings for a particular Wine Prefix environment.

- We can install some essential components (like Visual C++ Redistributable), DLLs, fonts and other dependencies or programs that some games might require.

**GAMESCOPE:**
- Gamescope is a micro-compositor developed by Valve that runs games in an isolated virtual display, providing games-specific features like resolution spoofing, upscaling (FSR for AMD or NIS for Nvidia GPUs) and compatibility enhancements for Wayland-based Desktops (like KDE or Gnome).

- Think of it as an extra layer running on top of your games independent of the underlying desktop environment or platform. It is generally recommended to use Gamescope everytime you play games on Linux.

**GAMEMODE:**
- Gamemode is a package consisting of bunch of scripts that handles the power output of portable devices like laptops or Steam Deck by switching the power profile to "performance" when launching and playing games.

- This usually provides performance improvements to the game you are running. After closing the game, the profile would reset back to "balanced" or "power-saving" mode (whatever the profile was on before launching the game).

- Note: If you are using CachyOS Linux distribution, it already comes with a package called `game-performance` that provides same functionality as gamemode with optimizations made particularly for CachyOS systems. Do not use gamemode within CachyOS, use `game-performance`.

**GAME LAUNCHERS:**
- A game launcher in Linux is a complete application that makes use of Wine/Proton, Wine Prefix and Winetricks together in a unified manner to make it easy to install, manage and play games on Linux.

- More technically, it handles various Proton versions (like Proton-GE or just Proton) to run games. For each game you install, it creates a seperate Wine Prefix. And then for tweaking and configuring additional stuff you can run Winetricks on that particular Wine Prefix. You can do all these things without a game launcher application but it makes it very easy by taking care of essential stuff behind the curtains.

- Faugus Launcher is a simple, minimal and lightweight game launcher that aims that aims to simplify the process of managing your Windows games on Linux. Some other popular game launchers are Lutris and Heroic Games Launcher.

## How to install games?
This section of the guide will explain the basic workflow for installing games on your Linux system. This guide assumes that you have read the above and understood some basics and have Faugus Launcher installed on your system.

<!-- ### Games with `.EXE` or `.MSI` Installers -->
1. **Prepare Your Game Installation Files:**
	- Create a separate folder `~/Downloads/Games`. This folder will keep your games folders with installation files (folders containing `.exe` or `.msi` files).
	
	- We will be using the GOG copy of the game `Prince of Persia The Sands of Time` as an example. Now, your setup files are in `~/Downloads/Games/Prince of Persia The Sands of Time/` and `setup_prince_of_persia_-_the_sands_of_time_181_(28548).exe` is the installer for the game.

2. **Download Proton-GE and Create Default Wine Prefix:**
	- Open Faugus Launcher and you will see that we have options to "Add Games" via the `+` button and "Settings" via the cog-wheel icon. We will not be adding new games just yet, we have to configure some things before that.

	- Open the settings: Under "Default Prefixes Location" you will see the default location of your Wine Prefixes for all of your games. You can set it to a different location like `~/Games/`.

	- Under the "Default Proton" section, choose the Proton version "GE-Proton Latest" and under the "Miscallaneous" section check the box with "Use discrete GPU" if you are indeed using a discrete GPU and does not want to use the integrated GPU for the games.

	- Now, under "Default Prefix Tools" section, click on the Winetricks button. A dialog box will appear inidicating that it will download and install our selected Proton version and create an initial `default` Prefix in our Prefixes location. Wait for it to complete. Now, close the settings.

3. **Install the Game:**
	- Click on the `+` button to add a new game to Faugus. Fill the title of the game under the "Title". Under the Prefix section you can see the default generated path of your game Prefix based on the title you filled.

	- Switch to the "Tools" tab at the top and click on the "Run" button located bottom-right of the dialog box. This allows you to open executable files running under the game's Prefix. Locate the installer `.exe` file and open it through the file chooser dialog. Now, install the game just like you do on Windows.

	- When prompted to choose the installation location for the game, choose any location under the `C:` drive (conventionally, `C:/Program Files` or `C:/Program Files (x86)`). After installation is complete, exit the installer and do not launch the game if the dialog prompts you to.

4. **Install Essential Dependencies:**
	- Now that you have installed your game in the Wine Prefix, it is time to take care of some of the dependencies that it might need. These dependencies might be available as `.exe`, `.msi` or `.bat` files. For example, older Ubisoft games require to install `UPlay` program for its games to work. 

	- **Microsoft Visual C++ Redistributable:** Most of the games requires you to have some specific version of Microsoft Visual C++ Redistributable installed on your Wine Prefix. The easiest and recommended way is to download and install latest release of [vcredist](https://github.com/abbodi1406/vcredist/releases) from their releases page. It is an open-source project that bundles and repacks all the previous versions of Microsoft Visual C++ Redistributable into a single installer file. Choose this installer `.exe` file from the file chooser dialog and follow the steps.

	- Go to the "Tools" tab and at the right bottom you will find the "Run" button which allows you to run executable (like `.exe`, `.msi` or `.bat`) files in the Wine Prefix you have just created for your game. Click on it and a file chooser dialog box will appear for you to choose your executable file. Go to the location where installer file is present and choose it. Follow the dialog steps to install your dependencies.

5. **All Complete! Its Time to Play Some Games:**
	- After installing your game and taking care of the dependencies it is finally time to play. Click the `Ok` button to save changes and close the dialog. From the home screen you can see that a new entry for your game has been added. Select it and click on the play button to open the game. Enjoy!

## Tips
- **Game Shortcuts:** To add shortcuts of your games to your desktop and application menu, right click on your selected game entry and click on "Edit". From the "Game/App" tab look to the bottom of the dialog and tick "Desktop" and "App Menu" checkboxes. To add the game to your Steam library as well tick the "Steam" checkbox too. You can now find the shortcuts for your game on your desktop, application and steam.

<!-- TODO: waiting for gamescope integration for faugus launcher to recommend general gamescope launch options --> 


