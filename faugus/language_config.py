import locale

from faugus.path_manager import *

config_file_dir = PathManager.user_config('faugus-launcher/config.ini')

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
    if os.path.exists(config_file_dir):
        with open(config_file_dir, 'r') as f:
            for line in f:
                line = line.strip()
                if line.startswith('language='):
                    return line.split('=', 1)[1].strip()
    return None

lang = get_language_from_config()
if not lang:
    lang = get_system_locale()

LOCALE_DIR = (
    PathManager.system_data('locale')
    if os.path.isdir(PathManager.system_data('locale'))
    else os.path.join(os.path.dirname(__file__), 'locale')
)