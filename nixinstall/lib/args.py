import argparse
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

from nixinstall.lib.models.application import ApplicationConfiguration
from nixinstall.lib.models.authentication import AuthenticationConfiguration
from nixinstall.lib.models.bootloader import Bootloader
from nixinstall.lib.models.device_model import DiskLayoutConfiguration
from nixinstall.lib.models.locale import LocaleConfiguration
from nixinstall.lib.models.network_configuration import NetworkConfiguration
from nixinstall.lib.models.profile_model import ProfileConfiguration
from nixinstall.lib.models.users import Password, User
from nixinstall.lib.output import error, logger, warn


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


class NixOSConfigHandler:
	def __init__(self) -> None:
		self._parser: ArgumentParser = self._define_arguments()
		self._args: Arguments = self._parse_args()
		self._config = NixOSConfig()

	@property
	def config(self) -> NixOSConfig:
		return self._config

	@property
	def args(self) -> Arguments:
		return self._args

	def get_script(self) -> str:
		# TODO: this can probably get inlined
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
