{
  description = "TriceraPost dev shell";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
  };

  outputs = { self, nixpkgs }:
    let
      system = "x86_64-linux";
      pkgs = import nixpkgs { inherit system; };
    in {
      devShells.${system}.default = pkgs.mkShell {
        packages = with pkgs; [
          python3
          python3Packages.pip
          go
          nodejs
          (roc.overrideAttrs (_: { doCheck = false; }))
          sqlite
          nzbget
        ];
      };
    };
}
