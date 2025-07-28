import glob
import os
import re
import shutil
import time
from collections.abc import Callable
from logging import warning
from pathlib import Path
from types import TracebackType
from typing import Any

from nixinstall.lib.disk.device_handler import device_handler
from nixinstall.lib.disk.fido import Fido2
from nixinstall.lib.disk.utils import get_lsblk_by_mountpoint, get_lsblk_info
from nixinstall.lib.models.device_model import (
	DiskEncryption,
	DiskLayoutConfiguration,
	EncryptionType,
	FilesystemType,
	LvmVolume,
	PartitionModification,
	SectorSize,
	Size,
	SnapshotType,
	SubvolumeModification,
	Unit,
)
from nixinstall.lib.nix.config import NixosConfig
from nixinstall.tui.curses_menu import Tui

from .exceptions import DiskError, SysCallError
from .general import SysCommand
from .hardware import SysInfo
from .luks import Luks2
from .models.bootloader import Bootloader
from .models.locale import LocaleConfiguration
from .models.network_configuration import Nic
from .models.users import User
from .output import debug, error, info, log, logger, warn
from .storage import storage

# Additional packages that are installed if the user is running the Live ISO with accessibility tools enabled
__accessibility_packages__ = ['brltty', 'espeakup', 'alsa-utils']


class Installer:
	def __init__(
		self,
		target: Path,
		disk_config: DiskLayoutConfiguration,
		packages: list[str] = [],
		kernels: list[str] | None = None,
	):
		"""
		`Installer()` is the wrapper for most basic installation steps.
		"""
		# TODO: remove
		self._packages = packages
		self.kernels = kernels or ['linux']
		self._disk_config = disk_config

		self._disk_encryption = disk_config.disk_encryption or DiskEncryption(EncryptionType.NoEncryption)
		self.target: Path = target

		self.init_time = time.strftime('%Y-%m-%d_%H-%M-%S')
		self.milliseconds = int(str(time.time()).split('.')[1])
		self._helper_flags: dict[str, str | bool | None] = {
			'base': False,
			'bootloader': None,
		}

		for kernel in self.kernels:
			self._packages.append(kernel)

		if accessibility_tools_in_use():
			warning('TODO: __accessibility_packages__ probably through a nixos module instead')
			NixosConfig().install(__accessibility_packages__)

		self.post_base_install: list[Callable] = []  # type: ignore[type-arg]

		storage['installation_session'] = self

		self._zram_enabled = False
		self._enable_fstrim = True

	def __enter__(self) -> 'Installer':
		return self

	def __exit__(self, exc_type: type[BaseException] | None, exc_value: BaseException | None, traceback: TracebackType | None) -> bool | None:
		if exc_type is not None:
			error(str(exc_value))

			self.sync_log_to_install_medium()

			# We avoid printing /mnt/<log path> because that might confuse people if they note it down
			# and then reboot, and a identical log file will be found in the ISO medium anyway.
			Tui.print(str(f'[!] A log file has been created here: {logger.path}'))
			Tui.print('Please submit this issue (and file) to https://github.com/dtomvan/nixinstall/issues')

			# Return None to propagate the exception
			return None

		self.sync()

		if not (missing_steps := self.post_install_check()):
			msg = f'Installation completed without any errors.\nLog files temporarily available at {logger.directory}.\nYou may reboot when ready.\n'
			log(msg, fg='green')
			self.sync_log_to_install_medium()
			return True
		else:
			warn('Some required steps were not successfully installed/configured before leaving the installer:')

			for step in missing_steps:
				warn(f' - {step}')

			warn(f'Detailed error logs can be found at: {logger.directory}')
			warn('Submit this zip file as an issue to https://github.com/dtomvan/nixinstall/issues')

			self.sync_log_to_install_medium()
			return False

	def sync(self) -> None:
		info('Syncing the system...')
		SysCommand('sync')

	def _verify_boot_part(self) -> None:
		"""
		Check that mounted /boot device has at minimum size for installation
		The reason this check is here is to catch pre-mounted device configuration and potentially
		configured one that has not gone through any previous checks (e.g. --silence mode)

		NOTE: this function should be run AFTER running the mount_ordered_layout function
		"""
		boot_mount = self.target / 'boot'
		lsblk_info = get_lsblk_by_mountpoint(boot_mount)

		if len(lsblk_info) > 0:
			if lsblk_info[0].size < Size(200, Unit.MiB, SectorSize.default()):
				raise DiskError(
					f'The boot partition mounted at {boot_mount} is not large enough to install a boot loader. '
					f'Please resize it to at least 200MiB and re-run the installation.',
				)

	def sanity_check(self) -> None:
		warning('TODO: _some_ kind of sanity check might be desired')
		pass

	def mount_ordered_layout(self) -> None:
		debug('Mounting ordered layout')

		luks_handlers: dict[Any, Luks2] = {}

		match self._disk_encryption.encryption_type:
			case EncryptionType.NoEncryption:
				self._mount_lvm_layout()
			case EncryptionType.Luks:
				luks_handlers = self._prepare_luks_partitions(self._disk_encryption.partitions)
			case EncryptionType.LvmOnLuks:
				luks_handlers = self._prepare_luks_partitions(self._disk_encryption.partitions)
				self._import_lvm()
				self._mount_lvm_layout(luks_handlers)
			case EncryptionType.LuksOnLvm:
				self._import_lvm()
				luks_handlers = self._prepare_luks_lvm(self._disk_encryption.lvm_volumes)
				self._mount_lvm_layout(luks_handlers)

		# mount all regular partitions
		self._mount_partition_layout(luks_handlers)

	def _mount_partition_layout(self, luks_handlers: dict[Any, Luks2]) -> None:
		debug('Mounting partition layout')

		# do not mount any PVs part of the LVM configuration
		pvs = []
		if self._disk_config.lvm_config:
			pvs = self._disk_config.lvm_config.get_all_pvs()

		sorted_device_mods = self._disk_config.device_modifications.copy()

		# move the device with the root partition to the beginning of the list
		for mod in self._disk_config.device_modifications:
			if any(partition.is_root() for partition in mod.partitions):
				sorted_device_mods.remove(mod)
				sorted_device_mods.insert(0, mod)
				break

		for mod in sorted_device_mods:
			not_pv_part_mods = [p for p in mod.partitions if p not in pvs]

			# partitions have to mounted in the right order on btrfs the mountpoint will
			# be empty as the actual subvolumes are getting mounted instead so we'll use
			# '/' just for sorting
			sorted_part_mods = sorted(not_pv_part_mods, key=lambda x: x.mountpoint or Path('/'))

			for part_mod in sorted_part_mods:
				if luks_handler := luks_handlers.get(part_mod):
					self._mount_luks_partition(part_mod, luks_handler)
				else:
					self._mount_partition(part_mod)

	def _mount_lvm_layout(self, luks_handlers: dict[Any, Luks2] = {}) -> None:
		lvm_config = self._disk_config.lvm_config

		if not lvm_config:
			debug('No lvm config defined to be mounted')
			return

		debug('Mounting LVM layout')

		for vg in lvm_config.vol_groups:
			sorted_vol = sorted(vg.volumes, key=lambda x: x.mountpoint or Path('/'))

			for vol in sorted_vol:
				if luks_handler := luks_handlers.get(vol):
					self._mount_luks_volume(vol, luks_handler)
				else:
					self._mount_lvm_vol(vol)

	def _prepare_luks_partitions(
		self,
		partitions: list[PartitionModification],
	) -> dict[PartitionModification, Luks2]:
		return {
			part_mod: device_handler.unlock_luks2_dev(
				part_mod.dev_path,
				part_mod.mapper_name,
				self._disk_encryption.encryption_password,
			)
			for part_mod in partitions
			if part_mod.mapper_name and part_mod.dev_path
		}

	def _import_lvm(self) -> None:
		lvm_config = self._disk_config.lvm_config

		if not lvm_config:
			debug('No lvm config defined to be imported')
			return

		for vg in lvm_config.vol_groups:
			device_handler.lvm_import_vg(vg)

			for vol in vg.volumes:
				device_handler.lvm_vol_change(vol, True)

	def _prepare_luks_lvm(
		self,
		lvm_volumes: list[LvmVolume],
	) -> dict[LvmVolume, Luks2]:
		return {
			vol: device_handler.unlock_luks2_dev(
				vol.dev_path,
				vol.mapper_name,
				self._disk_encryption.encryption_password,
			)
			for vol in lvm_volumes
			if vol.mapper_name and vol.dev_path
		}

	def _mount_partition(self, part_mod: PartitionModification) -> None:
		if not part_mod.dev_path:
			return

		# it would be none if it's btrfs as the subvolumes will have the mountpoints defined
		if part_mod.mountpoint:
			target = self.target / part_mod.relative_mountpoint
			device_handler.mount(part_mod.dev_path, target, options=part_mod.mount_options)
		elif part_mod.fs_type == FilesystemType.Btrfs:
			self._mount_btrfs_subvol(
				part_mod.dev_path,
				part_mod.btrfs_subvols,
				part_mod.mount_options,
			)
		elif part_mod.is_swap():
			device_handler.swapon(part_mod.dev_path)

	def _mount_lvm_vol(self, volume: LvmVolume) -> None:
		if volume.fs_type != FilesystemType.Btrfs:
			if volume.mountpoint and volume.dev_path:
				target = self.target / volume.relative_mountpoint
				device_handler.mount(volume.dev_path, target, options=volume.mount_options)

		if volume.fs_type == FilesystemType.Btrfs and volume.dev_path:
			self._mount_btrfs_subvol(volume.dev_path, volume.btrfs_subvols, volume.mount_options)

	def _mount_luks_partition(self, part_mod: PartitionModification, luks_handler: Luks2) -> None:
		if not luks_handler.mapper_dev:
			return None

		if part_mod.fs_type == FilesystemType.Btrfs and part_mod.btrfs_subvols:
			self._mount_btrfs_subvol(luks_handler.mapper_dev, part_mod.btrfs_subvols, part_mod.mount_options)
		elif part_mod.mountpoint:
			target = self.target / part_mod.relative_mountpoint
			device_handler.mount(luks_handler.mapper_dev, target, options=part_mod.mount_options)

	def _mount_luks_volume(self, volume: LvmVolume, luks_handler: Luks2) -> None:
		if volume.fs_type != FilesystemType.Btrfs:
			if volume.mountpoint and luks_handler.mapper_dev:
				target = self.target / volume.relative_mountpoint
				device_handler.mount(luks_handler.mapper_dev, target, options=volume.mount_options)

		if volume.fs_type == FilesystemType.Btrfs and luks_handler.mapper_dev:
			self._mount_btrfs_subvol(luks_handler.mapper_dev, volume.btrfs_subvols, volume.mount_options)

	def _mount_btrfs_subvol(
		self,
		dev_path: Path,
		subvolumes: list[SubvolumeModification],
		mount_options: list[str] = [],
	) -> None:
		for subvol in sorted(subvolumes, key=lambda x: x.relative_mountpoint):
			mountpoint = self.target / subvol.relative_mountpoint
			options = mount_options + [f'subvol={subvol.name}']
			device_handler.mount(dev_path, mountpoint, options=options)

	def generate_key_files(self) -> None:
		match self._disk_encryption.encryption_type:
			case EncryptionType.Luks:
				self._generate_key_files_partitions()
			case EncryptionType.LuksOnLvm:
				self._generate_key_file_lvm_volumes()
			case EncryptionType.LvmOnLuks:
				# currently LvmOnLuks only supports a single
				# partitioning layout (boot + partition)
				# so we won't need any keyfile generation atm
				pass

	def _generate_key_files_partitions(self) -> None:
		for part_mod in self._disk_encryption.partitions:
			gen_enc_file = self._disk_encryption.should_generate_encryption_file(part_mod)

			luks_handler = Luks2(
				part_mod.safe_dev_path,
				mapper_name=part_mod.mapper_name,
				password=self._disk_encryption.encryption_password,
			)

			if gen_enc_file and not part_mod.is_root():
				debug(f'Creating key-file: {part_mod.dev_path}')
				luks_handler.create_keyfile(self.target)

			if part_mod.is_root() and not gen_enc_file:
				if self._disk_encryption.hsm_device:
					if self._disk_encryption.encryption_password:
						Fido2.fido2_enroll(
							self._disk_encryption.hsm_device,
							part_mod.safe_dev_path,
							self._disk_encryption.encryption_password,
						)

	def _generate_key_file_lvm_volumes(self) -> None:
		for vol in self._disk_encryption.lvm_volumes:
			gen_enc_file = self._disk_encryption.should_generate_encryption_file(vol)

			luks_handler = Luks2(
				vol.safe_dev_path,
				mapper_name=vol.mapper_name,
				password=self._disk_encryption.encryption_password,
			)

			if gen_enc_file and not vol.is_root():
				info(f'Creating key-file: {vol.dev_path}')
				luks_handler.create_keyfile(self.target)

			if vol.is_root() and not gen_enc_file:
				if self._disk_encryption.hsm_device:
					if self._disk_encryption.encryption_password:
						Fido2.fido2_enroll(
							self._disk_encryption.hsm_device,
							vol.safe_dev_path,
							self._disk_encryption.encryption_password,
						)

	def sync_log_to_install_medium(self) -> bool:
		# Copy over the install log (if there is one) to the install medium if
		# at least the base has been strapped in, otherwise we won't have a filesystem/structure to copy to.
		if self._helper_flags.get('base-strapped', False) is True:
			absolute_logfile = logger.path

			if not os.path.isdir(f'{self.target}/{os.path.dirname(absolute_logfile)}'):
				os.makedirs(f'{self.target}/{os.path.dirname(absolute_logfile)}')

			shutil.copy2(absolute_logfile, f'{self.target}/{absolute_logfile}')

		return True

	def add_swapfile(self, size: str = '4G', enable_resume: bool = True, file: str = '/swapfile') -> None:
		error('add_swapfile not implemented')

		if file[:1] != '/':
			file = f'/{file}'
		if len(file.strip()) <= 0 or file == '/':
			raise ValueError(f'The filename for the swap file has to be a valid path, not: {self.target}{file}')

		SysCommand(f'dd if=/dev/zero of={self.target}{file} bs={size} count=1')
		SysCommand(f'chmod 0600 {self.target}{file}')
		SysCommand(f'mkswap {self.target}{file}')

		if enable_resume:
			error('resume from swap not implemented')

	def post_install_check(self, *args: str, **kwargs: str) -> list[str]:
		return [step for step, flag in self._helper_flags.items() if flag is False]

	def set_hostname(self, hostname: str) -> None:
		NixosConfig().set('networking.hostName', hostname)

	def set_locale(self, locale_config: LocaleConfiguration) -> bool:
		modifier = ''
		lang = locale_config.sys_lang
		encoding = locale_config.sys_enc

		# This is a temporary patch to fix #1200
		if '.' in locale_config.sys_lang:
			lang, potential_encoding = locale_config.sys_lang.split('.', 1)

			# Override encoding if encoding is set to the default parameter
			# and the "found" encoding differs.
			if locale_config.sys_enc == 'UTF-8' and locale_config.sys_enc != potential_encoding:
				encoding = potential_encoding

		# Make sure we extract the modifier, that way we can put it in if needed.
		if '@' in locale_config.sys_lang:
			lang, modifier = locale_config.sys_lang.split('@', 1)
			modifier = f'@{modifier}'
		# - End patch

		locale_gen = self.target / 'etc/locale.gen'
		locale_gen_lines = locale_gen.read_text().splitlines(True)

		# A locale entry in /etc/locale.gen may or may not contain the encoding
		# in the first column of the entry; check for both cases.
		entry_re = re.compile(rf'#{lang}(\.{encoding})?{modifier} {encoding}')

		lang_value = None
		for index, line in enumerate(locale_gen_lines):
			if entry_re.match(line):
				uncommented_line = line.removeprefix('#')
				locale_gen_lines[index] = uncommented_line
				locale_gen.write_text(''.join(locale_gen_lines))
				lang_value = uncommented_line.split()[0]
				break

		if lang_value is None:
			error(f"Invalid locale: language '{locale_config.sys_lang}', encoding '{locale_config.sys_enc}'")
			return False

		try:
			SysCommand(f'arch-chroot {self.target} locale-gen')
		except SysCallError as e:
			error(f'Failed to run locale-gen on target: {e}')
			return False

		(self.target / 'etc/locale.conf').write_text(f'LANG={lang_value}\n')
		return True

	def set_timezone(self, zone: str) -> None:
		warn('TODO: check if zone exists')

		NixosConfig().set('time.timeZone', zone)

	def activate_time_synchronization(self) -> None:
		info('Activating systemd-timesyncd for time synchronization using NixOS and ntp.org NTP servers')
		# TODO: actually fill in the NixOS option
		debug('activate_time_synchronization noop')

	def enable_espeakup(self) -> None:
		info('Enabling espeakup.service for speech synthesis (accessibility)')
		# TODO: enable espeakup
		debug('enable_espeakup noop')

	def set_periodic_trim(self, enable: bool) -> None:
		info('Enabling periodic TRIM')
		self.set_additional_option('services.fstrim.enable', enable)

	# TODO: move to NetworkManager config
	def configure_nic(self, nic: Nic) -> None:
		conf = nic.as_systemd_config()

		with open(f'{self.target}/etc/systemd/network/10-{nic.iface}.network', 'a') as netconf:
			netconf.write(str(conf))

	def copy_iso_network_config(self) -> bool:
		# Copy (if any) iwd password and config files
		if os.path.isdir('/var/lib/iwd/'):
			if psk_files := glob.glob('/var/lib/iwd/*.psk'):
				if not os.path.isdir(f'{self.target}/var/lib/iwd'):
					os.makedirs(f'{self.target}/var/lib/iwd')

				self._packages.append('iwd')

				for psk in psk_files:
					shutil.copy2(psk, f'{self.target}/var/lib/iwd/{os.path.basename(psk)}')

		# Copy (if any) systemd-networkd config files
		if netconfigurations := glob.glob('/etc/systemd/network/*'):
			if not os.path.isdir(f'{self.target}/etc/systemd/network/'):
				os.makedirs(f'{self.target}/etc/systemd/network/')

			for netconf_file in netconfigurations:
				shutil.copy2(netconf_file, f'{self.target}/etc/systemd/network/{os.path.basename(netconf_file)}')

		return True

	def _get_microcode(self) -> Path | None:
		if not SysInfo.is_vm():
			if vendor := SysInfo.cpu_vendor():
				return vendor.get_ucode()
		return None

	def _prepare_fs_type(
		self,
		fs_type: FilesystemType,
		mountpoint: Path | None,
	) -> None:
		if (pkg := fs_type.installation_pkg) is not None:
			self._packages.append(pkg)

		# https://github.com/archlinux/archinstall/issues/1837
		if fs_type.fs_type_mount == 'btrfs':
			self._enable_fstrim = False

	def _prepare_encrypt(self, before: str = 'filesystems') -> None:
		error('_prepare_encrypt not implemented')

	def minimal_installation(
		self,
		hostname: str | None = None,
		locale_config: LocaleConfiguration | None = LocaleConfiguration.default(),
	) -> None:
		if self._disk_config.lvm_config:
			lvm = 'lvm2'
			self._packages.append(lvm)

			for vg in self._disk_config.lvm_config.vol_groups:
				for vol in vg.volumes:
					if vol.fs_type is not None:
						self._prepare_fs_type(vol.fs_type, vol.mountpoint)

			types = (EncryptionType.LvmOnLuks, EncryptionType.LuksOnLvm)
			if self._disk_encryption.encryption_type in types:
				self._prepare_encrypt(lvm)
		else:
			for mod in self._disk_config.device_modifications:
				for part in mod.partitions:
					if part.fs_type is None:
						continue

					self._prepare_fs_type(part.fs_type, part.mountpoint)

					if part in self._disk_encryption.partitions:
						self._prepare_encrypt()

		if ucode := self._get_microcode():
			(self.target / 'boot' / ucode).unlink(missing_ok=True)
			self._packages.append(ucode.stem)
		else:
			debug('nixinstall will not install any ucode.')

		self._helper_flags['base-strapped'] = True

		# Periodic TRIM may improve the performance and longevity of SSDs whilst
		# having no adverse effect on other devices. Most distributions enable
		# periodic TRIM by default.
		self.set_periodic_trim(self._enable_fstrim)

		# TODO: Support locale and timezone
		# os.remove(f'{self.target}/etc/localtime')
		# sys_command(f'arch-chroot {self.target} ln -s /usr/share/zoneinfo/{localtime} /etc/localtime')
		# sys_command('arch-chroot /mnt hwclock --hctosys --localtime')
		if hostname:
			self.set_hostname(hostname)

		if locale_config:
			self.set_locale(locale_config)
			self.set_keyboard_language(locale_config.kb_layout)

		# TODO: Use python functions for this
		SysCommand(f'arch-chroot {self.target} chmod 700 /root')

		self._helper_flags['base'] = True

	def setup_btrfs_snapshot(
		self,
		snapshot_type: SnapshotType,
		bootloader: Bootloader | None = None,
	) -> None:
		if snapshot_type == SnapshotType.Snapper:
			debug('Setting up Btrfs snapper')
			# TODO: services.snapper.configs
		elif snapshot_type == SnapshotType.Timeshift:
			debug('Setting up Btrfs timeshift')
			# TODO: add timeshift timer

	def setup_swap(self, kind: str = 'zram') -> None:
		if kind == 'zram':
			# TODO: zramSwap.enable
			self._zram_enabled = True
		else:
			raise ValueError('nixinstall currently only supports setting up swap on zram')

	def _get_efi_partition(self) -> PartitionModification | None:
		for layout in self._disk_config.device_modifications:
			if partition := layout.get_efi_partition():
				return partition
		return None

	def _get_boot_partition(self) -> PartitionModification | None:
		for layout in self._disk_config.device_modifications:
			if boot := layout.get_boot_partition():
				return boot
		return None

	def _get_root(self) -> PartitionModification | LvmVolume | None:
		if self._disk_config.lvm_config:
			return self._disk_config.lvm_config.get_root_volume()
		else:
			for mod in self._disk_config.device_modifications:
				if root := mod.get_root_partition():
					return root
		return None

	def _get_luks_uuid_from_mapper_dev(self, mapper_dev_path: Path) -> str:
		lsblk_info = get_lsblk_info(mapper_dev_path, reverse=True, full_dev_path=True)

		if not lsblk_info.children or not lsblk_info.children[0].uuid:
			raise ValueError('Unable to determine UUID of luks superblock')

		return lsblk_info.children[0].uuid

	def _get_kernel_params(
		self,
		root: PartitionModification | LvmVolume,
		id_root: bool = True,
		partuuid: bool = True,
	) -> list[str]:
		warning('TODO: most likely _get_kernel_params will not be used')

		kernel_parameters = []

		warning('TODO: get fileSystems and swapDevices')

		# Zswap should be disabled when using zram.
		# https://github.com/archlinux/archinstall/issues/881
		if self._zram_enabled:
			kernel_parameters.append('zswap.enabled=0')

		return kernel_parameters

	def _create_bls_entries(
		self,
		boot_partition: PartitionModification,
		root: PartitionModification | LvmVolume,
		entry_name: str,
	) -> None:
		error('Installer._create_bls_entries not implemented, should be done by NixOS automatically')

	def _add_systemd_bootloader(
		self,
		boot_partition: PartitionModification,
		root: PartitionModification | LvmVolume,
		efi_partition: PartitionModification | None,
		uki_enabled: bool = False,
	) -> None:
		debug('Installing systemd bootloader')

		# TODO: implement systemd-bootd
		error('systemd bootloader not implemented yet')

		# if not SysInfo.has_uefi():
		# 	raise HardwareIncompatibilityError

		# if not efi_partition:
		# 	raise ValueError('Could not detect EFI system partition')
		# elif not efi_partition.mountpoint:
		# 	raise ValueError('EFI system partition is not mounted')

		# # TODO: Ideally we would want to check if another config
		# # points towards the same disk and/or partition.
		# # And in which case we should do some clean up.
		# bootctl_options = []

		# if boot_partition != efi_partition:
		# 	bootctl_options.append(f'--esp-path={efi_partition.mountpoint}')
		# 	bootctl_options.append(f'--boot-path={boot_partition.mountpoint}')

		# # TODO: Remove this line after 258 hits nixpkgs 25.05/25.11
		# systemd_version = 257  # This works as a safety workaround for this hot-fix

		# # Install the boot loader
		# try:
		# 	# Force EFI variables since bootctl detects arch-chroot
		# 	# as a container environemnt since v257 and skips them silently.
		# 	# https://github.com/systemd/systemd/issues/36174
		# 	if systemd_version >= 258:
		# 		SysCommand(f'arch-chroot {self.target} bootctl --variables=yes {" ".join(bootctl_options)} install')
		# 	else:
		# 		SysCommand(f'arch-chroot {self.target} bootctl {" ".join(bootctl_options)} install')
		# except SysCallError:
		# 	if systemd_version >= 258:
		# 		# Fallback, try creating the boot loader without touching the EFI variables
		# 		SysCommand(f'arch-chroot {self.target} bootctl --variables=no {" ".join(bootctl_options)} install')
		# 	else:
		# 		SysCommand(f'arch-chroot {self.target} bootctl --no-variables {" ".join(bootctl_options)} install')

		# # Loader configuration is stored in ESP/loader:
		# # https://man.archlinux.org/man/loader.conf.5
		# loader_conf = self.target / efi_partition.relative_mountpoint / 'loader/loader.conf'
		# # Ensure that the ESP/loader/ directory exists before trying to create a file in it
		# loader_conf.parent.mkdir(parents=True, exist_ok=True)

		# default_kernel = self.kernels[0]
		# if uki_enabled:
		# 	default_entry = f'arch-{default_kernel}.efi'
		# else:
		# 	entry_name = self.init_time + '_{kernel}{variant}.conf'
		# 	default_entry = entry_name.format(kernel=default_kernel, variant='')
		# 	self._create_bls_entries(boot_partition, root, entry_name)

		# default = f'default {default_entry}'

		# # Modify or create a loader.conf
		# try:
		# 	loader_data = loader_conf.read_text().splitlines()
		# except FileNotFoundError:
		# 	loader_data = [
		# 		default,
		# 		'timeout 15',
		# 	]
		# else:
		# 	for index, line in enumerate(loader_data):
		# 		if line.startswith('default'):
		# 			loader_data[index] = default
		# 		elif line.startswith('#timeout'):
		# 			# We add in the default timeout to support dual-boot
		# 			loader_data[index] = line.removeprefix('#')

		# loader_conf.write_text('\n'.join(loader_data) + '\n')

		self._helper_flags['bootloader'] = 'systemd'

	def _add_grub_bootloader(
		self,
		boot_partition: PartitionModification,
		root: PartitionModification | LvmVolume,
		efi_partition: PartitionModification | None,
	) -> None:
		debug('Installing grub bootloader')

		error('_add_grub_bootloader not yet implemented')

	def _add_limine_bootloader(
		self,
		boot_partition: PartitionModification,
		efi_partition: PartitionModification | None,
		root: PartitionModification | LvmVolume,
		uki_enabled: bool = False,
	) -> None:
		debug('Installing Limine bootloader')

		error('_add_limine_bootloader not yet implemented')

	def _add_efistub_bootloader(
		self,
		boot_partition: PartitionModification,
		root: PartitionModification | LvmVolume,
		uki_enabled: bool = False,
	) -> None:
		debug('Installing efistub bootloader')

		error('_add_efistub_bootloader not yet implemented')

	def _config_uki(
		self,
		root: PartitionModification | LvmVolume,
		efi_partition: PartitionModification | None,
	) -> None:
		warning('TODO: implement setting kernel versions')
		warning("TODO: implement UKI's (if possible on NixOS without lanzaboote IDK)")

	def add_bootloader(self, bootloader: Bootloader, uki_enabled: bool = False) -> None:
		"""
		Adds a bootloader to the installation instance.
		nixinstall supports one of three types:
		* systemd-bootctl
		* grub
		* limine (beta)
		* efistub (beta)

		:param bootloader: Type of bootloader to be added
		"""

		efi_partition = self._get_efi_partition()
		boot_partition = self._get_boot_partition()
		root = self._get_root()

		if boot_partition is None:
			raise ValueError(f'Could not detect boot at mountpoint {self.target}')

		if root is None:
			raise ValueError(f'Could not detect root at mountpoint {self.target}')

		info(f'Adding bootloader {bootloader.value} to {boot_partition.dev_path}')

		if uki_enabled:
			self._config_uki(root, efi_partition)

		match bootloader:
			case Bootloader.Systemd:
				self._add_systemd_bootloader(boot_partition, root, efi_partition, uki_enabled)
			case Bootloader.Grub:
				self._add_grub_bootloader(boot_partition, root, efi_partition)
			case Bootloader.Efistub:
				self._add_efistub_bootloader(boot_partition, root, uki_enabled)
			case Bootloader.Limine:
				self._add_limine_bootloader(boot_partition, efi_partition, root, uki_enabled)

	def add_additional_package(self, package: str) -> None:
		return self.add_additional_packages([package])

	def add_additional_packages(self, packages: list[str]) -> None:
		# TODO: this is an alias at this point
		NixosConfig().install(packages)

	def set_additional_option(self, key: str, value: Any) -> None:
		error('add_additional_option not implemented yet')

	def create_users(self, users: User | list[User]) -> None:
		if not isinstance(users, list):
			users = [users]

		for user in users:
			self._create_user(user)

	def _create_user(self, user: User) -> None:
		info(f'Creating user {user.username}')

		if user.sudo:
			user.groups += 'wheel'

		NixosConfig().set(
			f'users.users.{user.username}',
			{
				'extraGroups': user.groups,
				'hashedPassword': user.password.enc_password,
				'isNormalUser': True,
				'createHome': True,
			},
		)

	def set_keyboard_language(self, language: str) -> bool:
		info(f'Setting keyboard language to {language}')
		# TODO: use loadkeys, maybe set a variable for the target config
		error('Installer.set_keyboard_language not yet implemented')
		return False

	def set_x11_keyboard_language(self, language: str) -> bool:
		"""
		A fallback function to set x11 layout specifically and separately from console layout.
		This isn't strictly necessary since .set_keyboard_language() does this as well.
		"""
		info(f'Setting x11 keyboard language to {language}')
		error('Installer.set_x11_keyboard_language not yet implemented')
		return False


def accessibility_tools_in_use() -> bool:
	return os.system('systemctl is-active --quiet espeakup.service') == 0


def run_custom_user_commands(commands: list[str], installation: Installer) -> None:
	for index, command in enumerate(commands):
		script_path = f'/var/tmp/user-command.{index}.sh'
		chroot_path = f'{installation.target}/{script_path}'

		info(f'Executing custom command "{command}" ...')
		with open(chroot_path, 'w') as user_script:
			user_script.write(command)

		SysCommand(f'arch-chroot {installation.target} bash {script_path}')

		os.unlink(chroot_path)
