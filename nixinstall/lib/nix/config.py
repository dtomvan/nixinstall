from typing import Any, ClassVar, Self
from ..general import run


def python_to_nix(obj: Any) -> str:
    if isinstance(obj, dict):
        return "{ " + " ".join(f"{k} = {python_to_nix(v)};" for k, v in obj.items()) + " }"
    elif isinstance(obj, list):
        return "[ " + " ".join(python_to_nix(i) for i in obj) + " ]"
    elif isinstance(obj, str):
        return f"\"{obj}\""
    elif obj is True:
        return "true"
    elif obj is False:
        return "false"
    elif obj is None:
        return "null"
    else:
        return str(obj)


# This singleton state machine got a bit out of hand
class NixosConfig:
	"""
	Encompasses a single NixOS configuration.nix file. Used to do anything else
	in the installation procedure.
	"""
	_instance: ClassVar[Self | None] = None


	acc: str
	is_begun: bool
	is_finished: bool
	# not sus at all
	about_to_finish: bool
	set_keys: list[str]
	packages: list[str]


	def __new__(cls, *args: list[Any], **kwargs: list[Any]) -> Self:
		if cls._instance is None:
			cls._instance = super().__new__(cls)
		return cls._instance


	def __init__(self) -> None:
		self.acc = ""
		self.is_begun = False
		self.is_finished = False
		self.about_to_finish = False
		self.set_keys = []
		self.packages = []


	def _repr(self) -> str:
		return self.acc


	def begin(self) -> None:
		if self.is_begun:
			raise ValueError("Cannot begin config twice!")
		if self.is_finished:
			raise ValueError("We've finished the config without beginning, this is a miracle")
		self.acc += "{ pkgs, lib, config, ... }: {\n"
		self.is_begun = True


	def end(self) -> str:
		if not self.is_begun:
			raise ValueError("Never begun the config, cannot end")
		if self.is_finished:
			raise ValueError("Already finished the config, we're done here")

		self.about_to_finish = True

		pkgs = "\n".join([f'  {x}' for x in self.packages])
		self.comment("List of packages to install globally into the system.")
		self.comment("See https://search.nixos.org/")
		self.set_literal('environment.systemPackages', f'with pkgs; [\n{pkgs}\n]')

		# TODO: set system.stateVersion
		self.acc += "\n\n}"

		self.is_finished = True

		return self.acc


	def set_literal(self, key: str, value: str) -> None:
		if not self.is_begun:
			raise ValueError("Never begun the config, cannot set")
		if self.is_finished:
			raise ValueError("Cannot set anything after ending the config")
		if key in self.set_keys:
			raise ValueError(f'You have set {key} before, refusing to set again')
		if key == 'environment.systemPackages' and not self.about_to_finish:
			raise ValueError('Cannot directly set environment.systemPackages, use NixosConfig.install() instead')

		# indent for each line, not just the first line
		repr = f'{key} = {value};'
		repr = "\n".join([f'  {x}'.rstrip() for x in repr.split("\n")])

		self.acc += f'\n{repr}'
		self.set_keys += key


	def set(self, key: str, value: Any) -> None:
		# TODO: indirect keys, check if paths intersect
		return self.set_literal(key, python_to_nix(value))


	def install(self, packages: list[str]) -> None:
		if not self.is_begun:
			raise ValueError("Never begun the config, cannot install")
		if self.is_finished:
			raise ValueError("Cannot install anything after ending the config")

		# TODO: maybe check if they are all available???

		self.packages.extend(packages)

	# NOTE: begin check never set here, I am fine with commenting before the header
	def comment(self, what: str) -> None:
		indent = '  # ' if self.is_begun else '# '
		width = 80 - len(indent)
		chunks = [what[i:i+width] for i in range(0, len(what), width)]
		lines = "\n".join([f'{indent}{x}'.rstrip() for x in chunks])

		self.acc += f'\n{lines}'

		# if we haven't printed the header yet and we don't do this, we will
		# accidentally comment out the header
		if not self.is_begun:
			self.acc += '\n'


	def format(self) -> str:
		if not self.is_finished:
			raise ValueError("Cannot format if config isn't finished yet, nixfmt will fail for sure")

		output = run(["nixfmt"], input_data=self.acc.encode('utf-8')).stdout.decode()
		self.acc = output
		return output

