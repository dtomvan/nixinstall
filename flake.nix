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
            pkgs.makeBinaryWrapper
          ];

          buildInputs = with pkgs; [
            libxcrypt
            parted.dev
            pkg-config
            systemdLibs
          ];

          runtimeInputs = with pkgs; [
            # TODO: probably more
            nixos-install-tools
            nixos-enter
          ];

          devInputs = with pkgs; [
            python
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

            src = ./.;

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

            doInstallCheck = true;
            installCheckPhase = ''
              runHook preInstallCheck
                source ${pkgs.versionCheckHook}/nix-support/setup-hook
                versionCheckHook
              runHook postInstallCheck
            '';
          };

          checks =
            let
              mkCheck =
                tool: args:
                pkgs.runCommand "nixinstall-${tool}-check" {
                  nativeBuildInputs = devInputs ++ [
                    (python.withPackages (_: pythonPackages))
                  ];
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
              { lib, modulesPath, ... }:
              {
                imports = [ "${modulesPath}/installer/cd-dvd/installation-cd-minimal.nix" ];

                isoImage = {
                  edition = lib.mkForce "nixinstall";
                };
              }
            )
            nixosModules.default
          ];
        };
      };
    };
}
