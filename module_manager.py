import os
import webbrowser
from functools import partial

try:
    import shiboken2 as shiboken
    from PySide2 import QtWidgets, QtGui, QtCore
except:
    import shiboken6 as shiboken
    from PySide6 import QtWidgets, QtGui, QtCore
    
from maya import cmds
from maya import OpenMayaUI


# ----------------------CONSTANTS---------------------------------
MODULE_ARGUMENTS = [
    "MAYAVERSION",
    "PLATFORM",
    "LOCALE",
]
MAYA_ARGUMENTS = {
    "MAYAVERSION": cmds.about(version=True),
    "PLATFORM": cmds.about(operatingSystem=True),
    "LOCALE": cmds.about(uiLanguage=True),
}

MOD_EXTENSIONS = ("mod")  # lowercase only


# ----------------------UTILS---------------------------------

def get_main_window():
    """
    :return: Maya main window
    :rtype: QtWidgets.QMainWindow/None
    :raise RuntimeError: When the main window cannot be obtained.
    """
    ptr = OpenMayaUI.MQtUtil.mainWindow()
    ptr = int(ptr)
    if ptr:
        return shiboken.wrapInstance(ptr, QtWidgets.QMainWindow)

    raise RuntimeError("Failed to obtain a handle on the Maya main window.")


def get_icon_path(file_name):
    """
    Get an icon path based on file name. All paths in the XBMLANGPATH variable
    processed to see if the provided icon can be found.

    :param str file_name:
    :return: Icon path
    :rtype: str/None
    """
    for directory in os.environ["XBMLANGPATH"].split(os.pathsep):
        file_path = os.path.join(directory, file_name)
        if os.path.exists(file_path):
            return file_path.replace("\\", "/")


def divider(parent):
    """
    :param QtWidgets.QWidget parent:
    :rtype: QtWidgets.QFrame
    """
    line = QtWidgets.QFrame(parent)
    line.setFrameShape(QtWidgets.QFrame.HLine)
    line.setFrameShadow(QtWidgets.QFrame.Sunken)
    return line


def get_module_paths():
    """
    :return: Maya module paths
    :rtype: list[str]
    """
    return os.environ["MAYA_MODULE_PATH"].split(os.pathsep)


def get_module_file_paths():
    """
    :return: Maya module files
    :rtype: list[str]
    """
    # variable
    modules = []

    # loop module paths
    for path in get_module_paths():
        # make sure path exists, by default maya adds paths to the variable
        # that don't necessarily have to exist.
        if not os.path.exists(path):
            continue

        # extend modules
        modules.extend(
            [
                os.path.normpath(os.path.join(path, f))
                for f in os.listdir(path) or []
                if f.lower().endswith(MOD_EXTENSIONS) and not f.startswith("moduleManager")
            ]
        )

    # sort modules by file name
    modules.sort(key=lambda x: os.path.basename(x))

    return modules


def parse_module_line(line):
    """
    Parse the line of a module, the line needs to start with either a + or a -
    if this is not the case it means it is additional information that belongs
    to the module which is defined in the lines above this one. If that is the
    case None is returned.

    :param str line:
    :return: Module data
    :rtype: dict/None
    """
    # validate line
    if len(line) < 1 or line[0] not in {"+", "-"}:
        return

    # variable
    data = {}
    partitions = line.split()

    # copy partitions to loop and be able to remove from the original list
    # without messing with the loop
    for partition in reversed(partitions):
        for argument in MODULE_ARGUMENTS:
            if not partition.startswith(argument):
                continue

            data[argument] = partition[len(argument) + 1:]
            partitions.remove(partition)

    # validate length of partitions
    if len(partitions) != 4:
        return

    # add additional data
    for i, key in enumerate(["ENABLED", "NAME", "VERSION", "PATH"]):
        data[key] = partitions[i]

    return data


def filter_module_file(file_path):
    """
    :param str file_path:
    :return: Module data
    :rtype: generator
    """
    # read module file
    lines = read_module_file(file_path)

    # filter content
    for line in lines:
        data = parse_module_line(line)
        if not data:
            continue

        yield data


def read_module_file(file_path):
    """
    :param str file_path:
    :return: Module content
    :rtype: list
    """
    # read file
    with open(file_path, "r") as f:
        lines = f.readlines()
        lines = [x.strip() for x in lines]

    return lines


def update_module_file(file_path, state, data):
    """
    Update state of module, the module file gets read and the each line will
    be checked if it matches up with the data provided. If it does, that is
    the line that needs its state updated.

    :param str file_path:
    :param bool state:
    :param dict data:
    """
    # prepare state
    enabled = "+" if state else "-"

    # prepare data for comparison
    del data["ENABLED"]

    # read existing file
    content = []
    lines = read_module_file(file_path)

    for line in lines:
        # parse line
        line_data = parse_module_line(line)

        # validate line
        if line_data:
            # remove enabled for comparison
            del line_data["ENABLED"]

            # validate line data with provided data
            if data == line_data:
                content.append(enabled + line[1:])
                continue

        # store original line
        content.append(line)

    # add new line to content
    content = ["{}\n".format(c) for c in content]

    # write to file
    with open(file_path, "w") as f:
        f.writelines(content)

# ----------------------UI WIDGETS---------------------------------

FONT = QtGui.QFont()
FONT.setFamily("Consolas")
BOLT_FONT = QtGui.QFont()
BOLT_FONT.setFamily("Consolas")
# BOLT_FONT.setWeight(100)

# ICON_PATH = utils.get_icon_path("MM_icon.png")
FILE_ICON_PATH = ":/fileOpen.png"
ORANGE_STYLESHEET = "color: orange; text-align: left"


class MayaModuleDetailArgument(QtWidgets.QWidget):
    def __init__(self, parent, key, value):
        super(MayaModuleDetailArgument, self).__init__(parent)

        # create layout
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)

        # create key
        label = QtWidgets.QLabel(self)
        label.setFont(BOLT_FONT)
        label.setText(key)
        layout.addWidget(label)

        # create value
        label = QtWidgets.QLabel(self)
        label.setFont(FONT)
        label.setText(value)
        layout.addWidget(label)


class MayaModuleDetail(QtWidgets.QWidget):
    enabled_changed = QtCore.Signal(bool, dict)

    def __init__(self, parent, data):
        super(MayaModuleDetail, self).__init__(parent)

        # variables
        self._data = data
        self._path = self.get_path()
        scale_factor = self.logicalDpiX() / 96.0

        # create layout
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(7, 0, 7, 0)
        layout.setSpacing(3)

        # create enabled
        enabled_state = data.get("ENABLED") == "+"

        enabled = QtWidgets.QCheckBox(self)
        enabled.setChecked(enabled_state)
        enabled.setFont(BOLT_FONT)
        enabled.setText(data.get("NAME"))
        enabled.stateChanged.connect(self._emit_enabled_changed)
        enabled.setToolTip("Enable/Disable module")
        layout.addWidget(enabled)

        # create version
        version = QtWidgets.QLabel(self)
        version.setFont(FONT)
        version.setText(data.get("VERSION"))
        version.setFixedWidth(85 * scale_factor)
        layout.addWidget(version)

        # create maya version
        maya_version = MayaModuleDetailArgument(self, "Maya Version:", data.get("MAYAVERSION", "-"))
        layout.addWidget(maya_version)

        # create platform
        platform = MayaModuleDetailArgument(self, "Platform:", data.get("PLATFORM", "-"))
        layout.addWidget(platform)

        # create language
        language = MayaModuleDetailArgument(self, "Locale:", data.get("LOCALE", "-"))
        layout.addWidget(language)

        # create path
        browser = QtWidgets.QPushButton(self)
        browser.setEnabled(True if self.path else False)
        browser.setFlat(True)
        browser.setIcon(QtGui.QIcon(FILE_ICON_PATH))
        browser.setFixedSize(QtCore.QSize(18 * scale_factor, 18 * scale_factor))
        browser.released.connect(partial(webbrowser.open, self.path))
        browser.setToolTip("Open module content path with associated browser")
        layout.addWidget(browser)

    def _emit_enabled_changed(self, state):
        """
        :param bool state:
        """
        data = self.data.copy()
        self.enabled_changed.emit(state, data)

    # ------------------------------------------------------------------------

    @property
    def data(self):
        """
        :return: Data
        :rtype: dict
        """
        return self._data

    @property
    def path(self):
        """
        :return: Path
        :rtype: str
        """
        return self._path

    def get_path(self):
        """
        :return: Path to module
        :rtype: str
        """
        # get path
        path = self.data.get("PATH")

        # if the path is not an absolute path, use the parents path variable
        # to append the relative path to.
        if not os.path.isabs(path):
            path = os.path.join(os.path.dirname(self.parent().path), path)
            path = os.path.abspath(path)

        # open path
        return os.path.normpath(path)

    # ------------------------------------------------------------------------

    def is_compatible(self):
        """
        Validate the data against the current version of Maya ran, the
        platform it's ran on and it's language.

        :return: Validation state
        :rtype: bool
        """
        # validate data against current version of maya, the platform its ran
        for key, value in MAYA_ARGUMENTS.items():
            if key not in self.data:
                continue

            if self.data.get(key) != value:
                return False

        return True


class MayaModuleFileHeader(QtWidgets.QWidget):
    show_all_changed = QtCore.Signal(bool)

    def __init__(self, parent, path, show_all):
        super(MayaModuleFileHeader, self).__init__(parent)
        scale_factor = self.logicalDpiX() / 96.0

        # create layout
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)

        # create path
        browser = QtWidgets.QPushButton(self)
        browser.setFlat(True)
        browser.setIcon(QtGui.QIcon(FILE_ICON_PATH))
        browser.setFixedSize(QtCore.QSize(18 * scale_factor, 18 * scale_factor))
        browser.released.connect(partial(webbrowser.open, path))
        browser.setToolTip("Open module file with associated application")
        layout.addWidget(browser)

        # create text
        button = QtWidgets.QPushButton(self)
        button.setFlat(True)
        button.setFont(BOLT_FONT)
        button.setText(os.path.basename(path))
        button.setStyleSheet(ORANGE_STYLESHEET)
        button.setToolTip(path)
        button.released.connect(self.toggle_check_box)
        layout.addWidget(button)

        # create checkbox
        self._check_box = QtWidgets.QCheckBox(self)
        self._check_box.setFixedWidth(80 * scale_factor)
        self._check_box.setFont(FONT)
        self._check_box.setText("show all")
        self._check_box.setChecked(show_all)
        self._check_box.stateChanged.connect(self.show_all_changed.emit)
        layout.addWidget(self._check_box)

    # ------------------------------------------------------------------------

    def toggle_check_box(self):
        """
        Toggle the checked state of the checkbox.
        """
        state = self._check_box.isChecked()
        self._check_box.setChecked(not state)


class MayaModuleFile(QtWidgets.QFrame):
    def __init__(self, parent, path):
        super(MayaModuleFile, self).__init__(parent)

        # variables
        show_all = False
        self._path = path

        # set outline
        self.setFrameShape(QtWidgets.QFrame.Box)
        self.setFrameShadow(QtWidgets.QFrame.Sunken)

        # create layout
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(3, 3, 3, 3)
        layout.setSpacing(3)

        # create header
        header = MayaModuleFileHeader(self, path, show_all=show_all)
        header.show_all_changed.connect(self.manage_module_details)
        layout.addWidget(header)

        # create divider
        _divider = divider(self)
        layout.addWidget(_divider)

        # check permissions
        if not os.access(path, os.W_OK):
            self.setEnabled(False)

        # add module details
        self.add_module_details()
        self.manage_module_details(show_all)

    # ------------------------------------------------------------------------

    @property
    def path(self):
        """
        :return: Path
        :rtype: str
        """
        return self._path

    # ------------------------------------------------------------------------

    def manage_module_details(self, state):
        """
        Loop all widgets and either display all or filter the ones that are
        capable with the version of Maya that is ran.

        :param bool state:
        """
        for i in range(self.layout().count()):
            widget = self.layout().itemAt(i).widget()
            if not isinstance(widget, MayaModuleDetail):
                continue

            visible = True if state else widget.is_compatible()
            widget.setVisible(visible)

    def add_module_details(self):
        """
        Populate the widget with module data widgets, one for each module data
        line found in the module file.
        """
        for data in filter_module_file(self.path):
            mod = MayaModuleDetail(self, data)
            mod.enabled_changed.connect(self.update_module_file)
            self.layout().addWidget(mod)

    # ------------------------------------------------------------------------

    def update_module_file(self, state, data):
        """
        :param bool state:
        :param dict data:
        """
        update_module_file(self.path, state, data)


# ----------------------------------------------------------------------------


class MayaModuleManager(QtWidgets.QWidget):
    def __init__(self, parent):
        super(MayaModuleManager, self).__init__(parent)
        scale_factor = self.logicalDpiX() / 96.0
        
        # set ui
        self.setParent(parent)        
        self.setWindowFlags(QtCore.Qt.Window)
        self.setWindowTitle("Maya Module Manager")
        # self.setWindowIcon(QtGui.QIcon(ICON_PATH))
        self.resize(700 * scale_factor, 400 * scale_factor)

        # create container layout
        container = QtWidgets.QVBoxLayout(self)
        container.setContentsMargins(0, 0, 0, 0)
        container.setSpacing(3)

        # create scroll widget
        widget = QtWidgets.QWidget(self)
        self._layout = QtWidgets.QVBoxLayout(widget)
        self._layout.setContentsMargins(3, 3, 3, 3)
        self._layout.setSpacing(3)

        scroll = QtWidgets.QScrollArea(self)
        scroll.setFocusPolicy(QtCore.Qt.NoFocus)
        scroll.setWidgetResizable(True)
        scroll.setWidget(widget)
        container.addWidget(scroll)

        # add modules
        self.add_modules()

    # ------------------------------------------------------------------------

    def add_modules(self):
        """
        Populate the widget with module file widgets, one for each module file
        found.
        """
        for path in get_module_file_paths():
            mod = MayaModuleFile(self, path)
            self._layout.addWidget(mod)


def show(*args, **kwargs):
    parent = get_main_window()
    window = MayaModuleManager(parent)
    window.show()
    return window


# -------------------------- PLUGIN setup ----------------------------------
import sys
import maya.api.OpenMaya as om
import maya.cmds as cmds
import maya.mel as mel


# this plugin menu setup creates a single menu entry
# to create a menu under Windows/my-tool

# The below sample will create a new menu and menu-item: ToolsMenu/My cool tool
# MENU_NAME is the name maya assigns to a menu, this is not always the same as the visible label
# e.g. to parent to the default Maya menu 'Windows', use MENU_NAME="mainWindowMenu"
MENU_NAME = "mainWindowMenu"  # no spaces in names, use CamelCase. Used to find and parent to a menu.
# MENU_LABEL = "Tools"  # spaces are allowed in labels, only used when we create a new menu
MENU_ENTRY_LABEL = "Module Manager"

MENU_PARENT = "MayaWindow"  # do not change

__menu_entry_name = "" # Store generated menu item, used when unregister


def maya_useNewAPI():  # noqa
    """dummy method to tell Maya this plugin uses the Maya Python API 2.0"""
    pass


def loadMenu():
    """Setup the Maya menu, runs on plugin enable"""
    global __menu_entry_name

    # Maya builds its menus dynamically upon being accessed, so they don't exist if not yet accessed.
    # We force a menu build to allow parenting any new menu under a default Maya menu
    mel.eval("global string $gMainWindowMenu;buildViewMenu ( $gMainWindowMenu );")

    # if not cmds.menu(f"{MENU_PARENT}|{MENU_NAME}", exists=True):
    #     cmds.menu(MENU_NAME, label=MENU_LABEL, parent=MENU_PARENT)
    __menu_entry_name = cmds.menuItem(label=MENU_ENTRY_LABEL, command=show, parent=MENU_NAME)


def unloadMenuItem():
    """Remove the created Maya menu entry, runs on plugin disable"""
    if cmds.menu(f"{MENU_PARENT}|{MENU_NAME}", exists=True):
        menu_long_name = f"{MENU_PARENT}|{MENU_NAME}"
        # Check if the menu item exists; if it does, delete it
        if cmds.menuItem(__menu_entry_name, exists=True):
            cmds.deleteUI(__menu_entry_name, menuItem=True)
        # Check if the menu is now empty; if it is, delete the menu
        if not cmds.menu(menu_long_name, query=True, itemArray=True):
            cmds.deleteUI(menu_long_name, menu=True)


# =============================== Plugin (un)load ===========================================
def initializePlugin(plugin):
    loadMenu()


def uninitializePlugin(plugin):
    unloadMenuItem()
