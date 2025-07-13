"""NixOS installer - guided only, fork of archinstall"""

import importlib
import os
import sys
import traceback

from nixinstall.lib.args import arch_config_handler
from nixinstall.lib.disk.utils import disk_layouts

from .lib.hardware import SysInfo
from .lib.output import FormattedOutput, debug, error, info, log, warn
from .lib.pacman import Pacman
from .tui.curses_menu import Tui


def _log_sys_info() -> None:
	# Log various information about hardware before starting the installation. This might assist in troubleshooting
	debug(f'Hardware model detected: {SysInfo.sys_vendor()} {SysInfo.product_name()}; UEFI mode: {SysInfo.has_uefi()}')
	debug(f'Processor model detected: {SysInfo.cpu_model()}')
	debug(f'Memory statistics: {SysInfo.mem_available()} available out of {SysInfo.mem_total()} total installed')
	debug(f'Virtualization detected: {SysInfo.virtualization()}; is VM: {SysInfo.is_vm()}')
	debug(f'Graphics devices detected: {SysInfo._graphics_devices().keys()}')

	# For support reasons, we'll log the disk layout pre installation to match against post-installation layout
	debug(f'Disk states before installing:\n{disk_layouts()}')


def main() -> int:
	"""
	This can either be run as the compiled and installed application: python setup.py install
	OR straight as a module: python -m nixinstall
	In any case we will be attempting to load the provided script to be run from the scripts/ folder
	"""
	if '--help' in sys.argv or '-h' in sys.argv:
		arch_config_handler.print_help()
		return 0

	if os.getuid() != 0 and '--debug' not in sys.argv:
		print('nixinstall requires root privileges to run. See --help for more.')
		return 1

	_log_sys_info()

	script = arch_config_handler.get_script()

	mod_name = f'nixinstall.scripts.{script}'
	# by loading the module we'll automatically run the script
	importlib.import_module(mod_name)

	return 0


def run_as_a_module() -> None:
	rc = 0
	exc = None

	try:
		rc = main()
	except Exception as e:
		exc = e
	finally:
		# restore the terminal to the original state
		Tui.shutdown()

		if exc:
			err = ''.join(traceback.format_exception(exc))
			error(err)

			text = (
				'nixinstall experienced the above error. If you think this is a bug, please report it to\n'
				'https://github.com/dtomvan/nixinstall and include the log file "/var/log/nixinstall/install.log".\n\n'
				"Hint: To extract the log from a live ISO \ncurl -F'file=@/var/log/nixinstall/install.log' https://0x0.st\n"
			)

			warn(text)
			rc = 1

		exit(rc)


__all__ = [
	'FormattedOutput',
	'Pacman',
	'SysInfo',
	'Tui',
	'arch_config_handler',
	'debug',
	'disk_layouts',
	'error',
	'info',
	'log',
	'warn',
]
