from typing import TYPE_CHECKING, override

from nixinstall.default_profiles.profile import Profile, ProfileType

if TYPE_CHECKING:
	pass


class PostgresqlProfile(Profile):
	def __init__(self) -> None:
		super().__init__(
			'Postgresql',
			ProfileType.ServerType,
		)

	@property
	@override
	def packages(self) -> list[str]:
		return ['postgresql']
