{
  description = "Archinstall fork for nixos";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-parts.url = "github:hercules-ci/flake-parts";
    treefmt-nix = {
      url = "github:numtide/treefmt-nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  outputs =
    inputs@{ self, flake-parts, ... }:
    flake-parts.lib.mkFlake { inherit inputs; } {
      imports = [
        inputs.treefmt-nix.flakeModule
      ];

      systems = [
        "x86_64-linux"
        # "aarch64-linux" not yet
      ];

      perSystem =
        {
          pkgs,
          ...
        }:
        let
          python = pkgs.python313;
          pythonPackages = with python.pkgs; [
            pyparted
            pydantic
            cryptography
            pytest
            pkgs.makeBinaryWrapper
          ];

          buildInputs = with pkgs; [
            libxcrypt
            parted
            parted.dev
            pkg-config
            systemdLibs
          ];

          runtimeInputs = with pkgs; [
            # TODO: probably more
            nixos-install-tools
            nixos-enter
            nixfmt-rfc-style
            libfido2
          ];

          devInputs = with pkgs; [
            (python.withPackages (_: pythonPackages))
            python.pkgs.ipython

            bandit
            mypy
            python.pkgs.pytest
            pylint
            ruff
            sphinx
            uv
          ];

          dependencies = pythonPackages ++ buildInputs;
        in
        {
          packages.default = python.pkgs.buildPythonApplication {
            pname = "nixinstall";
            version = "3.0.8";

            src = pkgs.lib.sourceFilesBySuffices ./. [
              ".py"
              ".toml"
              ".lock"
            ];

            pyproject = true;

            build-system = with python.pkgs; [
              setuptools
            ];

            inherit dependencies;

            postInstall = ''
              wrapProgram $out/bin/nixinstall \
                --prefix PATH : "${pkgs.lib.makeBinPath runtimeInputs}" \
                --prefix LD_LIBRARY_PATH : "${pkgs.lib.makeLibraryPath buildInputs}"
            '';

            # this is a bit of a hack, sadly required so pytestCheckHook can
            # work inside the sandbox due to the runtime loading
            preCheck = ''
              export PATH="${pkgs.lib.makeBinPath runtimeInputs}:$PATH"
              export LD_LIBRARY_PATH="${pkgs.lib.makeLibraryPath buildInputs}:$PATH"
            '';

            nativeCheckInputs = [
              python.pkgs.pytestCheckHook
              pkgs.versionCheckHook
            ];
          };

          checks =
            let
              mkCheck =
                tool: args:
                pkgs.runCommand "nixinstall-${tool}-check" {
                  nativeBuildInputs = devInputs;
                } "cd ${./.}; ${tool} ${args}";
            in
            pkgs.lib.mapAttrs mkCheck {
              bandit = "-r nixinstall";
            };

          devShells.default = pkgs.mkShell {
            env = {
              UV_NO_MANAGED_PYTHON = 1;
              LD_LIBRARY_PATH = "${pkgs.lib.makeLibraryPath buildInputs}";
            };

            packages = devInputs ++ buildInputs;

            shellHook = ''
              if ! [ -e "$(git rev-parse --show-toplevel)/.venv" ]; then
                uv venv
              fi

              source .venv/bin/activate
              uv sync --frozen --active --no-dev

              PATH="${pkgs.lib.makeBinPath runtimeInputs}:$PATH"
            '';
          };

          treefmt = {
            programs.nixfmt.enable = true;
            programs.ruff.enable = true;
            programs.mypy = {
              enable = true;
              directories.nixinstall = {
                extraPythonPackages = dependencies;
              };
            };
          };
        };

      flake = rec {
        nixosModules.default =
          { pkgs, ... }:
          {
            environment.systemPackages = [ self.packages.${pkgs.stdenv.hostPlatform.system}.default ];
          };

        nixosConfigurations.installer = inputs.nixpkgs.lib.nixosSystem {
          system = "x86_64-linux";
          modules = [
            (
              {
                lib,
                pkgs,
                modulesPath,
                ...
              }:
              {
                imports = [
                  "${modulesPath}/installer/cd-dvd/installation-cd-minimal.nix"
                  "${modulesPath}/installer/cd-dvd/channel.nix"
                ];

                environment.sessionVariables.NIX_PATH = lib.mkForce "nixpkgs=${pkgs.path}";

                isoImage = {
                  edition = lib.mkForce "nixinstall";
                  squashfsCompression = "gzip -Xcompression-level 1";
                };
              }
            )
            nixosModules.default
          ];
        };
      };
    };
}
