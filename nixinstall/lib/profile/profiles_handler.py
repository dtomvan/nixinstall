from __future__ import annotations

import importlib.util
import inspect
import sys
from collections import Counter
from functools import cached_property
from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING

from ...default_profiles.profile import GreeterType, Profile
from ..hardware import GfxDriver
from ..models.profile_model import ProfileConfiguration
from ..networking import list_interfaces
from ..output import debug, error, info

if TYPE_CHECKING:
	from ..installer import Installer


class ProfileHandler:
	def __init__(self) -> None:
		self._profiles: list[Profile] | None = None

		# special variable to keep track of a profile url configuration
		# it is merely used to be able to export the path again when a user
		# wants to save the configuration
		self._url_path: str | None = None

	@property
	def profiles(self) -> list[Profile]:
		"""
		List of all available default_profiles
		"""
		self._profiles = self._profiles or self._find_available_profiles()
		return self._profiles

	@cached_property
	def _local_mac_addresses(self) -> list[str]:
		return list(list_interfaces())

	def get_profile_by_name(self, name: str) -> Profile | None:
		return next(filter(lambda x: x.name == name, self.profiles), None)  # type: ignore[arg-type, union-attr]

	def get_top_level_profiles(self) -> list[Profile]:
		return [p for p in self.profiles if p.is_top_level_profile()]

	def get_server_profiles(self) -> list[Profile]:
		return [p for p in self.profiles if p.is_server_type_profile()]

	def get_desktop_profiles(self) -> list[Profile]:
		return [p for p in self.profiles if p.is_desktop_type_profile()]

	def get_mac_addr_profiles(self) -> list[Profile]:
		tailored = [p for p in self.profiles if p.is_tailored()]
		return [t for t in tailored if t.name in self._local_mac_addresses]

	def install_greeter(self, install_session: 'Installer', greeter: GreeterType) -> None:
		match greeter:
			case GreeterType.LightdmSlick:
				error('GreeterType.LightdmSlick not implemented yet')
			case GreeterType.Lightdm:
				error('GreeterType.Lightdm not implemented yet')
			case GreeterType.Sddm:
				error('GreeterType.Sddm not implemented yet')
			case GreeterType.Gdm:
				error('GreeterType.Gdm not implemented yet')
			case GreeterType.Ly:
				error('GreeterType.Ly not implemented yet')
			case GreeterType.CosmicSession:
				error('GreeterType.CosmicSession not implemented yet')

	def install_gfx_driver(self, install_session: 'Installer', driver: GfxDriver) -> None:
		debug(f'Installing GFX driver: {driver.value}')
		error('install_gfx_driver not implemented yet')

	def install_profile_config(self, install_session: 'Installer', profile_config: ProfileConfiguration) -> None:
		profile = profile_config.profile

		if not profile:
			return

		profile.install(install_session)

		if profile_config.gfx_driver and (profile.is_xorg_type_profile() or profile.is_desktop_profile()):
			self.install_gfx_driver(install_session, profile_config.gfx_driver)

		if profile_config.greeter:
			self.install_greeter(install_session, profile_config.greeter)

	def _load_profile_class(self, module: ModuleType) -> list[Profile]:
		"""
		Load all default_profiles defined in a module
		"""
		profiles = []
		for v in module.__dict__.values():
			if isinstance(v, type) and v.__module__ == module.__name__:
				bases = inspect.getmro(v)

				if Profile in bases:
					try:
						cls_ = v()
						if isinstance(cls_, Profile):
							profiles.append(cls_)
					except Exception:
						debug(f'Cannot import {module}, it does not appear to be a Profile class')

		return profiles

	def _verify_unique_profile_names(self, profiles: list[Profile]) -> None:
		"""
		All profile names have to be unique, this function will verify
		that the provided list contains only default_profiles with unique names
		"""
		counter = Counter([p.name for p in profiles])
		duplicates = [x for x in counter.items() if x[1] != 1]

		if len(duplicates) > 0:
			err = f'Profiles must have unique name, but profile definitions with duplicate name found: {duplicates[0][0]}'
			error(err)
			sys.exit(1)

	def _is_legacy(self, file: Path) -> bool:
		"""
		Check if the provided profile file contains a
		legacy profile definition
		"""
		with open(file) as fp:
			for line in fp.readlines():
				if '__packages__' in line:
					return True
		return False

	def _process_profile_file(self, file: Path) -> list[Profile]:
		"""
		Process a file for profile definitions
		"""
		if self._is_legacy(file):
			info(f'Cannot import {file} because it is no longer supported, please use the new profile format')
			return []

		if not file.is_file():
			info(f'Cannot find profile file {file}')
			return []

		name = file.name.removesuffix(file.suffix)
		debug(f'Importing profile: {file}')

		try:
			if spec := importlib.util.spec_from_file_location(name, file):
				imported = importlib.util.module_from_spec(spec)
				if spec.loader is not None:
					spec.loader.exec_module(imported)
					return self._load_profile_class(imported)
		except Exception as e:
			error(f'Unable to parse file {file}: {e}')

		return []

	def _find_available_profiles(self) -> list[Profile]:
		"""
		Search the profile path for profile definitions
		"""
		profiles_path = Path(__file__).parents[2] / 'default_profiles'
		profiles = []
		for file in profiles_path.glob('**/*.py'):
			# ignore the abstract default_profiles class
			if 'profile.py' in file.name:
				continue
			profiles += self._process_profile_file(file)

		self._verify_unique_profile_names(profiles)
		return profiles

	def reset_top_level_profiles(self, exclude: list[Profile] = []) -> None:
		"""
		Reset all top level profile configurations, this is usually necessary
		when a new top level profile is selected
		"""
		excluded_profiles = [p.name for p in exclude]
		for profile in self.get_top_level_profiles():
			if profile.name not in excluded_profiles:
				profile.reset()


profile_handler = ProfileHandler()
