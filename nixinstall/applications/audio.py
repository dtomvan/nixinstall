from typing import TYPE_CHECKING

from nixinstall.lib.hardware import SysInfo
from nixinstall.lib.models.application import Audio, AudioConfiguration
from nixinstall.lib.models.users import User
from nixinstall.lib.output import debug

if TYPE_CHECKING:
	from nixinstall.lib.installer import Installer


class AudioApp:
	@property
	def pulseaudio_packages(self) -> list[str]:
		return [
			'pulseaudio',
		]

	@property
	def pipewire_packages(self) -> list[str]:
		return [
			'pipewire',
			'pipewire-alsa',
			'pipewire-jack',
			'pipewire-pulse',
			'gst-plugin-pipewire',
			'libpulse',
			'wireplumber',
		]

	def _enable_pipewire(
		self,
		install_session: 'Installer',
		users: list['User'] | None = None,
	) -> None:
		if users is None:
			return

		for user in users:
			# Create the full path for enabling the pipewire systemd items
			service_dir = install_session.target / 'home' / user.username / '.config' / 'systemd' / 'user' / 'default.target.wants'
			service_dir.mkdir(parents=True, exist_ok=True)

	def install(
		self,
		install_session: 'Installer',
		audio_config: AudioConfiguration,
		users: list[User] | None = None,
	) -> None:
		debug(f'Installing audio server: {audio_config.audio.value}')

		if audio_config.audio == Audio.NO_AUDIO:
			debug('No audio server selected, skipping installation.')
			return

		if SysInfo.requires_sof_fw():
			install_session.add_additional_package('sof-firmware')

		if SysInfo.requires_alsa_fw():
			install_session.add_additional_package('alsa-firmware')

		match audio_config.audio:
			case Audio.PIPEWIRE:
				install_session.add_additional_packages(self.pipewire_packages)
				self._enable_pipewire(install_session, users)
			case Audio.PULSEAUDIO:
				install_session.add_additional_packages(self.pulseaudio_packages)
