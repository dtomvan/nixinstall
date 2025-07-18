import time
from collections.abc import Callable
from pathlib import Path

from ..exceptions import RequirementError
from ..general import SysCommand
from ..output import error, info, warn


class Pacman:
	def __init__(self, target: Path, silent: bool = False):
		self.synced = False
		self.silent = silent
		self.target = target

	@staticmethod
	def run(args: str, default_cmd: str = 'pacman') -> SysCommand:
		"""
		A centralized function to call `pacman` from.
		It also protects us from colliding with other running pacman sessions (if used locally).
		The grace period is set to 10 minutes before exiting hard if another pacman instance is running.
		"""
		pacman_db_lock = Path('/var/lib/pacman/db.lck')

		if pacman_db_lock.exists():
			warn('Pacman is already running, waiting maximum 10 minutes for it to terminate.')

		started = time.time()
		while pacman_db_lock.exists():
			time.sleep(0.25)

			if time.time() - started > (60 * 10):
				error('Pre-existing pacman lock never exited. Please clean up any existing pacman sessions before using nixinstall.')
				exit(1)

		return SysCommand(f'{default_cmd} {args}')

	def ask(self, error_message: str, bail_message: str, func: Callable, *args, **kwargs) -> None:  # type: ignore[no-untyped-def, type-arg]
		while True:
			try:
				func(*args, **kwargs)
				break
			except Exception as err:
				error(f'{error_message}: {err}')
				if not self.silent and input('Would you like to re-try this download? (Y/n): ').lower().strip() in 'y':
					continue
				raise RequirementError(f'{bail_message}: {err}')

	# TODO: remove later
	def sync(self) -> None:
		warn("Sync called, this is a noop on NixOS")

	def strap(self, packages: str | list[str]) -> None:
		self.sync()
		if isinstance(packages, str):
			packages = [packages]

		info(f'Installing packages: {packages}')

		self.ask(
			'Could not strap in packages',
			'Pacstrap failed. See /var/log/nixinstall/install.log or above message for error details',
			SysCommand,
			f'pacstrap -C /etc/pacman.conf -K {self.target} {" ".join(packages)} --noconfirm',
			peek_output=True,
		)


__all__ = [
	'Pacman',
]
