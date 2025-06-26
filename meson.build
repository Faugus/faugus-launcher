project_name = 'faugus-launcher'
project_version = '1.7.2'

license_args = []

if meson.version().version_compare('>=0.64.0') and run_command('env', 'USE_LICENSE_FILES', check: false).stdout().strip() != '0'
  license_args = [license: 'MIT', license_files: 'LICENSE']
else
  license_args = [license: 'MIT']
endif

project(
  project_name,
  version: project_version,
  meson_version: '>=0.61.0',
  license_args...
)

py = import('python').find_installation()
fs = import('fs')
gnome = import('gnome')

subdir('assets')
subdir('data')
subdir('languages')

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
  install_dir: get_option('datadir') / 'licenses' / project_name,
)

gnome.post_install(
  gtk_update_icon_cache: true,
)
