{ pkgs ? import <nixpkgs> { } }:

with pkgs;

mkShellNoCC {
  nativeBuildInputs = [
    mypy
    flake8
  ];
}
