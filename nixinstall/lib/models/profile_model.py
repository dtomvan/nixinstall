from __future__ import annotations

from dataclasses import dataclass
from typing import TypedDict

from nixinstall.default_profiles.profile import GreeterType, Profile

from ..hardware import GfxDriver


class _ProfileConfigurationSerialization(TypedDict):
	profile: str
	gfx_driver: str | None
	greeter: str | None


@dataclass
class ProfileConfiguration:
	profile: Profile | None = None
	gfx_driver: GfxDriver | None = None
	greeter: GreeterType | None = None

	@classmethod
	def parse_arg(cls, arg: _ProfileConfigurationSerialization) -> 'ProfileConfiguration':
		from ..profile.profiles_handler import profile_handler

		profile = profile_handler.get_profile_by_name(arg['profile'])
		greeter = arg.get('greeter', None)
		gfx_driver = arg.get('gfx_driver', None)

		return ProfileConfiguration(
			profile,
			GfxDriver(gfx_driver) if gfx_driver else None,
			GreeterType(greeter) if greeter else None,
		)
