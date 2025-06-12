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

install_data(
  faugus_launcher_desktop,
  install_dir: get_option('datadir') / 'applications'
)
