{
description = "Faugus Launcher";

inputs = {
	nixpkgs.url = "github:nixos/nixpkgs/nixos-unstable";
	systems.url = "github:nix-systems/default";
	flake-utils.url = "github:numtide/flake-utils";
	flake-utils.inputs.systems.follows = "systems";
};

outputs = { self, nixpkgs, flake-utils, ... }:
	flake-utils.lib.eachDefaultSystem (
		system:
		let
		pkgs = import nixpkgs {
			inherit system;
		};
		stdenv = pkgs.stdenv;
		in rec
	{
	packages = {
		faugus-launcher = import ./nix/default.nix pkgs;
		default = packages.faugus-launcher;
	};
	homeManagerModule = import ./nix/hmModule.nix {inherit (packages) faugus-launcher;};
	homeManagerModules.default = homeManagerModule;
	});
}
