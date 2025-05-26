languages = fs.read('language-code').splitlines()

foreach lang : languages
  lang = lang.split(' ')[0]
  if fs.exists(lang)
    install_data(
      lang / 'faugus-launcher.mo',
      lang / 'faugus-proton-manager.mo',
      lang / 'faugus-run.mo',
      install_dir: get_option('datadir') / 'share' / 'locale' / lang / 'LC_MESSAGES',
    )
  endif
endforeach
