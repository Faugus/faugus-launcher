languages = [
  'de',
  'pl',
  'pt_BR',
]

foreach lang : languages
  install_data(
    lang / 'faugus-launcher.mo',
    lang / 'faugus-proton-manager.mo',
    lang / 'faugus-run.mo',
    install_dir: get_option('datadir') / 'share' / 'locale' / lang / 'LC_MESSAGES',
  )
endforeach
