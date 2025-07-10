# NixOS Installer

This is a WIP fork of Archinstall. Do not use.

More docs will go here.

## Plans
- Use the exiting archinstall TUI and profiles
- Output a `configuration.nix`, not a `config.json`
- Reuse the archinstall partitioning driver
- Provide an ISO with `nixinstall` command, based off the official NixOS minimal ISO

## Non-plans
- Provide a library to make profiles with, because that's exactly what NixOS already does
- Support deploying certain credentials (code still present but will be removed), use sops-nix or agenix instead

## Contributing
Not yet. I'll have to get this into a working state first.

TODO: make a [CONTRIBUTING.md](https://github.com/dtomvan/nixinstall/blob/master/CONTRIBUTING.md)
