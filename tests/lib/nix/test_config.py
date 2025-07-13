import pytest

from nixinstall.lib.nix.config import NixosConfig


def test_is_singleton() -> None:
	NixosConfig._instance = None
	a = NixosConfig()
	b = NixosConfig()
	assert a is b, "NixosConfig is a singleton"


@pytest.mark.xfail(strict=True)
def test_double_begin() -> None:
	NixosConfig._instance = None
	config = NixosConfig()
	config.begin()
	config.begin()


@pytest.mark.xfail(strict=True)
def test_end_before_begin() -> None:
	NixosConfig._instance = None
	config = NixosConfig()
	config.end()


@pytest.mark.xfail(strict=True)
def test_double_end() -> None:
	NixosConfig._instance = None
	config = NixosConfig()
	config.begin()
	config.end()
	config.end()


@pytest.mark.xfail(strict=True)
def test_set_before_begin() -> None:
	NixosConfig._instance = None

	a = NixosConfig()
	a.set("system.stateVersion", "25.05")


@pytest.mark.xfail(strict=True)
def test_set_after_end() -> None:
	NixosConfig._instance = None

	a = NixosConfig()
	a.begin()
	a.end()
	a.set("system.stateVersion", "25.05")


@pytest.mark.xfail(strict=True)
def test_format_before_end() -> None:
	NixosConfig._instance = None

	a = NixosConfig()
	a.begin()
	a.set("system.stateVersion", "25.05")
	a.format()


def test_header() -> None:
	NixosConfig._instance = None

	a = NixosConfig()
	assert 'pkgs' not in a._repr(), "before beginning the factory should be empty"

	a.begin()
	assert 'pkgs' in a._repr(), "after beginning the factory should contain a pkgs import"


def test_empty_config() -> None:
	NixosConfig._instance = None
	expected_result = '''\
{ pkgs, lib, config, ... }: {

  # List of packages to install globally into the system.
  # See https://search.nixos.org/
  environment.systemPackages = with pkgs; [

  ];

}'''

	a = NixosConfig()
	a.begin()
	a.end()

	assert a._repr() == expected_result


expected_result = '''\
{ pkgs, lib, config, ... }: {

  # Please never change this variable, it is the only bit of state the nix code
  # can get, protect it at all costs, foo bar baz, am I at 80 characters yet????
  system.stateVersion = "25.05";
  time.timeZone = "Europe/Amsterdam";
  programs.less.enable = true;
  # List of packages to install globally into the system.
  # See https://search.nixos.org/
  environment.systemPackages = with pkgs; [
    nh
    btop
    git
    python3
  ];

}'''

def get_full_config() -> NixosConfig:
	NixosConfig._instance = None

	a = NixosConfig()
	a.begin()
	a.comment("Please never change this variable, it is the only bit of state the nix code can get, protect it at all costs, foo bar baz, am I at 80 characters yet????")
	a.install(['nh', 'btop'])
	a.set("system.stateVersion", "25.05")
	a.set("time.timeZone", "Europe/Amsterdam")
	a.set("programs.less.enable", True)
	a.install(['git', 'python3'])
	a.end()
	return a


def test_full_config() -> None:
	assert get_full_config()._repr() == expected_result


def test_formatter() -> None:
	a = get_full_config()

	prev = str(a._repr())
	result = str(a.format())
	result2 = str(a.format())

	# we will not be testing any formatter behaviour, just these 3 base rules
	assert result != prev, "the formatting will for sure change something in the config"
	assert prev == expected_result
	assert result == result2, "formatter should be relatively consistent"
