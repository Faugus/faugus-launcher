import json
import locale
import gettext

from faugus.path_manager import *


def get_system_locale():
    lang = os.environ.get('LANG') or os.environ.get('LC_MESSAGES')
    if lang:
        return lang.split('.')[0]

    try:
        loc = locale.getdefaultlocale()[0]
        if loc:
            return loc
    except Exception:
        pass

    return 'en_US'


def get_language_from_config():
    if os.path.exists(CONFIG_FILE_DIR):
        try:
            with open(CONFIG_FILE_DIR, 'r', encoding='utf-8') as f:
                return json.load(f).get('language')
        except (OSError, json.JSONDecodeError):
            return None
    return None


lang = get_language_from_config()
if not lang:
    lang = get_system_locale()

_SOURCE_LANGUAGES_DIR = os.path.join(FAUGUS_SOURCE_ROOT, 'languages')

LOCALE_DIR = (
    _SOURCE_LANGUAGES_DIR
    if os.path.isdir(_SOURCE_LANGUAGES_DIR)
    else PathManager.system_data('locale')
)


def find_mo_file(locale_dir, lang_code, domain):
    for candidate in (
        os.path.join(locale_dir, lang_code, 'LC_MESSAGES', f'{domain}.mo'),
        os.path.join(locale_dir, lang_code, f'{domain}.mo'),
    ):
        if os.path.isfile(candidate):
            return candidate
    return None


def setup_gettext(domain):
    mo_path = find_mo_file(LOCALE_DIR, lang, domain) if lang else None
    if mo_path:
        with open(mo_path, 'rb') as f:
            translation = gettext.GNUTranslations(f)
        translation.install()
        return translation.gettext
    gettext.install(domain, localedir=LOCALE_DIR)
    return gettext.gettext