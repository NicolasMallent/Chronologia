# Confidentialité et données personnelles (RGPD)

Chronologia est une application **locale** : elle ne transmet aucune donnée à qui que ce soit.

## Qui traite quoi

Les fichiers CSV que vous ouvrez peuvent contenir des données personnelles (noms de personnes,
dates liées à des individus...). Elles sont lues et affichées **uniquement sur votre ordinateur**.
Le développeur de l'application n'y a jamais accès : il n'est ni responsable de traitement ni
sous-traitant pour ces données. **Vous** (ou votre organisation) restez responsable des fichiers
que vous créez, enregistrez, exportez ou partagez.

## Ce que l'application ne fait pas

- aucun accès réseau : pas de télémétrie, pas de statistiques d'usage, pas de rapport de plantage,
  pas de mise à jour automatique, pas de compte ;
- aucun cookie, aucun identifiant, aucune publicité ;
- aucun historique de fichiers récents, aucun journal d'activité.

Ces points sont vérifiés par des tests automatiques (`tests/test_security.py`) : aucun module réseau
dans le code, et le module réseau de Qt n'est jamais chargé pendant une session complète.

## Ce qui est écrit sur votre disque

| Quoi | Où | Quand |
|------|----|-------|
| CSV et PDF que vous enregistrez ou exportez | l'emplacement que vous choisissez | à votre demande uniquement |
| Fichiers temporaires `*.tmp` (écriture atomique) | à côté du fichier cible | supprimés aussitôt, y compris en cas d'erreur |
| Langue de l'interface et raccourcis clavier que vous personnalisez | Linux : `~/.config/Chronologia/Chronologia.conf` ; Windows : registre `HKEY_CURRENT_USER\Software\Chronologia` | quand vous choisissez une langue ou modifiez un raccourci (Fichier › Préférences) |
| Catégories personnalisées (nom, couleur) | Linux : `~/.config/chronologia/categories.json` ; Windows : `%APPDATA%\chronologia\categories.json` | quand vous enregistrez vos catégories |

L'historique d'annulation reste en mémoire et disparaît à la fermeture.

## Contenu des PDF exportés

Un PDF contient les titres, dates et couleurs des événements affichés, ainsi que le titre que vous
saisissez. Ses métadonnées contiennent « Chronologia » comme créateur, la version de Qt et la date de
création. Elles ne contiennent **ni nom d'utilisateur, ni nom de machine, ni chemin de fichier**
(vérifié par test). Avant de diffuser un PDF ou un CSV, vérifiez qu'il ne contient pas de données
personnelles que vous n'avez pas le droit de partager.

## Effacer vos données

L'application ne conserve rien d'autre que ce qui est listé ci-dessus. Pour tout effacer, supprimez
vos fichiers CSV/PDF, le dossier `chronologia` de la configuration et la clé de registre ou le fichier
`Chronologia.conf` (langue et raccourcis). Les droits d'accès, de rectification et d'effacement ne s'exercent
pas auprès du développeur, qui ne détient aucune donnée vous concernant.

## Distribution

Les installateurs sont publiés sur GitHub. Le téléchargement est soumis à la politique de
confidentialité de GitHub (adresse IP, statistiques de téléchargement) : cela ne concerne pas
l'application elle-même.

## Limites

Les boîtes de dialogue d'ouverture et d'enregistrement de fichiers sont fournies par le système
d'exploitation (par exemple pour parcourir des dossiers réseau) : leur comportement relève du système.
