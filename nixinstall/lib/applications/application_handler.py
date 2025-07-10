from typing import TYPE_CHECKING

from nixinstall.applications.audio import AudioApp
from nixinstall.applications.bluetooth import BluetoothApp
from nixinstall.lib.models.application import ApplicationConfiguration
from nixinstall.lib.models.users import User

if TYPE_CHECKING:
	from nixinstall.lib.installer import Installer


class ApplicationHandler:
	def __init__(self) -> None:
		pass

	def install_applications(self, install_session: 'Installer', app_config: ApplicationConfiguration, users: list['User'] | None = None) -> None:
		if app_config.bluetooth_config:
			BluetoothApp().install(install_session)

		if app_config.audio_config:
			AudioApp().install(
				install_session,
				app_config.audio_config,
				users,
			)


application_handler = ApplicationHandler()
