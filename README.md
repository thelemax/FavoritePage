# FavoritePage

Page de liens favoris auto-hébergée. Les données (`config/data.yaml`) et le thème (`config/theme.yaml`) sont éditables depuis l'interface **ou** à la main.

## Prérequis

- Docker 24+
- Docker Compose v2

## Installation

```bash
git clone <url-du-depot> favoritepage
cd favoritepage
cp .env.example .env        # puis adapter les valeurs
mkdir -p config             # le fichier data.yaml y sera créé s'il n'existe pas
docker compose up -d --build
```

Accès : `http://<ip-du-serveur>:<PORT>` (par défaut `http://localhost:8000`).

## Configuration (`.env`)

| Variable     | Défaut     | Description                                                                      |
|--------------|------------|----------------------------------------------------------------------------------|
| `PORT`       | `8000`     | Port exposé sur l'hôte.                                                          |
| `CONFIG_DIR` | `./config` | Dossier de l'hôte monté sur `/config` dans le conteneur.                         |
| `PUID`       | `1000`     | UID utilisé par le conteneur (propriétaire des fichiers écrits dans `/config`).  |
| `PGID`       | `1000`     | GID utilisé par le conteneur.                                                    |

Sous Linux, récupérer ses identifiants avec `id -u` et `id -g`. Le dossier `CONFIG_DIR` doit être accessible en écriture par cet utilisateur.

## Volume `/config`

`docker-compose.yml` monte `${CONFIG_DIR}` sur `/config`. Il contient :

| Élément        | Rôle                                                                                          |
|----------------|-----------------------------------------------------------------------------------------------|
| `data.yaml`    | Colonnes, catégories, liens. Créé (3 colonnes vides) s'il est absent.                          |
| `theme.yaml`   | Apparence (colonnes, liens, tailles, couleurs, fond). Créé avec les valeurs par défaut.        |
| `fonds/`       | Images de fond (`jpg`, `png`, `webp`, `gif`, `avif`, `svg`) pour le mode fixe ou aléatoire.   |
| `icons/`       | Icônes personnalisées des liens (référencées par nom de fichier).                             |
| `cache/`       | Cache des favicons (peut être supprimé sans risque pour forcer leur rechargement).             |

Les fichiers peuvent être modifiés à la main pendant que le conteneur tourne : ils sont relus à chaque requête, il suffit de recharger la page. Un exemple est disponible dans [`doc/data.yaml`](doc/data.yaml).

`data.yaml` minimal :

```yaml
columns:
  - categories:
      - name: "Ma catégorie"
        links:
          - name: "Mon lien"
            url: "https://example.com"
            description: "Infobulle (optionnel)"
            hidden: true   # optionnel : visible uniquement en mode édition
            style:         # optionnel : surcharge du thème pour ce lien
              icon: "mon-icone.png"   # fichier de config/icons ou URL
              icon_size: 24           # px
              font_size: 16           # px
```

`theme.yaml` (valeurs par défaut) :

```yaml
columns: 3                 # 1 à 6
link:
  width:                   # vide = automatique, sinon largeur en px (40-600)
  show_icon: true
  show_name: true
  show_description: false
  icon_size: 16            # px (10-64)
fonts:                     # tailles de police en px
  link: 14                 # 8-32
  description: 11          # 8-32
  category: 15             # 8-40
colors:
  button: '#1c1e22'
  button_hover: '#464a50'
  text: '#f2f2f2'
  button_opacity: 0.88     # 0 à 1
  panel: '#14181e'
  panel_opacity: 0.45
background:
  mode: fixed              # fixed | random (image aléatoire de config/fonds à chaque chargement)
  image: ''                # nom de fichier de config/fonds ou URL
  attachment: fixed        # fixed | scroll
```

> Le conteneur doit pouvoir accéder aux sites des liens pour récupérer leurs favicons.

## Commandes utiles

```bash
docker compose logs -f              # logs
docker compose restart              # redémarrage
git pull && docker compose up -d --build   # mise à jour
docker compose down                 # arrêt
```

> Pas d'authentification : à n'exposer que sur un réseau local de confiance.


