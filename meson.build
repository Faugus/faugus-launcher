project(
  'faugus-launcher',
  version: '1.7.4',
  meson_version: '>=1.2.0',
  license: 'MIT',
  license_files: 'LICENSE',
)

py = import('python').find_installation()
fs = import('fs')
gnome = import('gnome')

subdir('assets')
subdir('languages')
if get_option('flatpak_build')
  subdir('data')
endif

install_data(
  'faugus_launcher.py',
  'faugus_run.py',
  'faugus_proton_manager.py',
  'faugus_components.py',
  'faugus_proton_downloader.py',
  rename: [
    'faugus-launcher',
    'faugus-run',
    'faugus-proton-manager',
    'faugus-components',
    'faugus-proton-downloader',
  ],
  install_mode: 'rwxr-xr-x',
  install_dir: get_option('bindir'),
)

if not get_option('flatpak_build')
  install_data(
    'faugus-launcher.desktop',
    'faugus-shortcut.desktop',
    'faugus-run.desktop',
    'faugus-proton-manager.desktop',
    install_dir: get_option('datadir') / 'applications',
  )
endif

install_data(
  'LICENSE',
  install_dir: get_option('datadir') / 'licenses' / meson.project_name(),
)

gnome.post_install(
  gtk_update_icon_cache: true,
)
