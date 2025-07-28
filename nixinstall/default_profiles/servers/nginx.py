from typing import override

from nixinstall.default_profiles.profile import Profile, ProfileType


class NginxProfile(Profile):
	def __init__(self) -> None:
		super().__init__(
			'Nginx',
			ProfileType.ServerType,
		)

	@property
	@override
	def packages(self) -> list[str]:
		return ['nginx']
