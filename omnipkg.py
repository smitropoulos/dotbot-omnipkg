from __future__ import annotations

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

        for pkg in directives.packages:
            install_success = self._packageManager.package_install(pkg.package_name)
            # try alternative names if present
            if not install_success and len(pkg.package_name_alt) != 0:
                for alt_name in pkg.package_name_alt:
                    self._packageManager.package_install(alt_name)
            if not install_success:
                # instead of bailing, continue and log this
                self._log.error(f"Error installing {pkg}")
            else:
                self._log.info(f"Done installing {pkg}")

        self._log.info("Omnipkg done")
        return True


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
    packages: list[Package] = []  # noqa: RUF012


class Package:
    def __init__(self, name: str, alts: list[str] | None = None) -> None:
        """Initializes the Package object."""
        self.package_name = name
        self.package_name_alt = alts if alts is not None else []

    def __repr__(self) -> str:
        """Joins the original and alternative names with a slash."""
        # Create a new list starting with the original name
        all_names = [self.package_name]

        # Add the list of alternative names
        all_names.extend(self.package_name_alt)

        # Join all names
        return " || ".join(all_names)


class DirectivesParser:
    _mainDirective = "omnipkg"
    _installSubDirective = "install"
    _updateSubDirective = "update"

    def parse(self, data: list[any]) -> Directives:
        directives = Directives()
        for item in data:
            # 2. Handle simple string commands
            if isinstance(item, str):
                if item == self._updateSubDirective:
                    directives.update = True

            elif isinstance(item, dict):
                for command, packages_data in item.items():
                    if command == self._installSubDirective:
                        for package_item in packages_data:
                            # If it's a list, it has a primary name and alternatives
                            if isinstance(package_item, list):
                                pkg = Package(name=package_item[0], alts=package_item[1:])
                                directives.packages.append(pkg)
                            # If it's a string, it's just a primary name
                            elif isinstance(package_item, str):
                                pkg = Package(name=package_item)
                                directives.packages.append(pkg)
        return directives


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
        self._package_install_command = "sudo pacman -S --noconfirm --needed"  # plus pkg

    def update(self) -> None:
        run_in_shell(self._update_command, silent=True)

    def package_exists(self, package: str) -> bool:
        # regex here be specific
        cmd = self._package_exists_command + " ^" + package + "$"
        return run_in_shell(cmd, silent=True)

    def package_is_installed(self, package: str) -> bool:
        cmd = self._package_is_installed_command + " " + package
        return run_in_shell(cmd, silent=True)

    def package_install(self, package: str) -> bool:
        cmd = self._package_install_command + " " + package
        return run_in_shell(cmd, silent=True)


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
        return run_in_shell(cmd, silent=True)

    def package_is_installed(self, package: str) -> bool:
        cmd = self._package_is_installed_command + " " + package
        return run_in_shell(cmd, silent=True)

    def package_install(self, package: str) -> bool:
        cmd = self._package_install_command + " " + package
        return run_in_shell(cmd, silent=True)


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
        return run_in_shell(cmd, silent=True)

    def package_is_installed(self, package: str) -> bool:
        cmd = self._package_is_installed_command + " " + package
        return run_in_shell(cmd, silent=True)

    def package_install(self, package: str) -> bool:
        cmd = self._package_install_command + " " + package
        return run_in_shell(cmd, silent=True)


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
        return run_in_shell(cmd, silent=True)

    def package_is_installed(self, package: str) -> bool:
        cmd = self._package_is_installed_command + " " + package
        return run_in_shell(cmd, silent=True)

    def package_install(self, package: str) -> bool:
        cmd = self._package_install_command + " " + package
        return run_in_shell(cmd, silent=True)


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
        return run_in_shell(cmd, silent=True)

    def package_is_installed(self, package: str) -> bool:
        cmd = self._package_is_installed_command + " " + package
        return run_in_shell(cmd, silent=True)

    def package_install(self, package: str) -> bool:
        cmd = self._package_install_command + " " + package
        return run_in_shell(cmd, silent=True)


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
                return pm_tuple["pm"]
        msg = "Not supported platform"
        raise RuntimeError(msg)
