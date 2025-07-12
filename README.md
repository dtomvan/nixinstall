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
- For now: translations. It's just me on my own right now, so I ripped all translation logic out right now. I might add it back later but that'll probably just as much of a burden as it initially was to introduce it for archinstall...

## Contributing
Not yet. I'll have to get this into a working state first.

TODO: make a [CONTRIBUTING.md](https://github.com/dtomvan/nixinstall/blob/master/CONTRIBUTING.md)
