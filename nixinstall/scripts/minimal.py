from pathlib import Path

from nixinstall.default_profiles.minimal import MinimalProfile
from nixinstall.lib.args import nixos_config_handler
from nixinstall.lib.configuration import ConfigurationOutput
from nixinstall.lib.disk.disk_menu import DiskLayoutConfigurationMenu
from nixinstall.lib.disk.filesystem import FilesystemHandler
from nixinstall.lib.installer import Installer
from nixinstall.lib.models import Bootloader
from nixinstall.lib.models.profile_model import ProfileConfiguration
from nixinstall.lib.models.users import Password, User
from nixinstall.lib.output import debug, error, info
from nixinstall.lib.profile.profiles_handler import profile_handler
from nixinstall.tui import Tui


def perform_installation(mountpoint: Path) -> None:
	config = nixos_config_handler.config

	if not config.disk_config:
		error('No disk configuration provided')
		return

	disk_config = config.disk_config
	mountpoint = disk_config.mountpoint if disk_config.mountpoint else mountpoint

	with Installer(
		mountpoint,
		disk_config,
		kernels=config.kernels,
	) as installation:
		# Strap in the base system, add a boot loader and configure
		# some other minor details as specified by this profile and user.
		installation.mount_ordered_layout()
		installation.minimal_installation()
		installation.set_hostname('minimal-arch')
		installation.add_bootloader(Bootloader.Systemd)

		network_config = config.network_config

		if network_config:
			network_config.install_network_config(
				installation,
				config.profile_config,
			)

		installation.add_additional_packages(['nano', 'wget', 'git'])

		profile_config = ProfileConfiguration(MinimalProfile())
		profile_handler.install_profile_config(installation, profile_config)

		user = User('devel', Password(plaintext='devel'), False)
		installation.create_users(user)

	# Once this is done, we output some useful information to the user
	# And the installation is complete.
	info('There are two new accounts in your installation after reboot:')
	info(' * root (password: airoot)')
	info(' * devel (password: devel)')


def _minimal() -> None:
	with Tui():
		disk_config = DiskLayoutConfigurationMenu(disk_layout_config=None).run()
		nixos_config_handler.config.disk_config = disk_config

	config = ConfigurationOutput(nixos_config_handler.config)
	config.write_debug()
	config.save()

	if nixos_config_handler.args.dry_run:
		exit(0)

	if not nixos_config_handler.args.silent:
		aborted = False
		with Tui():
			if not config.confirm_config():
				debug('Installation aborted')
				aborted = True

		if aborted:
			return _minimal()

	if nixos_config_handler.config.disk_config:
		fs_handler = FilesystemHandler(nixos_config_handler.config.disk_config)
		fs_handler.perform_filesystem_operations()

	perform_installation(nixos_config_handler.args.mountpoint)


_minimal()
