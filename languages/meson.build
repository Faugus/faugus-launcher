languages = fs.read('language-code').splitlines()

foreach lang : languages
  lang = lang.split()[0]
  if fs.exists(lang)
    install_data(
      lang / 'faugus-launcher.mo',
      install_dir: get_option('localedir') / lang / 'LC_MESSAGES',
    )
  endif
endforeach
