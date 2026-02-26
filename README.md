# Forge SD-Krita Plugin

A Krita Plugin to work with [Forge WebUI](https://github.com/lllyasviel/stable-diffusion-webui-forge) and [Forge Neo](https://github.com/Haoming02/sd-webui-forge-classic/tree/neo)

**Note:** This plugin is in an experimental state. It might not work at all. Things are expected to change somewhat frequently.

# Install Instructions

1. Ensure your server has API access. For Forge, this means adding `--api` to your `COMMANDLINE_ARGS` in `webui-user.bat` (or equivalent)
2. Open Krita then go `Settings > Manage Resources`, then in the bottom right click the `Open Resource Folder` button

![](readme_imgs/krita_settings.png)

![](readme_imgs/krita_manage_resources.png)

1. Find the `pykrita` folder inside the explorer window Krita opened up
2. There's two options for installing the extension:
    * Easy install, annoying update - Download the project and put both the folder `forge` and the file `forge.desktop` in your `pykrita` folder. You'll have to redownload and recopy the files to this path any time you wish to update.
    * Annoying install, easy update - Git clone the project, then create a symlink in the `pykrita` folder to `forge` and `forge.desktop`. Anytime you do a git pull it'll update the plugin.
        * **Windows**: Open Command Prompt by right clicking it and selecting "Run as Administrator..." and run these commands

            ```bat
            mklink /j "path_to_your_pykrita_folder\forge" "path_to_your_git_pull\forge"
            mklink "path_to_your_pykrita_folder\forge.desktop" "path_to_your_git_pull\forge.desktop"
            ```

        * **Linux**: Open a terminal and run these commands

            ```sh
            ln -s "path_to_your_pykrita_folder/forge" "path_to_your_git_pull/forge"
            ln -s "path_to_your_pykrita_folder/forge.desktop" "path_to_your_git_pull/forge.desktop"
            ```

3. Restart Krita and go to `Settings > Configure Krita...`, then at the bottom left side of the window until you see `Python Plugin Manager`. Click that, then check the box to enable `forge SD Plugin for Krita`
4. Restart Krita one more time
5. You should see a docked `Forge SD` window in Krita. If it's not showing up, go to `Settings > Dockers` and check the box next to `Forge SD`
