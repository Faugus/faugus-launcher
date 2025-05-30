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
  'faugus-launcher.py',
  'faugus-run.py',
  'faugus-proton-manager.py',
  'faugus-components.py',
  'faugus-gamepad.py',
  'faugus-session',
  rename: [
    'faugus-launcher',
    'faugus-run',
    'faugus-proton-manager',
    'faugus-components',
    'faugus-gamepad',
    'faugus-session',
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
