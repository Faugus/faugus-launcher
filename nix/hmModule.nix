{faugus-launcher}:
{ 
	config, 
	lib, 
	pkgs, 
	... 
}:
let
	cfg = config.programs.faugus-launcher;
	json = pkgs.formats.json { };
  
	configDir = "${config.xdg.configHome}/faugus-launcher";
	dataDir = "${config.xdg.dataHome}/faugus-launcher";
  
	files = lib.filter (f: f.value != null) [
		{ value = cfg.config;     name = "config.json";     dir = configDir; }
		{ value = cfg.envar;      name = "envar.json";      dir = configDir; }
		{ value = cfg.games;      name = "games.json";      dir = dataDir; }
		{ value = cfg.categories; name = "categories.json"; dir = dataDir; }
	];
  
	# Copied (mode 644), not linked, so the program can still edit the files
	installLine = f:
		if builtins.isPath f.value then ''
			run install -Dm644 "${f.value}" "${f.dir}/${f.name}"
		'' else ''
			run install -Dm644 ${json.generate f.name f.value} "${f.dir}/${f.name}"
		'';
  
	opt = lib.mkOption {
		type = lib.types.nullOr (lib.types.oneOf [
			json.type
			lib.types.pathWith {}
		]);
		default = null;
	};
in
{
	options.programs.faugus-launcher = {
		enable = lib.mkEnableOption "Faugus Launcher";
		package = lib.mkOption {
			type = lib.types.package;
			default = faugus-launcher;
			defaultText = lib.literalExpression "pkgs.faugus-launcher";
			description = "The package to use.";
		};
		config = opt;
		envar = opt;
		games = opt;
		categories = opt;
	};

	config = lib.mkIf cfg.enable {
		home.packages = [ cfg.package ];
		home.activation.faugusLauncherFiles =
		lib.hm.dag.entryAfter [ "writeBoundary" ]
			(lib.concatMapStrings installLine files);
	};
}

