# ops/

Ce qui sert à **exploiter** l'application, par opposition à ce qui la fait
tourner. Rien ici n'est nécessaire pour lancer TeamFollowUP : l'application
n'a aucune dépendance vers ce dossier.

| Chemin | Rôle |
|---|---|
| `prometheus/prometheus.yml` | configuration de collecte : où scraper, à quelle fréquence, comment s'authentifier |
| `prometheus/alerts.yml` | les sept règles d'alerte, chacune commentée : disponibilité, taux d'erreur, latence, saturation de la base, planificateur bloqué, pic d'échecs de connexion |
| `grafana/provisioning/datasources/prometheus.yml` | déclare la source de données Grafana, pour ne pas avoir à la créer à la main |
| `docker-compose.observability.yml` | une pile locale Prometheus + Grafana, à lancer à côté de l'application |

Démarrage, depuis la racine du dépôt :

```bash
docker compose -f ops/docker-compose.observability.yml up -d
```

Prometheus est alors sur http://localhost:9090 et Grafana sur
http://localhost:3000 (`admin` / `admin`).

**Le mode d'emploi complet est [`docs/17-observabilite.md`](../docs/17-observabilite.md)** :
ce que chaque métrique mesure, les requêtes PromQL à connaître, comment lire
chaque alerte quand elle se déclenche, comment protéger `/metrics`, et comment
transposer tout ça sur Kubernetes et sur GKE.
