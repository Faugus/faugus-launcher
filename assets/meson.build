install_data(
  'faugus-banner.png',
  'faugus-notification.ogg',
)

install_data(
  'faugus-mono.svg',
  'faugus-battlenet.png',
  'faugus-ea.png',
  'faugus-epic-games.png',
  'faugus-ubisoft-connect.png',
  'faugus-rockstar.png',
  'faugus-wargaming.png',
  install_dir: get_option('datadir') / 'icons' / 'hicolor' / '256x256' / 'apps',
)

install_data(
  'faugus-add-symbolic.svg',
  'faugus-exit-symbolic.svg',
  'faugus-kill-symbolic.svg',
  'faugus-play-symbolic.svg',
  'faugus-settings-symbolic.svg',
  'faugus-stop-symbolic.svg',
  install_dir: get_option('datadir') / 'icons' / 'hicolor' / 'scalable' / 'actions',
)

icon_sizes = ['16', '32', '64', '128', '256']

foreach size : icon_sizes
  res = size + 'x' + size

  install_data(
    res / 'faugus-launcher.png',
    install_dir: get_option('datadir') / 'icons' / 'hicolor' / res / 'apps',
  )

  install_data(
    res / 'faugus-launcher.png',
    install_dir: get_option('datadir') / 'icons' / 'hicolor' / res / 'apps',
    rename: 'io.github.Faugus.faugus-launcher.png',
  )
endforeach
