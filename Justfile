default: build test lint

# Build a sdist and a wheel with uv
build:
    uv build .

# Run nixinstall in-place (will probably error because cannot run as root)
run +args="":
    uv pip install .
    uv run nixinstall --debug --offline {{args}}

# Run pytest
test +args="":
    uv tool run pytest

# Run all formatters and linters and check if no change is required
lint +args="":
    nix fmt -- --ci

# Run a vm with nixinstaller in it for manual testing
vm:
    nix run .#nixosConfigurations.installer.config.system.build.vm
