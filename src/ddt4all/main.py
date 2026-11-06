import codecs
import json
import os
from pathlib import Path
import sys

from ddt4all.qt import widgets

from ddt4all.cli.cli_args_parser import build_parser
import ddt4all.core.ecu.ecu_database as ecu_db
import ddt4all.core.elm.elm as elm
from ddt4all.file_manager import (
    get_config_dir,
    get_json_dir,
    get_logs_dir,
    get_projects_path,
)
import ddt4all.generated.resources_rc  # noqa: F401
import ddt4all.options as options
from ddt4all.ui.main_window.main_widget import MainWidget
from ddt4all.ui.main_window.utils import (
    set_socket_timeout,
    set_theme_style
)
import ddt4all.version as version

_ = options.translator('ddt4all')

from ddt4all.qt import HAS_WEBENGINE, webengine as webkitwidgets

BASE_DIR = Path(__file__).resolve().parent
icons_base_dir = BASE_DIR / "resources" / "icons"


def load_this():
    try:
        with open(get_projects_path(), "r", encoding="UTF-8") as f:
            vehicles_loc = json.loads(f.read())
        ecu_db.addressing = vehicles_loc["projects"]["All"]["addressing"]
        # TODO: Review DoIP addressing mapping loaded from projects.json.
        ecu_db.doip_addressing = vehicles_loc["projects"]["All"]["DoIP"]
        elm.snat = vehicles_loc["projects"]["All"]["snat"]
        elm.snat_ext = vehicles_loc["projects"]["All"]["snat_ext"]
        elm.dnat = vehicles_loc["projects"]["All"]["dnat"]
        elm.dnat_ext = vehicles_loc["projects"]["All"]["dnat_ext"]
        return vehicles_loc
    except (FileNotFoundError, json.JSONDecodeError, KeyError) as e:
        print(_("resources/projects.json not found or invalid.") + f" Error: {e}")
        exit(-1) # TODO raise ?


def main(argv=None) -> int:

    parser = build_parser()
    args = parser.parse_args()

    # If subcommand : run then exit
    if hasattr(args, "handler"):
        result = args.handler(args)
        # Potential return code propagation
        raise SystemExit(result if isinstance(result, int) else 0)

    # For InnoSetup version.h auto generator
    if os.path.isdir('setup_tools/inno-win-setup'):
        try:
            with open("setup_tools/inno-win-setup/version.h", "w", encoding="UTF-8") as f:
                f.write(f'#define __appname__ "{version.__appname__}"\n')
                f.write(f'#define __author__ "{version.__author__}"\n')
                f.write(f'#define __copyright__ "{version.__copyright__}"\n')
                f.write(f'#define __version__ "{version.__version__}"\n')
                f.write(f'#define __email__ "{version.__email__}"\n')
                f.write(f'#define __codename__ "{version.__codename__}"\n')
                f.write(f'#define __status__ "{version.__status__}"')
        except (OSError, IOError) as e:
            print(_("Warning: Could not write version.h: %s") % e)

    try:
        sys.stdout = open(sys.stdout.fileno(), mode='w', encoding='utf8', buffering=1)
    except (OSError, ValueError):
        sys.stdout = codecs.getwriter('utf8')(sys.stdout)


    vehicles = load_this()

    # Always start offline: the user connects from the toolbar once ready
    options.simulation_mode = True
    options.socket_timeout = False

    app = widgets.QApplication(sys.argv)
    # Lets the desktop match the window to its ddt4all.desktop launcher/icon
    app.setDesktopFileName("ddt4all")

    try:
        with open(get_config_dir() / "config.json", "r", encoding="UTF-8") as f:
            configuration = json.loads(f.read())
        set_theme_style(app, 2 if configuration.get("dark") else 0)
        set_socket_timeout(1 if configuration.get("socket_timeout") else 0)
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        set_theme_style(app, 0)

    if os.path.exists(options.ecus_dir + '/eculist.xml'):
        print(_("Using custom DDT database"))

    Path(get_json_dir()).mkdir(parents=True, exist_ok=True)
    Path(get_logs_dir()).mkdir(parents=True, exist_ok=True)

    w = MainWidget(app, vehicles)
    options.main_window = w
    w.show()
    app.exec()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())