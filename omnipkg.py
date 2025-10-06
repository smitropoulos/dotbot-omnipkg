from __future__ import annotations

import os
import subprocess
from shutil import which

import dotbot


class OmniPkg(dotbot.Plugin):
    # only support the omnipkg directive
    _mainDirective = "omnipkg"

    def __init__(self, context) -> None:  # noqa: ANN001
        super().__init__(context)
        pmf = PackageManagerFactory()
        self._packageManager = pmf.spawn()
        self.parser = DirectivesParser()

    def can_handle(self, directive: str) -> bool:
        # only allow the directives listed above
        return directive in (self._mainDirective)

    def handle(self, directive, data) -> bool:  # noqa: ANN001, ARG002
        directives = self.parser.parse(data)
        if directives.update is True:
            self._packageManager.update()
        return True

    def _printSubDirectiveError(self, sdName: str) -> None:
        self._log.error(f"Error executing {sdName} subdirective")

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


class Directives:
    """parse allowed directives
    example structure:

    - omnipkg:
        - install:
            - kitty
            - tmux
            - zsh
            - [ python3, python ]
            - neovim
      ]
    """

    update = False
    upgrade = False
    packages: list[Package] = []  # noqa: RUF012


class Package:
    def __init__(self, name: str, alts: list[str] | None = None) -> None:
        """Initializes the Package object."""
        self.package_name = name
        self.package_name_alt = alts if alts is not None else []

    def __repr__(self) -> str:
        """Provides a clean, readable string representation of the object."""
        if self.package_name_alt:
            return f"Package(name='{self.package_name}', alts={self.package_name_alt})"
        return f"Package(name='{self.package_name}')"


class DirectivesParser:
    _mainDirective = "omnipkg"
    _installSubDirective = "install"
    _updateSubDirective = "update"
    _upgradeSubDirective = "upgrade"

    def parse(self, data: list[any]) -> Directives:
        directives = Directives()
        for item in data:
            # 2. Handle simple string commands
            if isinstance(item, str):
                print(item)
                if item == self._updateSubDirective:
                    directives.update = True
                if item == self._upgradeSubDirective:
                    directives.upgrade = True

            elif isinstance(item, dict):
                for command, packages_data in item.items():
                    if command == self._installSubDirective:
                        package_objects = []
                        for package_item in packages_data:
                            # If it's a list, it has a primary name and alternatives
                            if isinstance(package_item, list):
                                pkg = Package(name=package_item[0], alts=package_item[1:])
                                package_objects.append(pkg)
                            # If it's a string, it's just a primary name
                            elif isinstance(package_item, str):
                                pkg = Package(name=package_item)
                                package_objects.append(pkg)
        print("Done parsing")


class PackageManager:
    """package manager interface"""

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
        print(f"Updating using {self._update_command}")
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
        {"executable": "brew", "pm": BrewPackageManager()},
        {"executable": "apt-get", "pm": AptPackageManager()},
        {"executable": "pacman", "pm": PacmanPackageManager()},
        {"executable": "dnf", "pm": DnfPackageManager()},
        {"executable": "zypper", "pm": ZypperPackageManager()},
    )

    def spawn(self) -> PackageManager:
        for pm_tuple in self.pms:
            if which(pm_tuple["executable"]) is not None:
                print("========================")
                print(pm_tuple["executable"])
                return pm_tuple["pm"]
        msg = "Not supported platform"
        raise RuntimeError(msg)
