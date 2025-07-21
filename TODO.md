## Menu items die het programma crashen
- [ ] Locales → locale language/encoding
- [ ] Mirrors (weggooien/vervangen door channels)
- [ ] Authentication (add libfido2?)
- [ ] Additional packages (duhh)
- [ ] Install

## Features die niet werken
- [ ] Install (moet `nixos-install` callen)
- [ ] Locales `i18n`
- [ ] Bootloader (redelijk 1:1 `boot.loader.*`)
- [ ] Hostname `networking.hostName`
- [ ] Root password `users.users.root.initialHashedPassword`
- [ ] Authentication `services.pam.yubico/boot.initrd.luks.devices.<name>.fido2.credentials`
- [ ] User account `users.users.*`
- [ ] Profile (vooral `environment.systemPackages`/`programs.*.enable`/`services.desktopManager`)
- [ ] Applications (`hardware.bluetooth.enable`+`services.blueman.enable`)/(`services.pipewire.enable`)/`services.pulseaudio`
- [ ] Kernels `boot.kernelPackages = pkgs.linuxPackages_*;`
- [ ] Network configuration → aan/uit maken, `services.networkmanager.enable`
- [ ] Additional packages → package list ergens anders vandaan halen, maar t zijn er sws te veel dus n freeform input van maken, wrappen in `environment.systemPackages = with pkgs; [ <> ];`
- [ ] Timezone 1:1 `time.timeZone`
- [ ] NTP → weggooien, we hadden al `services.timesyncd.enable`


## Overig
- [ ] Iets dat een nix file samenstelt:
	- Accumulate python dict
		- Serialize custom?
	- String append in een template?
	- JSON output → json2nix?
- [ ] CONTRIBUTING.md


## Install procedure
- partitioning
- `nixos-generate-config`
- overwrite `/mnt/etc/nixos/configuration.nix`
- `nixos-install`
