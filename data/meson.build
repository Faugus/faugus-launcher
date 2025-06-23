install_data(
  'io.github.Faugus.faugus-launcher.metainfo.xml',
  install_dir: get_option('datadir') / 'metainfo',
)

icon_name = get_option('flatpak_build') ? 'io.github.Faugus.faugus-launcher' : 'faugus-launcher'

faugus_launcher_desktop = configure_file(
  input: 'io.github.Faugus.faugus-launcher.desktop.in',
  output: 'io.github.Faugus.faugus-launcher.desktop',
  configuration: {
    'ICON': icon_name,
    'EXEC': 'faugus-launcher',
  }
)

faugus_proton_manager_desktop = configure_file(
  input: 'io.github.Faugus.faugus-launcher.proton-manager.desktop.in',
  output: 'io.github.Faugus.faugus-launcher.proton-manager.desktop',
  configuration: {
    'ICON': icon_name,
  }
)

faugus_run_desktop = configure_file(
  input: 'io.github.Faugus.faugus-launcher.run.desktop.in',
  output: 'io.github.Faugus.faugus-launcher.run.desktop',
  configuration: {
    'ICON': icon_name,
  }
)

faugus_shortcut_desktop = configure_file(
  input: 'io.github.Faugus.faugus-launcher.shortcut.desktop.in',
  output: 'io.github.Faugus.faugus-launcher.shortcut.desktop',
  configuration: {
    'ICON': icon_name,
  }
)

install_data(
  faugus_launcher_desktop,
  faugus_proton_manager_desktop,
  faugus_run_desktop,
  faugus_shortcut_desktop,
  install_dir: get_option('datadir') / 'applications'
)
