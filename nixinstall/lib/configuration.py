from pathlib import Path

from nixinstall.lib.nix.config import NixosConfig
from nixinstall.tui.curses_menu import SelectMenu, Tui
from nixinstall.tui.menu_item import MenuItem, MenuItemGroup
from nixinstall.tui.types import Alignment, FrameProperties, Orientation, PreviewStyle

from .args import NixOSConfig
from .output import logger, warn


class ConfigurationOutput:
	def __init__(self, config: NixOSConfig):
		"""
		Configuration output handler to parse the existing
		configuration data structure and prepare for output on the
		console and for saving it to configuration files

		:param config: nixinstall configuration object
		:type config: NixOSConfig
		"""

		self._config = config
		self._default_save_path = logger.directory
		self._user_config_file = Path('user_configuration.json')
		self._user_creds_file = Path('user_credentials.json')

	@property
	def user_configuration_file(self) -> Path:
		return self._user_config_file

	@property
	def user_credentials_file(self) -> Path:
		return self._user_creds_file

	def confirm_config(self) -> bool:
		header = f'{"The specified configuration will be applied"}. '
		header += 'Would you like to continue?' + '\n'

		with Tui():
			group = MenuItemGroup.yes_no()
			group.focus_item = MenuItem.yes()
			group.set_preview_for_all(lambda _: NixosConfig()._repr())

			result = SelectMenu[bool](
				group,
				header=header,
				alignment=Alignment.CENTER,
				columns=2,
				orientation=Orientation.HORIZONTAL,
				allow_skip=False,
				preview_size='auto',
				preview_style=PreviewStyle.BOTTOM,
				preview_frame=FrameProperties.max('Configuration'),
			).run()

			if result.item() != MenuItem.yes():
				return False

		return True

	def _is_valid_path(self, dest_path: Path) -> bool:
		dest_path_ok = dest_path.exists() and dest_path.is_dir()
		if not dest_path_ok:
			warn(
				f'Destination directory {dest_path.resolve()} does not exist or is not a directory\n.',
				'Configuration files can not be saved',
			)
		return dest_path_ok
