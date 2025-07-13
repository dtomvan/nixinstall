import pytest

from .config import NixosConfig


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


def test_header() -> None:
	NixosConfig._instance = None

	a = NixosConfig()
	assert 'pkgs' not in a._repr(), "before beginning the factory should be empty"

	a.begin()
	assert 'pkgs' in a._repr(), "after beginning the factory should contain a pkgs import"


def test_full_config() -> None:
	NixosConfig._instance = None

	a = NixosConfig()
	a.begin()
	a.set("system.stateVersion", "25.05")
	a.set("time.timeZone", "Europe/Amsterdam")
	a.set("programs.less.enable", True)
	a.set_literal("environment.systemPackages", '''\
with pkgs; [
  nh
  btop
  git
  python3
]''')
	result = a.end()

	assert result == '''\
{ pkgs, lib, config, ... }: {

  system.stateVersion = "25.05";
  time.timeZone = "Europe/Amsterdam";
  programs.less.enable = true;
  environment.systemPackages = with pkgs; [
    nh
    btop
    git
    python3
  ];

}'''
