install_data(
  'io.github.Faugus.faugus-launcher.metainfo.xml',
  install_dir: get_option('datadir') / 'metainfo',
)

icon_name = 'io.github.Faugus.faugus-launcher'

faugus_launcher_out = 'io.github.Faugus.faugus-launcher.desktop'
faugus_shortcut_out = 'io.github.Faugus.faugus-launcher.shortcut.desktop'

faugus_launcher_desktop = configure_file(
  input: 'io.github.Faugus.faugus-launcher.desktop.in',
  output: faugus_launcher_out,
  configuration: {
    'ICON': icon_name,
    'EXEC': 'faugus-launcher',
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
  faugus_shortcut_desktop,
  install_dir: get_option('datadir') / 'applications'
)
