from typing import TYPE_CHECKING, override

from nixinstall.default_profiles.profile import ProfileType
from nixinstall.default_profiles.xorg import XorgProfile

if TYPE_CHECKING:
	from nixinstall.lib.installer import Installer


class AwesomeProfile(XorgProfile):
	def __init__(self) -> None:
		super().__init__('Awesome', ProfileType.WindowMgr)

	@property
	@override
	def packages(self) -> list[str]:
		return super().packages + [
			'awesome',
			'alacritty',
			'xorg-xinit',
			'xorg-xrandr',
			'xterm',
			'feh',
			'slock',
			'terminus-font',
			'gnu-free-fonts',
			'ttf-liberation',
			'xsel',
		]

	@override
	def install(self, install_session: 'Installer') -> None:
		super().install(install_session)

		# TODO: Copy a full configuration to ~/.config/awesome/rc.lua instead.
		with open(f'{install_session.target}/etc/xdg/awesome/rc.lua') as fh:
			awesome_lua = fh.read()

		# Replace xterm with alacritty for a smoother experience.
		awesome_lua = awesome_lua.replace('"xterm"', '"alacritty"')

		with open(f'{install_session.target}/etc/xdg/awesome/rc.lua', 'w') as fh:
			fh.write(awesome_lua)

		# TODO: Configure the right-click-menu to contain the above packages that were installed. (as a user config)

		# TODO: check if we selected a greeter,
		# but for now, awesome is intended to run without one.
		with open(f'{install_session.target}/etc/X11/xinit/xinitrc') as xinitrc:
			xinitrc_data = xinitrc.read()

		for line in xinitrc_data.split('\n'):
			if 'twm &' in line:
				xinitrc_data = xinitrc_data.replace(line, f'# {line}')
			if 'xclock' in line:
				xinitrc_data = xinitrc_data.replace(line, f'# {line}')
			if 'xterm' in line:
				xinitrc_data = xinitrc_data.replace(line, f'# {line}')

		xinitrc_data += '\n'
		xinitrc_data += 'exec awesome\n'

		with open(f'{install_session.target}/etc/X11/xinit/xinitrc', 'w') as xinitrc:
			xinitrc.write(xinitrc_data)
