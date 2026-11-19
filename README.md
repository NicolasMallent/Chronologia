# Chronologia
Timeline visualisation - Transform your CSV into a banner for your seminar and presentation

## Développement
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python -m chronologia input_claude/exemple_timeline.csv
pytest
```
Sous Linux, Qt (X11) demande `libxcb-cursor0` : `sudo apt install libxcb-cursor0`.

## Publier une version
Les paquets ne sont construits **que lorsqu'une release GitHub est publiée** (workflow `release.yml`) ;
les push et pull requests ne lancent que les tests (`ci.yml`).

1. Mettre à jour la version dans `pyproject.toml` **et** `src/chronologia/__init__.py`.
2. Commiter, puis créer sur GitHub une release avec le tag `vX.Y.Z` (même numéro) et la publier.
3. Le workflow vérifie la cohérence des versions et lance les tests, construit
   `chronologia_X.Y.Z_amd64.deb` (Debian 12+ / Ubuntu 22.04+) et `Chronologia-Setup-X.Y.Z.exe`
   (Windows 11), vérifie chaque paquet avec `--smoke-test`, puis les joint à la release avec leur
   empreinte SHA-256 (`*.sha256`).

Construction locale du `.deb` : `pip install -r packaging/requirements-build.txt`,
`pyinstaller --noconfirm --clean packaging/chronologia.spec`, puis
`packaging/deb/build_deb.sh X.Y.Z`.

## Confidentialité et sécurité
L'application est locale, sans télémétrie ni accès réseau : voir [PRIVACY.md](PRIVACY.md) (RGPD) et
[SECURITY.md](SECURITY.md) (mesures, limites, signalement d'une vulnérabilité).
