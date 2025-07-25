from pathlib import Path

from nixinstall import debug, error
from nixinstall.lib.args import nixos_config_handler
from nixinstall.lib.configuration import ConfigurationOutput
from nixinstall.lib.disk.filesystem import FilesystemHandler
from nixinstall.lib.disk.utils import disk_layouts
from nixinstall.lib.global_menu import GlobalMenu
from nixinstall.lib.installer import Installer
from nixinstall.tui import Tui


def ask_user_questions() -> None:
	with Tui():
		global_menu = GlobalMenu(nixos_config_handler.config)
		global_menu.disable_all()

		global_menu.set_enabled('disk_config', True)
		global_menu.set_enabled('swap', True)
		global_menu.set_enabled('__config__', True)

		global_menu.run()


def perform_installation(mountpoint: Path) -> None:
	"""
	Performs the installation steps on a block device.
	Only requirement is that the block devices are
	formatted and setup prior to entering this function.
	"""
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
		# Mount all the drives to the desired mountpoint
		# This *can* be done outside of the installation, but the installer can deal with it.
		installation.mount_ordered_layout()

		# to generate a fstab directory holder. Avoids an error on exit and at the same time checks the procedure
		target = Path(f'{mountpoint}/etc/fstab')
		if not target.parent.exists():
			target.parent.mkdir(parents=True)

	# For support reasons, we'll log the disk layout post installation (crash or no crash)
	debug(f'Disk states after installing:\n{disk_layouts()}')


def _only_hd() -> None:
	if not nixos_config_handler.args.silent:
		ask_user_questions()

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
			return _only_hd()

	if nixos_config_handler.config.disk_config:
		fs_handler = FilesystemHandler(nixos_config_handler.config.disk_config)
		fs_handler.perform_filesystem_operations()

	perform_installation(nixos_config_handler.args.mountpoint)


_only_hd()
