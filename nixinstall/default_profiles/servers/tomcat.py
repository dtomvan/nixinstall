from typing import override

from nixinstall.default_profiles.profile import Profile, ProfileType


class TomcatProfile(Profile):
	def __init__(self) -> None:
		super().__init__(
			'Tomcat',
			ProfileType.ServerType,
		)

	@property
	@override
	def packages(self) -> list[str]:
		return ['tomcat10']
