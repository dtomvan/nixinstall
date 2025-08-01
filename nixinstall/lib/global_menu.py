from __future__ import annotations

from typing import override

from nixinstall.lib.disk.disk_menu import DiskLayoutConfigurationMenu
from nixinstall.lib.models.application import ApplicationConfiguration
from nixinstall.lib.models.authentication import AuthenticationConfiguration
from nixinstall.lib.models.device_model import DiskLayoutConfiguration, DiskLayoutType, EncryptionType, FilesystemType, PartitionModification
from nixinstall.tui.menu_item import MenuItem, MenuItemGroup

from .applications.application_menu import ApplicationMenu
from .args import NixOSConfig
from .authentication.authentication_menu import AuthenticationMenu
from .hardware import SysInfo
from .interactions.general_conf import (
	add_number_of_parallel_downloads,
	ask_additional_packages_to_install,
	ask_for_a_timezone,
	ask_hostname,
	ask_ntp,
)
from .interactions.manage_users_conf import ask_for_additional_users
from .interactions.network_menu import ask_to_configure_network
from .interactions.system_conf import ask_for_bootloader, ask_for_swap, ask_for_uki, select_kernel
from .locale.locale_menu import LocaleMenu
from .menu.abstract_menu import CONFIG_KEY, AbstractMenu
from .models.bootloader import Bootloader
from .models.locale import LocaleConfiguration
from .models.network_configuration import NetworkConfiguration, NicType
from .models.profile_model import ProfileConfiguration
from .models.users import Password, User
from .output import FormattedOutput, error
from .utils.util import get_password


class GlobalMenu(AbstractMenu[None]):
	def __init__(self, nixos_config: NixOSConfig) -> None:
		self._nixos_config = nixos_config
		menu_optioons = self._get_menu_options()

		self._item_group = MenuItemGroup(
			menu_optioons,
			sort_items=False,
			checkmarks=True,
		)

		super().__init__(self._item_group, config=nixos_config)

	def _get_menu_options(self) -> list[MenuItem]:
		return [
			MenuItem(
				text='Locales',
				action=self._locale_selection,
				preview_action=self._prev_locale,
				key='locale_config',
			),
			# TODO: add item for channels
			MenuItem(
				text='Disk configuration',
				action=self._select_disk_config,
				preview_action=self._prev_disk_config,
				mandatory=True,
				key='disk_config',
			),
			MenuItem(
				text='Swap',
				value=True,
				action=ask_for_swap,
				preview_action=self._prev_swap,
				key='swap',
			),
			MenuItem(
				text='Bootloader',
				value=Bootloader.get_default(),
				action=self._select_bootloader,
				preview_action=self._prev_bootloader,
				mandatory=True,
				key='bootloader',
			),
			MenuItem(
				text='Unified kernel images',
				value=False,
				enabled=SysInfo.has_uefi(),
				action=ask_for_uki,
				preview_action=self._prev_uki,
				key='uki',
			),
			MenuItem(
				text='Hostname',
				value='nixos',
				action=ask_hostname,
				preview_action=self._prev_hostname,
				key='hostname',
			),
			MenuItem(
				text='Root password',
				action=self._set_root_password,
				preview_action=self._prev_root_pwd,
				key='root_enc_password',
			),
			MenuItem(
				text='Authentication',
				action=self._select_authentication,
				value=[],
				preview_action=self._prev_authentication,
				key='auth_config',
			),
			MenuItem(
				text='User account',
				action=self._create_user_account,
				preview_action=self._prev_users,
				key='users',
			),
			MenuItem(
				text='Profile',
				action=self._select_profile,
				preview_action=self._prev_profile,
				key='profile_config',
			),
			MenuItem(
				text='Applications',
				action=self._select_applications,
				value=[],
				preview_action=self._prev_applications,
				key='app_config',
			),
			MenuItem(
				text='Kernels',
				value=['linux'],
				action=select_kernel,
				preview_action=self._prev_kernel,
				mandatory=True,
				key='kernels',
			),
			MenuItem(
				text='Network configuration',
				action=ask_to_configure_network,
				value={},
				preview_action=self._prev_network_config,
				key='network_config',
			),
			MenuItem(
				text='Parallel Downloads',
				action=add_number_of_parallel_downloads,
				value=0,
				preview_action=self._prev_parallel_dw,
				key='parallel_downloads',
			),
			MenuItem(
				text='Additional packages',
				action=self._select_additional_packages,
				value=[],
				preview_action=self._prev_additional_pkgs,
				key='packages',
			),
			MenuItem(
				text='Timezone',
				action=ask_for_a_timezone,
				value='UTC',
				preview_action=self._prev_tz,
				key='timezone',
			),
			MenuItem(
				text='Automatic time sync (NTP)',
				action=ask_ntp,
				value=True,
				preview_action=self._prev_ntp,
				key='ntp',
			),
			MenuItem(
				text='',
			),
			MenuItem(
				text='Save configuration',
				action=lambda x: error('save configuration not implemented yet'),
				key=f'{CONFIG_KEY}_save',
			),
			MenuItem(
				text='Install',
				preview_action=self._prev_install_invalid_config,
				key=f'{CONFIG_KEY}_install',
			),
			MenuItem(
				text='Abort',
				action=lambda x: exit(1),
				key=f'{CONFIG_KEY}_abort',
			),
		]

	def _missing_configs(self) -> list[str]:
		def check(s: str) -> bool:
			item = self._item_group.find_by_key(s)
			return item.has_value()

		def has_superuser() -> bool:
			item = self._item_group.find_by_key('users')

			if item.has_value():
				users = item.value
				if users:
					return any([u.sudo for u in users])
			return False

		missing = set()

		for item in self._item_group.items:
			if item.key in ['root_enc_password', 'users']:
				if not check('root_enc_password') and not has_superuser():
					missing.add(
						'Either root-password or at least 1 user with sudo privileges must be specified',
					)
			elif item.mandatory:
				assert item.key is not None
				if not check(item.key):
					missing.add(item.text)

		return list(missing)

	@override
	def _is_config_valid(self) -> bool:
		"""
		Checks the validity of the current configuration.
		"""
		if len(self._missing_configs()) != 0:
			return False
		return self._validate_bootloader() is None

	def _select_applications(self, preset: ApplicationConfiguration | None) -> ApplicationConfiguration | None:
		app_config = ApplicationMenu(preset).run()
		return app_config

	def _select_authentication(self, preset: AuthenticationConfiguration | None) -> AuthenticationConfiguration | None:
		auth_config = AuthenticationMenu(preset).run()
		return auth_config

	def _update_lang_text(self) -> None:
		"""
		The options for the global menu are generated with a static text;
		each entry of the menu needs to be updated with the new translation
		"""
		new_options = self._get_menu_options()

		for o in new_options:
			if o.key is not None:
				self._item_group.find_by_key(o.key).text = o.text

	def _locale_selection(self, preset: LocaleConfiguration) -> LocaleConfiguration:
		locale_config = LocaleMenu(preset).run()
		return locale_config

	def _prev_locale(self, item: MenuItem) -> str | None:
		if not item.value:
			return None

		config: LocaleConfiguration = item.value
		return config.preview()

	def _prev_network_config(self, item: MenuItem) -> str | None:
		if item.value:
			network_config: NetworkConfiguration = item.value
			if network_config.type == NicType.MANUAL:
				output = FormattedOutput.as_table(network_config.nics)
			else:
				output = f'{"Network configuration"}:\n{network_config.type.display_msg()}'

			return output
		return None

	def _prev_additional_pkgs(self, item: MenuItem) -> str | None:
		if item.value:
			output = '\n'.join(sorted(item.value))
			return output
		return None

	def _prev_authentication(self, item: MenuItem) -> str | None:
		if item.value:
			auth_config: AuthenticationConfiguration = item.value
			output = ''

			if auth_config.u2f_config:
				u2f_config = auth_config.u2f_config
				login_method = u2f_config.u2f_login_method.display_value()
				output = 'U2F login method: ' + login_method

				output += '\n'
				output += 'Passwordless sudo: ' + ('Enabled' if u2f_config.passwordless_sudo else 'Disabled')

			return output

		return None

	def _prev_applications(self, item: MenuItem) -> str | None:
		if item.value:
			app_config: ApplicationConfiguration = item.value
			output = ''

			if app_config.bluetooth_config:
				output += f'{"Bluetooth"}: '
				output += 'Enabled' if app_config.bluetooth_config.enabled else 'Disabled'
				output += '\n'

			if app_config.audio_config:
				audio_config = app_config.audio_config
				output += f'{"Audio"}: {audio_config.audio.value}'
				output += '\n'

			return output

		return None

	def _prev_tz(self, item: MenuItem) -> str | None:
		if item.value:
			return f'{"Timezone"}: {item.value}'
		return None

	def _prev_ntp(self, item: MenuItem) -> str | None:
		if item.value is not None:
			output = f'{"NTP"}: '
			output += 'Enabled' if item.value else 'Disabled'
			return output
		return None

	def _prev_disk_config(self, item: MenuItem) -> str | None:
		disk_layout_conf: DiskLayoutConfiguration | None = item.value

		if disk_layout_conf:
			output = f'Configuration type: {disk_layout_conf.config_type.display_msg()}' + '\n'

			if disk_layout_conf.config_type == DiskLayoutType.Pre_mount:
				output += 'Mountpoint' + ': ' + str(disk_layout_conf.mountpoint)

			if disk_layout_conf.lvm_config:
				output += '{}: {}'.format('LVM configuration type', disk_layout_conf.lvm_config.config_type.display_msg()) + '\n'

			if disk_layout_conf.disk_encryption:
				output += 'Disk encryption' + ': ' + EncryptionType.type_to_text(disk_layout_conf.disk_encryption.encryption_type) + '\n'

			if disk_layout_conf.btrfs_options:
				btrfs_options = disk_layout_conf.btrfs_options
				if btrfs_options.snapshot_config:
					output += f'Btrfs snapshot type: {btrfs_options.snapshot_config.snapshot_type.value}' + '\n'

			return output

		return None

	def _prev_swap(self, item: MenuItem) -> str | None:
		if item.value is not None:
			output = f'{"Swap on zram"}: '
			output += 'Enabled' if item.value else 'Disabled'
			return output
		return None

	def _prev_uki(self, item: MenuItem) -> str | None:
		if item.value is not None:
			output = f'{"Unified kernel images"}: '
			output += 'Enabled' if item.value else 'Disabled'
			return output
		return None

	def _prev_hostname(self, item: MenuItem) -> str | None:
		if item.value is not None:
			return f'{"Hostname"}: {item.value}'
		return None

	def _prev_root_pwd(self, item: MenuItem) -> str | None:
		if item.value is not None:
			password: Password = item.value
			return f'{"Root password"}: {password.hidden()}'
		return None

	def _prev_parallel_dw(self, item: MenuItem) -> str | None:
		if item.value is not None:
			return f'{"Parallel Downloads"}: {item.value}'
		return None

	def _prev_kernel(self, item: MenuItem) -> str | None:
		if item.value:
			kernel = ', '.join(item.value)
			return f'{"Kernel"}: {kernel}'
		return None

	def _prev_bootloader(self, item: MenuItem) -> str | None:
		if item.value is not None:
			return f'{"Bootloader"}: {item.value.value}'
		return None

	def _validate_bootloader(self) -> str | None:
		"""
		Checks the selected bootloader is valid for the selected filesystem
		type of the boot partition.

		Returns [`None`] if the bootloader is valid, otherwise returns a
		string with the error message.

		XXX: The caller is responsible for wrapping the string with the translation
			shim if necessary.
		"""
		bootloader = self._item_group.find_by_key('bootloader').value
		root_partition: PartitionModification | None = None
		boot_partition: PartitionModification | None = None
		efi_partition: PartitionModification | None = None

		if disk_config := self._item_group.find_by_key('disk_config').value:
			for layout in disk_config.device_modifications:
				if root_partition := layout.get_root_partition():
					break
			for layout in disk_config.device_modifications:
				if boot_partition := layout.get_boot_partition():
					break
			if SysInfo.has_uefi():
				for layout in disk_config.device_modifications:
					if efi_partition := layout.get_efi_partition():
						break
		else:
			return 'No disk layout selected'

		if root_partition is None:
			return 'Root partition not found'

		if boot_partition is None:
			return 'Boot partition not found'

		if SysInfo.has_uefi():
			if efi_partition is None:
				return 'EFI system partition (ESP) not found'

			if efi_partition.fs_type not in [FilesystemType.Fat12, FilesystemType.Fat16, FilesystemType.Fat32]:
				return 'ESP must be formatted as a FAT filesystem'

		if bootloader == Bootloader.Limine:
			if boot_partition.fs_type not in [FilesystemType.Fat12, FilesystemType.Fat16, FilesystemType.Fat32]:
				return 'Limine does not support booting with a non-FAT boot partition'

		return None

	def _prev_install_invalid_config(self, item: MenuItem) -> str | None:
		if missing := self._missing_configs():
			text = 'Missing configurations:\n'
			for m in missing:
				text += f'- {m}\n'
			return text[:-1]  # remove last new line

		if error := self._validate_bootloader():
			return f'Invalid configuration: {error}'

		return None

	def _prev_users(self, item: MenuItem) -> str | None:
		users: list[User] | None = item.value

		if users:
			return FormattedOutput.as_table(users)
		return None

	def _prev_profile(self, item: MenuItem) -> str | None:
		profile_config: ProfileConfiguration | None = item.value

		if profile_config and profile_config.profile:
			output = 'Profiles' + ': '
			if profile_names := profile_config.profile.current_selection_names():
				output += ', '.join(profile_names) + '\n'
			else:
				output += profile_config.profile.name + '\n'

			if profile_config.gfx_driver:
				output += 'Graphics driver' + ': ' + profile_config.gfx_driver.value + '\n'

			if profile_config.greeter:
				output += 'Greeter' + ': ' + profile_config.greeter.value + '\n'

			return output

		return None

	def _set_root_password(self, preset: str | None = None) -> Password | None:
		password = get_password(text='Root password', allow_skip=True)
		return password

	def _select_disk_config(
		self,
		preset: DiskLayoutConfiguration | None = None,
	) -> DiskLayoutConfiguration | None:
		disk_config = DiskLayoutConfigurationMenu(preset).run()

		return disk_config

	def _select_bootloader(self, preset: Bootloader | None) -> Bootloader | None:
		bootloader = ask_for_bootloader(preset)

		if bootloader:
			uki = self._item_group.find_by_key('uki')
			if not SysInfo.has_uefi() or not bootloader.has_uki_support():
				uki.value = False
				uki.enabled = False
			else:
				uki.enabled = True

		return bootloader

	def _select_profile(self, current_profile: ProfileConfiguration | None) -> ProfileConfiguration | None:
		from .profile.profile_menu import ProfileMenu

		profile_config = ProfileMenu(preset=current_profile).run()
		return profile_config

	# FIXME: inline this or something
	def _select_additional_packages(self, preset: list[str]) -> list[str]:
		return ask_additional_packages_to_install(preset)

	def _create_user_account(self, preset: list[User] | None = None) -> list[User]:
		preset = [] if preset is None else preset
		users = ask_for_additional_users(defined_users=preset)
		return users
