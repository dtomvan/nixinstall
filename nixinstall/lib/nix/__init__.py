from ..general import SysCommand


# returns outpath
def nix_build(package_name: str) -> str:
	return SysCommand(['nix-build', '<nixpkgs>', '--no-out-link', '-A', package_name]).decode().splitlines()[0]
