# Sécurité

## Signaler une vulnérabilité

Utilisez le signalement privé de GitHub (onglet **Security** → **Report a vulnerability**) plutôt
qu'une issue publique. Seule la dernière version publiée est maintenue.

## Principales mesures

Le CSV ouvert est considéré comme une **entrée non fiable**.

| Risque | Mesure |
|--------|--------|
| Fichier CSV démesuré ou piégé | lecture bornée à 20 Mo (un fichier spécial comme `/dev/zero` ne sature pas la mémoire), champ et fichier mal formés refusés proprement, 5 000 événements maximum, titres limités à 500 caractères et sources à 5 000 |
| HTML dans un titre ou une source (`<img ...>`) | texte échappé dans les info-bulles et boîtes de message (`textutil.plain`) |
| Injection de formule dans un tableur (`=`, `+`, `-`, `@`) | une apostrophe est ajoutée à l'export CSV et retirée à la relecture |
| Fichier tronqué en cas d'erreur ou de coupure | écritures atomiques (CSV, PDF, configuration) ; droits de l'ancien fichier conservés |
| Configuration corrompue ou démesurée | repli sur les valeurs par défaut (1 Mo et 500 catégories maximum), fichier non écrasé |
| Exfiltration de données | aucun accès réseau, aucun module de lancement de processus ou de code dynamique (vérifié par test) |
| Dépendances vulnérables | versions de build épinglées (`packaging/requirements-build.txt`), `pip-audit` et `bandit` à chaque push et chaque lundi |
| Chaîne de livraison | actions GitHub épinglées par empreinte de commit, permissions minimales, pas de `pull_request_target`, données de l'événement passées par variables d'environnement, tag vérifié (`vX.Y.Z` = version du projet), empreintes SHA-256 jointes aux paquets, installation de chaque paquet testée (`--smoke-test`) |

## Limites connues

- Les installateurs ne sont **pas signés** : Windows SmartScreen affichera un avertissement. Vérifiez
  l'empreinte SHA-256 jointe à la release.
- Pas de dépôt apt signé : le `.deb` s'installe depuis le fichier téléchargé.
- Les dépendances indirectes de PySide6 ne sont pas verrouillées individuellement (elles sont
  contraintes par la version de PySide6).
- L'apostrophe ajoutée contre l'injection de formule peut apparaître dans un tableur qui ne
  l'interprète pas comme marqueur de texte ; Chronologia la retire à la relecture.
- Le texte d'un PDF reste lisible par tout lecteur de PDF : ne l'utilisez pas pour masquer une
  information.
