from functools import cache

from ..exceptions import ServiceException, SysCallError
from ..general import SysCommand
from ..nix import nix_build
from ..output import error


@cache
def list_keyboard_languages() -> list[str]:
	kbd = nix_build('kbd')
	keymap_directory = f'{kbd}/share/keymaps'

	return (
		SysCommand(
			'localectl --no-pager list-keymaps',
			environment_vars={'SYSTEMD_COLORS': '0', 'SYSTEMD_KEYMAP_DIRECTORIES': keymap_directory},
		)
		.decode()
		.splitlines()
	)


@cache
def list_locales() -> list[str]:
	# FIXME: see https://github.com/NixOS/nixpkgs/issues/267101#issuecomment-2284844496
	glibc_locales = nix_build('glibcLocales')
	locale_archive = f'{glibc_locales}/lib/locale/locale-archive'

	return (
		SysCommand(
			'localectl --no-pager list-locales',
			environment_vars={'SYSTEMD_COLORS': '0', 'LOCALE_ARCHIVE': locale_archive},
		)
		.decode()
		.splitlines()
	)


def list_x11_keyboard_languages() -> list[str]:
	# TODO: probe whether this works on a minimal ISO and what we would need to
	# do to fix it
	return (
		SysCommand(
			'localectl --no-pager list-x11-keymap-layouts',
			environment_vars={'SYSTEMD_COLORS': '0'},
		)
		.decode()
		.splitlines()
	)


def verify_keyboard_layout(layout: str) -> bool:
	for language in list_keyboard_languages():
		if layout.lower() == language.lower():
			return True
	return False


def verify_x11_keyboard_layout(layout: str) -> bool:
	for language in list_x11_keyboard_languages():
		if layout.lower() == language.lower():
			return True
	return False


def get_kb_layout() -> str:
	try:
		lines = (
			SysCommand(
				'localectl --no-pager status',
				environment_vars={'SYSTEMD_COLORS': '0'},
			)
			.decode()
			.splitlines()
		)
	except Exception:
		return ''

	vcline = ''
	for line in lines:
		if 'VC Keymap: ' in line:
			vcline = line

	if vcline == '':
		return ''

	layout = vcline.split(': ')[1]
	if not verify_keyboard_layout(layout):
		return ''

	return layout


def set_kb_layout(locale: str) -> bool:
	if len(locale.strip()):
		if not verify_keyboard_layout(locale):
			error(f'Invalid keyboard locale specified: {locale}')
			return False

		# Failed to set keymap: Changing system settings via systemd is not supported on NixOS.
		# FIXME: it cannot be done in-place on the system. Would we actually
		# have to rebuild the system or can we change it on-the-fly in SOME
		# way?
		try:
			SysCommand(f'loadkeys {locale}')
		except SysCallError as err:
			raise ServiceException(f"Unable to set locale '{locale}' for console: {err}")

		return True

	return False


def list_timezones() -> list[str]:
	return (
		SysCommand(
			'timedatectl --no-pager list-timezones',
			environment_vars={'SYSTEMD_COLORS': '0'},
		)
		.decode()
		.splitlines()
	)
