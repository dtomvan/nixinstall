from typing import TYPE_CHECKING, override

from nixinstall.default_profiles.profile import Profile, ProfileType

if TYPE_CHECKING:
	from nixinstall.lib.installer import Installer


class DockerProfile(Profile):
	def __init__(self) -> None:
		super().__init__(
			'Docker',
			ProfileType.ServerType,
		)

	@property
	@override
	def packages(self) -> list[str]:
		return ['docker']

	@override
	def post_install(self, install_session: 'Installer') -> None:
		from nixinstall.lib.args import nixos_config_handler

		for user in nixos_config_handler.config.users:
			install_session.set_additional_option(f'users.users."{user.username}".extraGroups', ['docker'])
