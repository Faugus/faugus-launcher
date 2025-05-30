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

foreach file : [
  ['faugus_launcher.py', 'faugus-launcher'],
  ['faugus_run.py', 'faugus-run'],
  ['faugus_proton_manager.py', 'faugus-proton-manager'],
  ['faugus_components.py', 'faugus-components']
]
  install_data(
    file[0],
    install_dir: get_option('bindir'),
    rename: file[1],
    install_mode: ['rwxr-xr-x', 'root', 'root']
  )
endforeach

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
