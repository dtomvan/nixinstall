import os
from logging import warning
from pathlib import Path

from nixinstall import SysInfo
from nixinstall.lib.applications.application_handler import application_handler
from nixinstall.lib.args import nixos_config_handler
from nixinstall.lib.authentication.authentication_handler import auth_handler
from nixinstall.lib.configuration import ConfigurationOutput
from nixinstall.lib.disk.filesystem import FilesystemHandler
from nixinstall.lib.disk.utils import disk_layouts
from nixinstall.lib.global_menu import GlobalMenu
from nixinstall.lib.installer import Installer, accessibility_tools_in_use, run_custom_user_commands
from nixinstall.lib.interactions.general_conf import PostInstallationAction, ask_post_installation
from nixinstall.lib.models import Bootloader
from nixinstall.lib.models.device_model import (
	DiskLayoutType,
	EncryptionType,
)
from nixinstall.lib.nix.config import NixosConfig
from nixinstall.lib.output import debug, error, info
from nixinstall.lib.profile.profiles_handler import profile_handler
from nixinstall.tui import Tui


def ask_user_questions() -> None:
	"""
	First, we'll ask the user for a bunch of user input.
	Not until we're satisfied with what we want to install
	will we continue with the actual installation steps.
	"""

	title_text = None

	with Tui():
		global_menu = GlobalMenu(nixos_config_handler.config)

		if not nixos_config_handler.args.advanced:
			global_menu.set_enabled('parallel_downloads', False)

		global_menu.run(additional_title=title_text)


def perform_installation(mountpoint: Path) -> None:
	"""
	Performs the installation steps on a block device.
	Only requirement is that the block devices are
	formatted and setup prior to entering this function.
	"""
	info('Starting installation...')

	config = nixos_config_handler.config

	if not config.disk_config:
		error('No disk configuration provided')
		return

	disk_config = config.disk_config
	locale_config = config.locale_config
	mountpoint = disk_config.mountpoint if disk_config.mountpoint else mountpoint

	with Installer(
		mountpoint,
		disk_config,
		kernels=config.kernels,
	) as installation:
		osconfig = NixosConfig()
		osconfig.begin()

		# Mount all the drives to the desired mountpoint
		if disk_config.config_type != DiskLayoutType.Pre_mount:
			installation.mount_ordered_layout()

		installation.sanity_check()

		if disk_config.config_type != DiskLayoutType.Pre_mount:
			if disk_config.disk_encryption and disk_config.disk_encryption.encryption_type != EncryptionType.NoEncryption:
				# generate encryption key files for the mounted luks devices
				installation.generate_key_files()

		installation.minimal_installation(
			hostname=nixos_config_handler.config.hostname,
			locale_config=locale_config,
		)

		if config.swap:
			installation.setup_swap('zram')

		if config.bootloader == Bootloader.Grub and SysInfo.has_uefi():
			installation.add_additional_package('grub')

		installation.add_bootloader(config.bootloader, config.uki)

		# If user selected to copy the current ISO network configuration
		# Perform a copy of the config
		network_config = config.network_config

		if network_config:
			network_config.install_network_config(
				installation,
				config.profile_config,
			)

		if users := config.users:
			installation.create_users(users)

		if config.auth_config and config.users:
			auth_handler.setup_auth(installation, config.auth_config, config.users, config.hostname)

		if config.packages and config.packages[0] != '':
			installation.add_additional_packages(config.packages)

		if profile_config := config.profile_config:
			profile_handler.install_profile_config(installation, profile_config)

		if app_config := config.app_config:
			application_handler.install_applications(installation, app_config)

		if timezone := config.timezone:
			installation.set_timezone(timezone)

		if config.ntp:
			installation.activate_time_synchronization()

		if accessibility_tools_in_use():
			installation.enable_espeakup()

		if root_pw := config.root_enc_password:
			osconfig.set('users.users.root.initialHashedPassword', root_pw)

		if (profile_config := config.profile_config) and profile_config.profile:
			profile_config.profile.post_install(installation)

		if _services := config.services:
			# TODO: enable services
			pass

		if disk_config.is_default_btrfs():
			btrfs_options = disk_config.btrfs_options
			snapshot_config = btrfs_options.snapshot_config if btrfs_options else None
			snapshot_type = snapshot_config.snapshot_type if snapshot_config else None
			if snapshot_type:
				installation.setup_btrfs_snapshot(snapshot_type, config.bootloader)

		# If the user provided custom commands to be run post-installation, execute them now.
		if cc := config.custom_commands:
			run_custom_user_commands(cc, installation)

		warning('TODO: implement setting filesystems, most likely a call to nixos-generate-config')

		debug(f'Disk states after installing:\n{disk_layouts()}')

		if not nixos_config_handler.args.silent:
			with Tui():
				action = ask_post_installation()

			match action:
				case PostInstallationAction.EXIT:
					pass
				case PostInstallationAction.REBOOT:
					os.system('reboot')
				case PostInstallationAction.CHROOT:
					try:
						error('post-installation action CHROOT not implemented yet')
						# TODO: nixos-enter
					except Exception:
						pass


def guided() -> None:
	if not nixos_config_handler.args.silent:
		ask_user_questions()

	config = ConfigurationOutput(nixos_config_handler.config)

	if nixos_config_handler.args.dry_run:
		exit(0)

	if not nixos_config_handler.args.silent:
		aborted = False
		with Tui():
			if not config.confirm_config():
				debug('Installation aborted')
				aborted = True

		if aborted:
			return guided()

	if nixos_config_handler.config.disk_config:
		fs_handler = FilesystemHandler(nixos_config_handler.config.disk_config)
		fs_handler.perform_filesystem_operations()

	perform_installation(nixos_config_handler.args.mountpoint)


guided()
