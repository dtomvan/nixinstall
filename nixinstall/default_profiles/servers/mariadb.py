from typing import TYPE_CHECKING, override

from nixinstall.default_profiles.profile import Profile, ProfileType

if TYPE_CHECKING:
	pass


class MariadbProfile(Profile):
	def __init__(self) -> None:
		super().__init__(
			'Mariadb',
			ProfileType.ServerType,
		)

	@property
	@override
	def packages(self) -> list[str]:
		return ['mariadb']

	@property
	@override
	def services(self) -> list[str]:
		return ['mariadb']
