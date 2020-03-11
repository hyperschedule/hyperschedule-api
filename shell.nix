{ pkgs ? import <nixos> {} }:
let
  chromeAlias = pkgs.stdenv.mkDerivation {
    name = "google-chrome";
    phases = ["buildPhase"];
    buildPhase = ''
      mkdir -p $out/bin
      ln -s ${pkgs.google-chrome}/bin/google-chrome-stable $out/bin/google-chrome
    '';
  };
in
pkgs.mkShell {
  buildInputs = 
    [chromeAlias] ++ (with pkgs; [
      chromedriver
      pipenv
      which
    ]) ++ (with pkgs.python37Packages; [
      beautifulsoup4
      flask
      gunicorn
      lxml
      dateutil
      selenium
      requests
      psutil
      frozendict
      flask-cors
      atomicwrites
      boto3
      flake8
    ]);
}
