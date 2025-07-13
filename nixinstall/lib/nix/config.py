from typing import Any, ClassVar, Self


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


class NixosConfig:
	_instance: ClassVar[Self | None] = None


	acc: str
	is_begun: bool
	is_finished: bool
	set_keys: list[str]


	def __new__(cls, *args: list[Any], **kwargs: list[Any]) -> Self:
		if cls._instance is None:
			cls._instance = super().__new__(cls)
		return cls._instance


	def __init__(self) -> None:
		self.acc = ""
		self.is_begun = False
		self.is_finished = False
		self.set_keys = []


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
		# TODO: set system.stateVersion
		self.acc += "\n\n}"

		self.is_finished = True

		# TODO: run through nixfmt
		return self.acc


	def set_literal(self, key: str, value: str) -> None:
		if not self.is_begun:
			raise ValueError("Never begun the config, cannot set")
		if key in self.set_keys:
			raise ValueError(f'You have set {key} before, refusing to set again')

		# indent for each line, not just the first line
		repr = f'{key} = {value};'
		repr = "\n".join([f'  {x}' for x in repr.split("\n")])

		self.acc += f'\n{repr}'
		self.set_keys += key

	def set(self, key: str, value: Any) -> None:
		# TODO: indirect keys, check if paths intersect
		return self.set_literal(key, python_to_nix(value))

