{
	description = "Faugus Launcher";

	inputs = {
		nixpkgs.url = "github:nixos/nixpkgs/nixos-unstable";
		systems.url = "github:nix-systems/default";
		flake-utils.url = "github:numtide/flake-utils";
		flake-utils.inputs.systems.follows = "systems";
	};

	outputs = { self, nixpkgs, flake-utils, ... }:
		let
			homeManagerModule = import ./nix/hmModule.nix {
				faugus-launcher = self.packages.x86_64-linux.faugus-launcher;
			};
		in
		(flake-utils.lib.eachDefaultSystem (system:
			let
				pkgs = import nixpkgs { inherit system; };
			in
			{
				packages = rec {
					faugus-launcher = import ./nix/default.nix pkgs;
					default = faugus-launcher;
				};
			}
		)) // {
			homeManagerModules.default = homeManagerModule;
		};
}
