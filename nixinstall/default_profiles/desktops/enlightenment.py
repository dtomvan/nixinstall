from typing import override

from nixinstall.default_profiles.profile import GreeterType, ProfileType
from nixinstall.default_profiles.xorg import XorgProfile


class EnlighenmentProfile(XorgProfile):
	def __init__(self) -> None:
		super().__init__('Enlightenment', ProfileType.WindowMgr)

	@property
	@override
	def packages(self) -> list[str]:
		return [
			'enlightenment',
			'terminology',
		]

	@property
	@override
	def default_greeter_type(self) -> GreeterType:
		return GreeterType.Lightdm
