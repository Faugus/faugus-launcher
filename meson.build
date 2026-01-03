project(
  'faugus-launcher',
  version: '1.11.8',
  meson_version: '>=1.2.0',
  license: 'MIT',
  license_files: 'LICENSE',
)

py = import('python').find_installation()
fs = import('fs')
gnome = import('gnome')

subdir('assets')
subdir('languages')
subdir('data')
subdir('faugus')

install_data(
  'faugus_launcher.py',
  'faugus_run.py',
  'faugus_proton_manager.py',
  rename: [
    'faugus-launcher',
    'faugus-run',
    'faugus-proton-manager',
  ],
  install_mode: 'rwxr-xr-x',
  install_dir: get_option('bindir'),
)

install_data(
  'LICENSE',
  install_dir: get_option('datadir') / 'licenses' / meson.project_name(),
)

gnome.post_install(
  gtk_update_icon_cache: true,
)
