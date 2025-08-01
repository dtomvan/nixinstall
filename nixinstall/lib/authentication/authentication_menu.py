from typing import override

from nixinstall.lib.disk.fido import Fido2
from nixinstall.lib.menu.abstract_menu import AbstractSubMenu
from nixinstall.lib.models.authentication import AuthenticationConfiguration, U2FLoginConfiguration, U2FLoginMethod
from nixinstall.tui.curses_menu import SelectMenu, Tui
from nixinstall.tui.menu_item import MenuItem, MenuItemGroup
from nixinstall.tui.result import ResultType
from nixinstall.tui.types import Alignment, FrameProperties, Orientation


class AuthenticationMenu(AbstractSubMenu[AuthenticationConfiguration]):
	def __init__(self, preset: AuthenticationConfiguration | None = None):
		if preset:
			self._auth_config = preset
		else:
			self._auth_config = AuthenticationConfiguration()

		if not self._depends_on_u2f():
			# TODO: this message actually doesn't get displayed, how to do that?
			Tui.print('No fido2 devices found, skipping')
			return

		menu_optioons = self._define_menu_options()
		self._item_group = MenuItemGroup(menu_optioons, checkmarks=True)

		super().__init__(
			self._item_group,
			config=self._auth_config,
			allow_reset=True,
		)

	@override
	def run(self, additional_title: str | None = None) -> AuthenticationConfiguration:
		super().run(additional_title=additional_title)
		return self._auth_config

	def _define_menu_options(self) -> list[MenuItem]:
		return [
			MenuItem(
				text='U2F login setup',
				action=setup_u2f_login,
				value=self._auth_config.u2f_config,
				preview_action=self._prev_u2f_login,
				dependencies=[self._depends_on_u2f],
				key='u2f_config',
			),
		]

	def _depends_on_u2f(self) -> bool:
		devices = Fido2.get_fido2_devices()
		if not devices or len(devices) == 0:
			return False
		return True

	def _prev_u2f_login(self, item: MenuItem) -> str | None:
		if item.value is not None:
			u2f_config: U2FLoginConfiguration = item.value

			login_method = u2f_config.u2f_login_method.display_value()
			output = 'U2F login method: ' + login_method

			output += '\n'
			output += 'Passwordless sudo: ' + ('Enabled' if u2f_config.passwordless_sudo else 'Disabled')

			return output
		return None


def setup_u2f_login(preset: U2FLoginConfiguration) -> U2FLoginConfiguration | None:
	items = []
	for method in U2FLoginMethod:
		items.append(MenuItem(method.display_value(), value=method))

	group = MenuItemGroup(items)

	if preset is not None:
		group.set_selected_by_value(preset.u2f_login_method)

	result = SelectMenu[U2FLoginMethod](
		group,
		alignment=Alignment.CENTER,
		frame=FrameProperties.min('U2F Login Method'),
		allow_skip=True,
		allow_reset=True,
	).run()

	match result.type_:
		case ResultType.Selection:
			u2f_method = result.get_value()

			group = MenuItemGroup.yes_no()
			group.focus_item = MenuItem.no()
			header = 'Enable passwordless sudo?'

			result_sudo = SelectMenu[bool](
				group,
				header=header,
				alignment=Alignment.CENTER,
				columns=2,
				orientation=Orientation.HORIZONTAL,
				allow_skip=True,
			).run()

			passwordless_sudo = result_sudo.item() == MenuItem.yes()

			return U2FLoginConfiguration(
				u2f_login_method=u2f_method,
				passwordless_sudo=passwordless_sudo,
			)
		case ResultType.Skip:
			return preset
		case ResultType.Reset:
			return None
		case _:
			raise ValueError('Unhandled result type')
