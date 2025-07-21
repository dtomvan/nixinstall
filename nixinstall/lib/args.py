import argparse
import json
import os
import urllib.error
import urllib.parse
from argparse import ArgumentParser, Namespace
from dataclasses import dataclass, field
from importlib.metadata import version
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

from pydantic.dataclasses import dataclass as p_dataclass

from nixinstall.lib.crypt import decrypt
from nixinstall.lib.models.application import ApplicationConfiguration
from nixinstall.lib.models.authentication import AuthenticationConfiguration
from nixinstall.lib.models.bootloader import Bootloader
from nixinstall.lib.models.device_model import DiskEncryption, DiskLayoutConfiguration
from nixinstall.lib.models.locale import LocaleConfiguration
from nixinstall.lib.models.network_configuration import NetworkConfiguration
from nixinstall.lib.models.profile_model import ProfileConfiguration
from nixinstall.lib.models.users import Password, User
from nixinstall.lib.output import debug, error, logger, warn
from nixinstall.lib.utils.util import get_password
from nixinstall.tui.curses_menu import Tui


@p_dataclass
class Arguments:
	config: Path | None = None
	config_url: str | None = None
	creds: Path | None = None
	creds_url: str | None = None
	creds_decryption_key: str | None = None
	silent: bool = False
	dry_run: bool = False
	script: str | None = None
	mountpoint: Path = Path('/mnt')
	debug: bool = False
	offline: bool = False
	no_pkg_lookups: bool = False
	skip_version_check: bool = False
	advanced: bool = False
	verbose: bool = False


@dataclass
class NixOSConfig:
	version: str | None = None
	script: str | None = None
	locale_config: LocaleConfiguration | None = None
	disk_config: DiskLayoutConfiguration | None = None
	profile_config: ProfileConfiguration | None = None
	network_config: NetworkConfiguration | None = None
	bootloader: Bootloader = field(default=Bootloader.get_default())
	uki: bool = False
	app_config: ApplicationConfiguration | None = None
	auth_config: AuthenticationConfiguration | None = None
	hostname: str = 'nixos'
	kernels: list[str] = field(default_factory=lambda: ['linux'])
	ntp: bool = True
	packages: list[str] = field(default_factory=list)
	parallel_downloads: int = 0
	swap: bool = True
	timezone: str = 'UTC'
	services: list[str] = field(default_factory=list)
	custom_commands: list[str] = field(default_factory=list)

	# Special fields that should be handle with care due to security implications
	users: list[User] = field(default_factory=list)
	root_enc_password: Password | None = None

	def unsafe_json(self) -> dict[str, Any]:
		config = {
			'users': [user.json() for user in self.users],
			'root_enc_password': self.root_enc_password.enc_password if self.root_enc_password else None,
		}

		if self.disk_config:
			disk_encryption = self.disk_config.disk_encryption
			if disk_encryption and disk_encryption.encryption_password:
				config['encryption_password'] = disk_encryption.encryption_password.plaintext

		return config

	def safe_json(self) -> dict[str, Any]:
		config: Any = {
			'version': self.version,
			'script': self.script,
			'hostname': self.hostname,
			'kernels': self.kernels,
			'ntp': self.ntp,
			'packages': self.packages,
			'parallel_downloads': self.parallel_downloads,
			'swap': self.swap,
			'timezone': self.timezone,
			'services': self.services,
			'custom_commands': self.custom_commands,
			'bootloader': self.bootloader.json(),
			'app_config': self.app_config.json() if self.app_config else None,
			'auth_config': self.auth_config.json() if self.auth_config else None,
		}

		if self.locale_config:
			config['locale_config'] = self.locale_config.json()

		if self.disk_config:
			config['disk_config'] = self.disk_config.json()

		if self.profile_config:
			config['profile_config'] = self.profile_config.json()

		if self.network_config:
			config['network_config'] = self.network_config.json()

		return config

	@classmethod
	def from_config(cls, args_config: dict[str, Any]) -> 'NixOSConfig':
		nixos_config = NixOSConfig()

		nixos_config.locale_config = LocaleConfiguration.parse_arg(args_config)

		if script := args_config.get('script', None):
			nixos_config.script = script

		if disk_config := args_config.get('disk_config', {}):
			enc_password = args_config.get('encryption_password', '')
			password = Password(plaintext=enc_password) if enc_password else None
			nixos_config.disk_config = DiskLayoutConfiguration.parse_arg(disk_config, password)

			# TODO: remove backwards compatibility with arch config like these
			# DEPRECATED
			# backwards compatibility for main level disk_encryption entry
			disk_encryption: DiskEncryption | None = None

			if args_config.get('disk_encryption', None) is not None and nixos_config.disk_config is not None:
				disk_encryption = DiskEncryption.parse_arg(
					nixos_config.disk_config,
					args_config['disk_encryption'],
					Password(plaintext=args_config.get('encryption_password', '')),
				)

				if disk_encryption:
					nixos_config.disk_config.disk_encryption = disk_encryption

		if profile_config := args_config.get('profile_config', None):
			nixos_config.profile_config = ProfileConfiguration.parse_arg(profile_config)

		if net_config := args_config.get('network_config', None):
			nixos_config.network_config = NetworkConfiguration.parse_arg(net_config)

		# DEPRECATED: backwards copatibility
		if users := args_config.get('!users', None):
			nixos_config.users = User.parse_arguments(users)

		if users := args_config.get('users', None):
			nixos_config.users = User.parse_arguments(users)

		if bootloader_config := args_config.get('bootloader', None):
			nixos_config.bootloader = Bootloader.from_arg(bootloader_config)

		if args_config.get('uki') and not nixos_config.bootloader.has_uki_support():
			nixos_config.uki = False

		# deprecated: backwards compatibility
		audio_config_args = args_config.get('audio_config', None)
		app_config_args = args_config.get('app_config', None)

		if audio_config_args is not None or app_config_args is not None:
			nixos_config.app_config = ApplicationConfiguration.parse_arg(app_config_args, audio_config_args)

		if auth_config_args := args_config.get('auth_config', None):
			nixos_config.auth_config = AuthenticationConfiguration.parse_arg(auth_config_args)

		if hostname := args_config.get('hostname', ''):
			nixos_config.hostname = hostname

		if kernels := args_config.get('kernels', []):
			nixos_config.kernels = kernels

		nixos_config.ntp = args_config.get('ntp', True)

		if packages := args_config.get('packages', []):
			nixos_config.packages = packages

		if parallel_downloads := args_config.get('parallel_downloads', 0):
			nixos_config.parallel_downloads = parallel_downloads

		nixos_config.swap = args_config.get('swap', True)

		if timezone := args_config.get('timezone', 'UTC'):
			nixos_config.timezone = timezone

		if services := args_config.get('services', []):
			nixos_config.services = services

		# DEPRECATED: backwards compatibility
		if root_password := args_config.get('!root-password', None):
			nixos_config.root_enc_password = Password(plaintext=root_password)

		if enc_password := args_config.get('root_enc_password', None):
			nixos_config.root_enc_password = Password(enc_password=enc_password)

		if custom_commands := args_config.get('custom_commands', []):
			nixos_config.custom_commands = custom_commands

		return nixos_config


class NixOSConfigHandler:
	def __init__(self) -> None:
		self._parser: ArgumentParser = self._define_arguments()
		self._args: Arguments = self._parse_args()

		config = self._parse_config()

		try:
			self._config = NixOSConfig.from_config(config)
		except ValueError as err:
			warn(str(err))
			exit(1)

	@property
	def config(self) -> NixOSConfig:
		return self._config

	@property
	def args(self) -> Arguments:
		return self._args

	def get_script(self) -> str:
		if script := self.args.script:
			return script

		if script := self.config.script:
			return script

		return 'guided'

	def print_help(self) -> None:
		self._parser.print_help()

	def _get_version(self) -> str:
		try:
			return version('nixinstall')
		except Exception:
			return 'nixinstall version not found'

	def _define_arguments(self) -> ArgumentParser:
		parser = ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)
		parser.add_argument(
			'-v',
			'--version',
			action='version',
			default=False,
			version='%(prog)s ' + self._get_version(),
		)
		parser.add_argument(
			'--config',
			type=Path,
			nargs='?',
			default=None,
			help='JSON configuration file',
		)
		parser.add_argument(
			'--config-url',
			type=str,
			nargs='?',
			default=None,
			help='Url to a JSON configuration file',
		)
		parser.add_argument(
			'--creds',
			type=Path,
			nargs='?',
			default=None,
			help='JSON credentials configuration file',
		)
		parser.add_argument(
			'--creds-url',
			type=str,
			nargs='?',
			default=None,
			help='Url to a JSON credentials configuration file',
		)
		parser.add_argument(
			'--creds-decryption-key',
			type=str,
			nargs='?',
			default=None,
			help='Decryption key for credentials file',
		)
		parser.add_argument(
			'--silent',
			action='store_true',
			default=False,
			help='WARNING: Disables all prompts for input and confirmation. If no configuration is provided, this is ignored',
		)
		parser.add_argument(
			'--dry-run',
			'--dry_run',
			action='store_true',
			default=False,
			help='Generates a configuration file and then exits instead of performing an installation',
		)
		parser.add_argument(
			'--script',
			nargs='?',
			help='Script to run for installation',
			type=str,
		)
		parser.add_argument(
			'--mountpoint',
			type=Path,
			nargs='?',
			default=Path('/mnt'),
			help='Define an alternate mount point for installation',
		)
		parser.add_argument(
			'--debug',
			action='store_true',
			default=False,
			help='Adds debug info into the log',
		)
		parser.add_argument(
			'--offline',
			action='store_true',
			default=False,
			help='Disabled online upstream services such as package search and key-ring auto update.',
		)
		parser.add_argument(
			'--no-pkg-lookups',
			action='store_true',
			default=False,
			help='Disabled package validation specifically prior to starting installation.',
		)
		parser.add_argument(
			'--advanced',
			action='store_true',
			default=False,
			help='Enabled advanced options',
		)
		parser.add_argument(
			'--verbose',
			action='store_true',
			default=False,
			help='Enabled verbose options',
		)

		return parser

	def _parse_args(self) -> Arguments:
		argparse_args = vars(self._parser.parse_args())
		args: Arguments = Arguments(**argparse_args)

		# amend the parameters (check internal consistency)
		# Installation can't be silent if config is not passed
		if args.config is None and args.config_url is None:
			args.silent = False

		if args.debug:
			warn(f'Warning: --debug mode will write certain credentials to {logger.path}!')

		if args.creds_decryption_key is None:
			if os.environ.get('ARCHINSTALL_CREDS_DECRYPTION_KEY'):
				args.creds_decryption_key = os.environ.get('ARCHINSTALL_CREDS_DECRYPTION_KEY')

		return args

	def _parse_config(self) -> dict[str, Any]:
		config: dict[str, Any] = {}
		config_data: str | None = None
		creds_data: str | None = None

		if self._args.config is not None:
			config_data = self._read_file(self._args.config)
		elif self._args.config_url is not None:
			config_data = self._fetch_from_url(self._args.config_url)

		if config_data is not None:
			config.update(json.loads(config_data))

		if self._args.creds is not None:
			creds_data = self._read_file(self._args.creds)
		elif self._args.creds_url is not None:
			creds_data = self._fetch_from_url(self._args.creds_url)

		if creds_data is not None:
			json_data = self._process_creds_data(creds_data)
			if json_data is not None:
				config.update(json_data)

		config = self._cleanup_config(config)

		return config

	def _process_creds_data(self, creds_data: str) -> dict[str, Any] | None:
		if creds_data.startswith('$'):  # encrypted data
			if self._args.creds_decryption_key is not None:
				try:
					creds_data = decrypt(creds_data, self._args.creds_decryption_key)
					return json.loads(creds_data)
				except ValueError as err:
					if 'Invalid password' in str(err):
						error('Incorrect credentials file decryption password')
						exit(1)
					else:
						debug(f'Error decrypting credentials file: {err}')
						raise err from err
			else:
				incorrect_password = False

				with Tui():
					while True:
						header = 'Incorrect password' if incorrect_password else None

						decryption_pwd = get_password(
							text='Credentials file decryption password',
							header=header,
							allow_skip=False,
							skip_confirmation=True,
						)

						if not decryption_pwd:
							return None

						try:
							creds_data = decrypt(creds_data, decryption_pwd.plaintext)
							break
						except ValueError as err:
							if 'Invalid password' in str(err):
								debug('Incorrect credentials file decryption password')
								incorrect_password = True
							else:
								debug(f'Error decrypting credentials file: {err}')
								raise err from err

		return json.loads(creds_data)

	def _fetch_from_url(self, url: str) -> str:
		if urllib.parse.urlparse(url).scheme:
			try:
				req = Request(url, headers={'User-Agent': 'nixinstall'})
				with urlopen(req) as resp:
					return resp.read().decode('utf-8')
			except urllib.error.HTTPError as err:
				error(f'Could not fetch JSON from {url}: {err}')
		else:
			error('Not a valid url')

		exit(1)

	def _read_file(self, path: Path) -> str:
		if not path.exists():
			error(f'Could not find file {path}')
			exit(1)

		return path.read_text()

	def _cleanup_config(self, config: Namespace | dict[str, Any]) -> dict[str, Any]:
		clean_args = {}
		for key, val in config.items():
			if isinstance(val, dict):
				val = self._cleanup_config(val)

			if val is not None:
				clean_args[key] = val

		return clean_args


nixos_config_handler: NixOSConfigHandler = NixOSConfigHandler()
