from typing import override

from nixinstall.default_profiles.desktops import SeatAccess
from nixinstall.default_profiles.profile import GreeterType, ProfileType
from nixinstall.default_profiles.xorg import XorgProfile
from nixinstall.tui.curses_menu import SelectMenu
from nixinstall.tui.menu_item import MenuItem, MenuItemGroup
from nixinstall.tui.result import ResultType
from nixinstall.tui.types import Alignment, FrameProperties


class NiriProfile(XorgProfile):
	def __init__(self) -> None:
		super().__init__(
			'Niri',
			ProfileType.WindowMgr,
		)

		self.custom_settings = {'seat_access': None}

	@property
	@override
	def packages(self) -> list[str]:
		additional = []
		if seat := self.custom_settings.get('seat_access', None):
			additional = [seat]

		return [
			'niri',
			'alacritty',
			'fuzzel',
			'mako',
			'xorg-xwayland',
			'waybar',
			'swaybg',
			'swayidle',
			'swaylock',
			'xdg-desktop-portal-gnome',
		] + additional

	@property
	@override
	def default_greeter_type(self) -> GreeterType:
		return GreeterType.Lightdm

	def _ask_seat_access(self) -> None:
		# need to activate seat service and add to seat group
		header = 'niri needs access to your seat (collection of hardware devices i.e. keyboard, mouse, etc)'
		header += '\n' + 'Choose an option to give niri access to your hardware' + '\n'

		items = [MenuItem(s.value, value=s) for s in SeatAccess]
		group = MenuItemGroup(items, sort_items=True)

		default = self.custom_settings.get('seat_access', None)
		group.set_default_by_value(default)

		result = SelectMenu[SeatAccess](
			group,
			header=header,
			allow_skip=False,
			frame=FrameProperties.min('Seat access'),
			alignment=Alignment.CENTER,
		).run()

		if result.type_ == ResultType.Selection:
			self.custom_settings['seat_access'] = result.get_value().value

	@override
	def do_on_select(self) -> None:
		self._ask_seat_access()
		return None
