project(
  'faugus-launcher',
  version: '1.5.10.dev0',
  meson_version: '>=1.2.0',
  license: 'MIT',
  license_files: 'LICENSE',
)

py = import('python').find_installation()
fs = import('fs')

subdir('assets')
subdir('languages')

install_data(
  'faugus_launcher.py',
  'faugus_run.py',
  'faugus_proton_manager.py',
  'faugus_components.py',
  rename: [
    'faugus-launcher',
    'faugus-run',
    'faugus-proton-manager',
    'faugus-components',
  ],
  install_mode: 'rwxr-xr-x',
  install_dir: get_option('bindir'),
)

install_data(
  'faugus-launcher.desktop',
  'faugus-shortcut.desktop',
  'faugus-run.desktop',
  'faugus-proton-manager.desktop',
  install_dir: get_option('datadir') / 'applications',
)

install_data(
  'LICENSE',
  install_dir: get_option('datadir') / 'licenses' / meson.project_name(),
)
