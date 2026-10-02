{
  description = "Faugus Launcher";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
  };

  outputs = { self, nixpkgs }:
  let
    system = "x86_64-linux";
    pkgs = import nixpkgs {
      inherit system;
    };
  in
  {
    packages.${system}.default = pkgs.python3Packages.buildPythonApplication {
      pname = "faugus-launcher";
      version = "2.4.2";

      pyproject = false;

      src = ./.;

      nativeBuildInputs = [
        pkgs.meson
        pkgs.ninja
        pkgs.wrapGAppsHook4
        pkgs.gobject-introspection
      ];

      buildInputs = [
        pkgs.gtk4
        pkgs.libadwaita
        pkgs.libmanette
      ];

      dependencies = with pkgs.python3Packages; [
        pygobject3
        requests
        pillow
        vdf
        psutil
        dbus-python
        icoextract
      ];

      postPatch = ''
        substituteInPlace faugus-launcher \
          --replace-fail "/usr/bin/python3" \
            "${pkgs.python3Packages.python.interpreter}"
      '';

      preFixup = ''
        gappsWrapperArgs+=(
          --set PYTHONPATH \
            "$out/${pkgs.python3Packages.python.sitePackages}:$PYTHONPATH"

          --suffix PATH : "${pkgs.lib.makeBinPath [
            pkgs.coreutils
            pkgs.gawk
            pkgs.gnugrep
            pkgs.which
            pkgs.xdg-utils
            pkgs.python3Packages.icoextract
          ]}"
        )
      '';
    };
  };
}
