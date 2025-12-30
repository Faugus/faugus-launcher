snap_build = get_option('snap_build')
flatpak_build = get_option('flatpak_build')

if flatpak_build
    app_id = 'io.github.Faugus.faugus-launcher'
elif snap_build
    app_id = 'faugus-launcher'
else
    app_id = 'faugus-launcher'
endif

metainfo_file = app_id + '.metainfo.xml'

install_data(
  metainfo_file,
  install_dir: get_option('datadir') / 'metainfo',
)

icon_name = app_id

faugus_launcher_out = app_id + '.desktop'
faugus_proton_manager_out = app_id + '.proton-manager.desktop'
faugus_run_out = app_id + '.run.desktop'
faugus_shortcut_out = app_id + '.shortcut.desktop'

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