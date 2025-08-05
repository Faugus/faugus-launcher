flatpak_build = get_option('flatpak_build')

metainfo_file = flatpak_build ? 'io.github.Faugus.faugus-launcher.metainfo.xml' : 'faugus-launcher.metainfo.xml'

install_data(
  metainfo_file,
  install_dir: get_option('datadir') / 'metainfo',
)

icon_name = flatpak_build ? 'io.github.Faugus.faugus-launcher' : 'faugus-launcher'

faugus_launcher_out = flatpak_build ? 'io.github.Faugus.faugus-launcher.desktop' : 'faugus-launcher.desktop'
faugus_proton_manager_out = flatpak_build ? 'io.github.Faugus.faugus-launcher.proton-manager.desktop' : 'faugus-proton-manager.desktop'
faugus_run_out = flatpak_build ? 'io.github.Faugus.faugus-launcher.run.desktop' : 'faugus-run.desktop'
faugus_shortcut_out = flatpak_build ? 'io.github.Faugus.faugus-launcher.shortcut.desktop' : 'faugus-shortcut.desktop'

faugus_launcher_desktop = configure_file(
  input: 'io.github.Faugus.faugus-launcher.desktop.in',
  output: faugus_launcher_out,
  configuration: {
    'ICON': icon_name,
    'EXEC': 'faugus-launcher',
  }
)

faugus_proton_manager_desktop = configure_file(
  input: 'io.github.Faugus.faugus-launcher.proton-manager.desktop.in',
  output: faugus_proton_manager_out,
  configuration: {
    'ICON': icon_name,
  }
)

faugus_run_desktop = configure_file(
  input: 'io.github.Faugus.faugus-launcher.run.desktop.in',
  output: faugus_run_out,
  configuration: {
    'ICON': icon_name,
  }
)

faugus_shortcut_desktop = configure_file(
  input: 'io.github.Faugus.faugus-launcher.shortcut.desktop.in',
  output: faugus_shortcut_out,
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
