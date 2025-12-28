{
  description = "TriceraPost dev shell";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
  };

  outputs = { self, nixpkgs }:
    let
      system = "x86_64-linux";
      pkgs = import nixpkgs { inherit system; };
      lib = pkgs.lib;
      src = ./.;
      hasWasm = builtins.pathExists (toString src + "/parsers/overview/build.sh");
    in {
      devShells.${system}.default = pkgs.mkShell {
        packages = with pkgs; [
          python313
          python313Packages.pip
          wasmtime
          go
          nodejs
          sqlite
          nzbget
          zig
        ];
        shellHook = ''
          if [ ! -d .venv ]; then
            python3.13 -m venv .venv
          fi
          . .venv/bin/activate
          python3.13 - <<'PY'
try:
    import wasmtime  # noqa: F401
except Exception:
    raise SystemExit(1)
PY
          if [ $? -ne 0 ]; then
            pip install wasmtime
          fi
        '';
      };
      checks.${system} = {
        pipeline-tests = pkgs.runCommand "tricerapost-pipeline-tests" {
          src = src;
          nativeBuildInputs = [
            pkgs.python313
          ];
        } ''
          cp -r "$src" source
          chmod -R u+w source
          cd source
          ${pkgs.python313}/bin/python -m unittest tests.test_pipeline
          mkdir -p "$out"
        '';
      } // lib.optionalAttrs hasWasm {
        wasm-build = pkgs.runCommand "tricerapost-wasm-build" {
          src = src;
          nativeBuildInputs = [
            pkgs.bash
            pkgs.zig
          ];
        } ''
          cp -r "$src" source
          chmod -R u+w source
          cd source
          export ZIG_GLOBAL_CACHE_DIR="${TMPDIR:-/tmp}/zig-cache"
          ${pkgs.bash}/bin/bash ./parsers/overview/build.sh
          test -f parsers/overview/wasm/pipeline.wasm
          mkdir -p "$out"
        '';
      };
    };
}
