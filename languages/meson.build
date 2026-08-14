languages = fs.read('language-code').splitlines()

lang_list = []
foreach lang : languages
  lang = lang.split()[0]
  if fs.exists(lang / 'faugus-launcher.po')
    lang_list += lang
  endif
endforeach

meson.add_install_script(
  find_program('compile-translations.sh'),
  get_option('localedir'),
  lang_list,
)
