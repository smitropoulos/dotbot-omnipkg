import os
from shutil import which
import subprocess
import sys

import dotbot


class OmniPkg(dotbot.Plugin):
    # only support the omnipkg directive
    _mainDirective = "omnipkg"

    # omnipkg directive should include subdirectives underneath it as such
    _installSubDirective = "install"
    _updateSubDirective = "update"
    _upgradeSubDirective = "upgrade"

    # The name of the package manager that has been found
    _packageManagerName = ""

    # The name of the platform
    _platformName = ""

    # The lookup name in optional package dictionaries
    _dictLookup = ""
    _dictLookupElse = "else"
    _dictLookupRequireGUI = "require_gui"

    # commands are setup based on the platform and installed package manager
    _installCommand = ""
    _updateCommand = ""
    _upgradeCommand = ""

    # Command used to check that the package exists before installing it
    _existsCheck = ""

    # command is installed already
    _installedCheck = ""

    # flag for if a gui is installed. Default to True, only checked if on linux
    _guiInstalled = True

    def __init__(self, context) -> None:
        super().__init__(context)
        # here we setup the commands based on whether linux or macos is
        # installed.
        # if macos is installed then we try to setup with brew
        # if linux is installed then we select a package manager
        # and use that instead
        if sys.platform == "linux" or sys.platform == "linux2":
            self._setupLinux()
        elif sys.platform == "darwin":
            self._setupMacOS()

    def can_handle(self, directive):
        # only allow the directives listed above
        return directive in (self._mainDirective)

    def handle(self, directive, data):
        # first process the subdirectives then run each

        # for each item in data, identify the sub directive and get the data
        # for the sub directive
        _doUpdate = False
        _updateStatus = True

        _doUpgrade = False
        _upgradeStatus = True

        _installData = []
        _installStatus = True

        for sd in data:
            if isinstance(sd, str):
                if sd == self._updateSubDirective:
                    _doUpdate = True
                elif sd == self._upgradeSubDirective:
                    _doUpgrade = True
            elif isinstance(sd, object) and self._installSubDirective in sd:
                _installData = sd[self._installSubDirective]

        # execute the processed sub directives and report any errors but
        # continue for each sub directive
        if _doUpdate:
            _updateStatus = self._doUpdate()
            if not _updateStatus:
                self._printSubDirectiveError(self._updateSubDirective)

        _installStatus = self._doInstall(_installData)
        if not _installStatus:
            self._printSubDirectiveError(self._installSubDirective)

        if _doUpgrade:
            _upgradeStatus = self._doUpgrade()
            if not _upgradeStatus:
                self._printSubDirectiveError(self._upgradeSubDirective)

        return _updateStatus and _installStatus and _upgradeStatus

    def _printSubDirectiveError(self, sdName: str) -> None:
        self._log.error(f"Error executing {sdName} subdirective")

    def _setupMacOS(self) -> None:
        self._platformName = "mac"
        self._setupBrew()

    def _setupLinux(self) -> None:
        self._platformName = "linux"

        # check if gui is installed on this linux
        self._guiInstalled = os.getenv("XDG_CURRENT_DESKTOP") is not None

        # check the package manager that is installed and use that
        # the following are the supported package managers for now
        # name, dict lookup, file, setup function
        managers = [
            ("apt-get", "apt", "/etc/debian_version", "_setupAptGet"),
            ("pacman", "pac", "/etc/arch-release", "_setupPacman"),
            ("dnf", "dnf", "/etc/redhat-release", "_setupDnf"),
        ]
        self._selectPackageManager(managers)

    def _selectPackageManager(self, packageManagers) -> None:
        for name, lookup, file, func in packageManagers:
            if os.path.exists(file):
                # set the package manager name and run the setup function
                self._packageManagerName = name
                self._dictLookup = lookup
                eval("self." + func + "()")
                break

    def _setupBrew(self) -> None:
        self._packageManagerName = "brew"
        self._dictLookup = self._packageManagerName

        # add a brew installation if not already installed
        self._installCommand = "brew install"
        self._existsCheck = "brew search /^$PKG_NAME$/"
        self._upgradeCommand = "brew upgrade"

    def _setupAptGet(self) -> None:
        self._installCommand = "sudo apt-get install -y"
        self._existsCheck = "apt-cache show $PKG_NAME"
        self._updateCommand = "sudo apt-get update"
        self._upgradeCommand = "sudo apt-get dist-upgrade -y"

    def _setupPacman(self) -> None:
        baseCommand = "sudo pacman --noconfirm %s"
        self._installCommand = baseCommand % "-S"
        self._existsCheck = "pacman -Si $PKG_NAME"
        self._installedCheck = "pacman -Q $PKG_NAME"
        self._updateCommand = baseCommand % "-Syy"
        self._upgradeCommand = baseCommand % "-Syu"

    def _setupDnf(self) -> None:
        self._installCommand = "sudo dnf install -y"
        self._existsCheck = "dnf list $PKG_NAME"
        self._updateCommand = "sudo dnf check-update"
        self._upgradeCommand = "sudo dnf upgrade -y"

    def _doInstall(self, pkgList):
        if self._installCommand != "":
            # append the package to the install command and run the command
            success = True
            for pkg in pkgList:
                if isinstance(pkg, str):
                    isinstalled = self._pkgIsInstalled(pkg)
                    if isinstalled:
                        self._log.info(f"Package {pkg} is already installed. Skipping")
                        continue
                    self._log.info(f"Installing package: {pkg}")
                    exists = self._pkgExists(pkg)
                    existsInDict = True
                    requireGUI = False
                elif isinstance(pkg, list):
                    self._log.info(f"Selecting package from {pkg}")
                    exists, pkg = self._getPkgNameFromList(pkg)
                    existsInDict = True
                    requireGUI = False
                    if exists:
                        self._log.info(f"Found package: {pkg} - Installing")
                elif isinstance(pkg, dict):
                    self._log.info(f"Selecting optional package from {pkg}")
                    existsInDict, exists, requireGUI, pkg, directive = self._getPkgNameFromDict(
                        pkg
                    )
                    if exists and not (requireGUI and not self._guiInstalled):
                        self._log.info(f"Found package: {pkg} for {directive} - Installing")
                else:
                    # invalid data
                    # this should be handled above the plugin level
                    msg = "Invalid data given to omnipkg-install"
                    raise TypeError(msg)

                # first check that item exists in data (only relevant for dictionary data)
                if not existsInDict:
                    self._log.lowinfo(
                        f"Skipping installation as no package specified for {self._packageManagerName} or {self._platformName}"
                    )
                    # otherwise skip if package doesn't exist
                elif not exists:
                    self._log.lowinfo("Skipping installation as package does not exist")
                elif requireGUI and not self._guiInstalled:
                    self._log.lowinfo("Skipping installation as package requires an installed GUI")
                else:
                    cmd = f"{self._installCommand} {pkg}"
                    result = self.run_in_shell(cmd)
                    if not result:
                        success = False  # if one fails we still continue
                        self._log.warning(f"Package {pkg} failed to install")

            return success
        # there should always be an install command
        return False

    def _doUpdate(self) -> bool:
        if self._updateCommand != "":
            self._log.info(f"Begin Update <{self._updateCommand}>")
            return self.run_in_shell(self._updateCommand)
        # there doesn't have to be an update command
        return True

    def _doUpgrade(self) -> bool:
        if self._upgradeCommand != "":
            self._log.info(f"Begin Upgrade <{self._upgradeCommand}>")
            return self.run_in_shell(self._upgradeCommand, silent=False)
        # there doesn't have to be an upgrade command
        return True

    def _pkgExists(self, pkg) -> bool:
        if self._existsCheck != "":
            cmd = self._existsCheck.replace("$PKG_NAME", pkg)
            return self.run_in_shell(cmd)
        # assume the package exists if no check
        return True

    def _pkgIsInstalled(self, pkg: str) -> bool:
        if self._installedCheck != "":
            cmd = self._installedCheck.replace("$PKG_NAME", pkg)
            return self.run_in_shell(cmd)
        # assume the package is not installed if no check provided
        return True

    def _getPkgNameFromList(self, pkgList):
        for pkg in pkgList:
            if self._pkgExists(pkg):
                return (True, pkg)

        return (False, "")

    def _getPkgNameFromDict(self, pkgDict):
        # check if require_gui flag is set to true but only use it if platform
        # is linux
        if self._platformName == "linux" and self._dictLookupRequireGUI in pkgDict:
            requireGUI = pkgDict[self._dictLookupRequireGUI]
        else:
            requireGUI = False

        # first check that there is an item for the current package manager
        # otherwise check for a platform directive (linux or mac)
        # otherwise check for an else directive
        # otherwise we don't install for this package
        if self._dictLookup in pkgDict:
            pkg = pkgDict[self._dictLookup]
            return (True, self._pkgExists(pkg), requireGUI, pkg, self._dictLookup)
        if self._platformName in pkgDict:
            pkg = pkgDict[self._platformName]
            return (True, self._pkgExists(pkg), requireGUI, pkg, self._platformName)
        if self._dictLookupElse in pkgDict:
            pkg = pkgDict[self._dictLookupElse]
            return (True, self._pkgExists(pkg), requireGUI, pkg, self._dictLookupElse)
        return (False, False, requireGUI, None, None)

    def run_in_shell(self, cmd: str, *, silent: bool = True) -> bool:
        with open(os.devnull, "w") as devnull:
            if silent:
                stdout = stderr = devnull
            else:
                stdout = stderr = None

            result = subprocess.call(
                cmd, shell=True, stdout=stdout, stderr=stderr, cwd=self._context.base_directory()
            )
            return result == 0
        return True

    def run_in_shellBrew(self) -> None:
        # install brew
        link = "https://raw.githubusercontent.com/Homebrew/install/master/install.sh"
        cmd = f"""hash brew || /bin/bash -c "$(curl -fsSL {link})";
              brew update"""
        self.run_in_shell(cmd)


class PackageManager:
    def setup(self) -> None:
        """if necessary setup the package manager"""

    def package_install(self, package: str) -> bool:
        """install a package

        Returns:
            success
        """

    def update(self) -> None:
        """update the caches"""

    def package_exists(self, package: str) -> bool:
        """check if the package exists in the remote

        Returns:
            success
        """

    def package_is_installed(self, package: str) -> bool:
        """checks if the packages is already installed

        Returns:
            true if installed, false if not
        """


def run_in_shell(cmd: str, *, silent: bool = True) -> bool:
    if silent:
        stdout = stderr = subprocess.DEVNULL
    else:
        stdout = stderr = None

    result = subprocess.call(cmd, shell=True, stdout=stdout, stderr=stderr)
    return result == 0


class PacmanPackageManager(PackageManager):
    def __init__(self) -> None:
        self._update_command = "sudo pacman --sync --refresh --refresh"
        self._package_exists_command = "pacman -Si"  # plus pkg
        self._package_is_installed_command = "pacman -Qe"  # plus pkg
        self._package_install_command = "pacman -S --noconfirm --needed"  # plus pkg

    def update(self) -> None:
        run_in_shell(self._update_command, silent=True)

    def package_exists(self, package: str) -> bool:
        # regex here be specific
        cmd = self._package_exists_command + " ^" + package + "$"
        return run_in_shell(cmd, silent=False)

    def package_is_installed(self, package: str) -> bool:
        cmd = self._package_is_installed_command + " " + package
        return run_in_shell(cmd, silent=False)

    def package_install(self, package: str) -> bool:
        cmd = self._package_install_command + " " + package
        return run_in_shell(cmd, silent=False)


class AptPackageManager(PackageManager):
    def __init__(self) -> None:
        self._update_command = "DEBIAN_FRONTEND=noninteractive sudo apt-get update"
        self._package_exists_command = "DEBIAN_FRONTEND=noninteractive apt-cache show"  # plus pkg
        self._package_is_installed_command = "dpkg -s"  # plus pkg
        self._package_install_command = (
            "DEBIAN_FRONTEND=noninteractive sudo apt-get install -y"  # plus pkg
        )

    def update(self) -> None:
        run_in_shell(self._update_command, silent=True)

    def package_exists(self, package: str) -> bool:
        cmd = self._package_exists_command + " " + package
        return run_in_shell(cmd, silent=False)

    def package_is_installed(self, package: str) -> bool:
        cmd = self._package_is_installed_command + " " + package
        return run_in_shell(cmd, silent=False)

    def package_install(self, package: str) -> bool:
        cmd = self._package_install_command + " " + package
        return run_in_shell(cmd, silent=False)


class BrewPackageManager(PackageManager):
    def __init__(self) -> None:
        self._update_command = "brew update"
        self._package_exists_command = "brew info"  # plus pkg
        self._package_is_installed_command = "brew list"  # plus pkg
        self._package_install_command = "brew install"  # plus pkg

    def update(self) -> None:
        run_in_shell(self._update_command, silent=True)

    def package_exists(self, package: str) -> bool:
        cmd = self._package_exists_command + " " + package
        return run_in_shell(cmd, silent=False)

    def package_is_installed(self, package: str) -> bool:
        cmd = self._package_is_installed_command + " " + package
        return run_in_shell(cmd, silent=False)

    def package_install(self, package: str) -> bool:
        cmd = self._package_install_command + " " + package
        return run_in_shell(cmd, silent=False)


class DnfPackageManager(PackageManager):
    def __init__(self) -> None:
        self._update_command = "sudo dnf makecache"
        self._package_exists_command = "dnf list available"  # plus pkg
        self._package_is_installed_command = "dnf list installed"  # plus pkg
        self._package_install_command = "sudo dnf install -y"  # plus pkg

    def update(self) -> None:
        run_in_shell(self._update_command, silent=True)

    def package_exists(self, package: str) -> bool:
        cmd = self._package_exists_command + " " + package
        return run_in_shell(cmd, silent=False)

    def package_is_installed(self, package: str) -> bool:
        cmd = self._package_is_installed_command + " " + package
        return run_in_shell(cmd, silent=False)

    def package_install(self, package: str) -> bool:
        cmd = self._package_install_command + " " + package
        return run_in_shell(cmd, silent=False)


class ZypperPackageManager(PackageManager):
    def __init__(self) -> None:
        self._update_command = "sudo zypper refresh"
        self._package_exists_command = "zypper search --match-exact"  # plus pkg
        self._package_is_installed_command = "zypper se --installed-only --match-exact"  # plus pkg
        self._package_install_command = "sudo zypper install --non-interactive"  # plus pkg

    def update(self) -> None:
        run_in_shell(self._update_command, silent=True)

    def package_exists(self, package: str) -> bool:
        cmd = self._package_exists_command + " " + package
        return run_in_shell(cmd, silent=False)

    def package_is_installed(self, package: str) -> bool:
        cmd = self._package_is_installed_command + " " + package
        return run_in_shell(cmd, silent=False)

    def package_install(self, package: str) -> bool:
        cmd = self._package_install_command + " " + package
        return run_in_shell(cmd, silent=False)


class PackageManagerFactory:
    pms = (
        {"executable": "brew", "pm": BrewPackageManager},
        {"executable": "apt-get", "pm": AptPackageManager},
        {"executable": "pacman", "pm": PacmanPackageManager},
        {"executable": "dnf", "pm": DnfPackageManager},
        {"executable": "zypper", "pm": ZypperPackageManager},
    )

    def spawn(self) -> PackageManager:
        for pm_tuple in self.pms:
            if which(pm_tuple["executable"]) is not None:
                return pm_tuple["pm"]
        msg = "Not supported platform"
        raise RuntimeError(msg)
