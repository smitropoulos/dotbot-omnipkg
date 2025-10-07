from __future__ import annotations

import subprocess
from shutil import which

import dotbot

omnipkg_silent_toggle = False


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

        for install_entry in directives.install_entries:
            print(install_entry)
            filters = install_entry.filters
            if filters is not None:
                print(f"Filters found {filters}")
            install_success = self._packageManager.package_install(install_entry.package_name)
            # try alternative names if present
            if not install_success and len(install_entry.package_name_alt) != 0:
                for alt_name in install_entry.package_name_alt:
                    install_success = self._packageManager.package_install(alt_name)
            if not install_success:
                # instead of bailing, continue and log this
                self._log.error(f"Error installing {install_entry}")
            else:
                self._log.info(f"Done installing {install_entry}")

        self._log.info("Omnipkg done")
        return True


class Directives:
    """Holds all parsed directives from the configuration."""

    update: bool = False
    install_entries: list[InstallEntry] = []  # noqa: RUF012


class InstallEntry:
    def __init__(
        self,
        name: str | None = None,
        alts: list[str] | None = None,
        filters: list[str] | None = None,
    ) -> None:
        """Initializes the Package object."""
        self.package_name = name if name is not None else ""
        self.package_name_alt = alts if alts is not None else []
        self.filters = filters if alts is not None else []

    def __repr__(self) -> str:
        """Provides a clean, readable string representation."""
        name_str = self.package_name
        if self.package_name_alt:
            name_str += f" (alts: {', '.join(self.package_name_alt)})"

        filter_str = ""
        if self.filters:
            filter_str = f" [filters: {', '.join(self.filters)}]"

        return f"InstallEntry('{name_str}'{filter_str})"


class DirectivesParser:
    _mainDirective = "omnipkg"
    _installSubDirective = "install"
    _updateSubDirective = "update"

    def _parse_package_attributes(self, entry: InstallEntry, attributes: dict | None) -> None:
        """Helper to populate an InstallEntry from an attributes dictionary."""
        if attributes is None:
            return

        # Safely get alt_name and ensure it's a list
        alt_name = attributes.get("alt_name")
        if isinstance(alt_name, str):
            entry.package_name_alt = [alt_name]
        elif isinstance(alt_name, list):
            entry.package_name_alt = alt_name

        # Safely get filter and ensure it's a list
        package_filter = attributes.get("filter")
        if isinstance(package_filter, str):
            entry.filters = [package_filter]
        elif isinstance(package_filter, list):
            entry.filters = package_filter

    def _parse_install_list(self, packages_data: list) -> list[InstallEntry]:
        """Parses a list of packages containing mixed types (strings and dicts)."""
        parsed_entries = []
        for item in packages_data:
            # Handle simple package names like "lsd"
            if isinstance(item, str):
                entry = InstallEntry(name=item)
                parsed_entries.append(entry)

            # Handle complex package entries like {"neovim": {...}}
            elif isinstance(item, dict):
                # Extract the name (key) and attributes (value)
                for name, attributes in item.items():
                    entry = InstallEntry(name=name)
                    self._parse_package_attributes(entry, attributes)
                    parsed_entries.append(entry)

        return parsed_entries

    def parse(self, data: list) -> Directives:
        """The main entry point for parsing the configuration list."""
        directives = Directives()

        for item in data:
            if isinstance(item, str) and item == self._updateSubDirective:
                directives.update = True

            elif isinstance(item, dict) and self._installSubDirective in item:
                packages_list = item[self._installSubDirective]
                # Delegate the mixed-type list to the helper
                install_entries = self._parse_install_list(packages_list)
                directives.install_entries.extend(install_entries)

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
        run_in_shell(self._update_command, silent=omnipkg_silent_toggle)

    def package_exists(self, package: str) -> bool:
        # regex here be specific
        cmd = self._package_exists_command + " ^" + package + "$"
        return run_in_shell(cmd, silent=omnipkg_silent_toggle)

    def package_is_installed(self, package: str) -> bool:
        cmd = self._package_is_installed_command + " " + package
        return run_in_shell(cmd, silent=omnipkg_silent_toggle)

    def package_install(self, package: str) -> bool:
        cmd = self._package_install_command + " " + package
        return run_in_shell(cmd, silent=omnipkg_silent_toggle)


class AptPackageManager(PackageManager):
    def __init__(self) -> None:
        self._update_command = "DEBIAN_FRONTEND=noninteractive sudo apt-get update"
        self._package_exists_command = "DEBIAN_FRONTEND=noninteractive apt-cache show"  # plus pkg
        self._package_is_installed_command = "dpkg -s"  # plus pkg
        self._package_install_command = (
            "DEBIAN_FRONTEND=noninteractive sudo apt-get install -y"  # plus pkg
        )

    def update(self) -> None:
        run_in_shell(self._update_command, silent=omnipkg_silent_toggle)

    def package_exists(self, package: str) -> bool:
        cmd = self._package_exists_command + " " + package
        return run_in_shell(cmd, silent=omnipkg_silent_toggle)

    def package_is_installed(self, package: str) -> bool:
        cmd = self._package_is_installed_command + " " + package
        return run_in_shell(cmd, silent=omnipkg_silent_toggle)

    def package_install(self, package: str) -> bool:
        cmd = self._package_install_command + " " + package
        return run_in_shell(cmd, silent=omnipkg_silent_toggle)


class BrewPackageManager(PackageManager):
    def __init__(self) -> None:
        self._update_command = "brew update"
        self._package_exists_command = "brew info"  # plus pkg
        self._package_is_installed_command = "brew list"  # plus pkg
        self._package_install_command = "brew install"  # plus pkg

    def update(self) -> None:
        run_in_shell(self._update_command, silent=omnipkg_silent_toggle)

    def package_exists(self, package: str) -> bool:
        cmd = self._package_exists_command + " " + package
        return run_in_shell(cmd, silent=omnipkg_silent_toggle)

    def package_is_installed(self, package: str) -> bool:
        cmd = self._package_is_installed_command + " " + package
        return run_in_shell(cmd, silent=omnipkg_silent_toggle)

    def package_install(self, package: str) -> bool:
        cmd = self._package_install_command + " " + package
        return run_in_shell(cmd, silent=omnipkg_silent_toggle)


class DnfPackageManager(PackageManager):
    def __init__(self) -> None:
        self._update_command = "sudo dnf makecache"
        self._package_exists_command = "dnf list available"  # plus pkg
        self._package_is_installed_command = "dnf list installed"  # plus pkg
        self._package_install_command = "sudo dnf install -y"  # plus pkg

    def update(self) -> None:
        run_in_shell(self._update_command, silent=omnipkg_silent_toggle)

    def package_exists(self, package: str) -> bool:
        cmd = self._package_exists_command + " " + package
        return run_in_shell(cmd, silent=omnipkg_silent_toggle)

    def package_is_installed(self, package: str) -> bool:
        cmd = self._package_is_installed_command + " " + package
        return run_in_shell(cmd, silent=omnipkg_silent_toggle)

    def package_install(self, package: str) -> bool:
        cmd = self._package_install_command + " " + package
        return run_in_shell(cmd, silent=omnipkg_silent_toggle)


class ZypperPackageManager(PackageManager):
    def __init__(self) -> None:
        self._update_command = "sudo zypper refresh"
        self._package_exists_command = "zypper search --match-exact"  # plus pkg
        self._package_is_installed_command = "zypper se --installed-only --match-exact"  # plus pkg
        self._package_install_command = "sudo zypper install --non-interactive"  # plus pkg

    def update(self) -> None:
        run_in_shell(self._update_command, silent=omnipkg_silent_toggle)

    def package_exists(self, package: str) -> bool:
        cmd = self._package_exists_command + " " + package
        return run_in_shell(cmd, silent=omnipkg_silent_toggle)

    def package_is_installed(self, package: str) -> bool:
        cmd = self._package_is_installed_command + " " + package
        return run_in_shell(cmd, silent=omnipkg_silent_toggle)

    def package_install(self, package: str) -> bool:
        cmd = self._package_install_command + " " + package
        return run_in_shell(cmd, silent=omnipkg_silent_toggle)


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
