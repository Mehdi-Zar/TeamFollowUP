# 19 - Plan de reprise : sauvegardes, restauration, exercices

Une sauvegarde qu'on n'a jamais restaurée n'est pas une sauvegarde, c'est une
rumeur. Ce document donne la procédure de restauration **telle qu'elle a été
exécutée**, pas telle qu'on l'imagine, et l'exercice qui permet de vérifier
qu'elle marche encore, sans toucher aux données de production.

---

## 1. Objectifs, et ce qu'ils coûtent

Deux chiffres à décider avant toute chose, parce qu'ils dictent le reste :

| Terme | Ce que ça veut dire | Ce que donne la configuration livrée |
|---|---|---|
| **RPO** (Recovery Point Objective) | combien de données on accepte de perdre | **24 h** : le sidecar sauvegarde une fois par jour (`BACKUP_INTERVAL_SECONDS=86400`) |
| **RTO** (Recovery Time Objective) | combien de temps on accepte d'être arrêté | **environ 15 minutes** pour une base de cette taille, dont l'essentiel est le chargement du dump |

Ces valeurs sont des **choix par défaut**, pas des fatalités.

- Pour un RPO plus court, baissez `BACKUP_INTERVAL_SECONDS` (4 h : `14400`). Un dump
  logique de cette base pèse quelques mégaoctets et prend quelques secondes, donc
  sauvegarder plus souvent coûte très peu.
- Pour un RPO proche de zéro, il faut autre chose que des dumps : la
  **restauration à un instant précis** (PITR) de votre base managée, Cloud SQL ou
  autre. Voir §7.

---

## 2. Ce qui sauvegarde, et comment le vérifier

Le service `backup` de `docker-compose.yml` est un conteneur PostgreSQL qui lance
`pg_dump` en boucle. Il est **optionnel** :

```bash
docker compose --profile backup up -d
```

| Variable | Défaut | Effet |
|---|---|---|
| `BACKUP_INTERVAL_SECONDS` | `86400` | délai entre deux sauvegardes réussies |
| `BACKUP_KEEP` | `14` | nombre de fichiers conservés ; au-delà, les plus anciens sont supprimés |
| `BACKUP_RETRY_SECONDS` | `300` | délai avant de réessayer après un échec |

Les fichiers atterrissent dans `./backups/`, nommés `tribe_AAAAMMJJ_HHMMSS.sql`.

### Ce qu'il faut regarder

```bash
docker compose logs backup --tail 20
ls -la backups/
```

Une sauvegarde réussie écrit une ligne qui **donne sa taille** :

```
[backup] tribe_20260827_095943.sql ok (2371312 bytes)
```

Un échec le dit, avec l'erreur de `pg_dump`, et réessaie cinq minutes plus tard :

```
[backup] FAILED, retrying in 300 s:
pg_dump: error: connection to server at "db" (172.21.0.3), port 5432 failed: Connection refused
```

> **Pourquoi la taille est dans le message.** Une version précédente écrivait
> directement dans le fichier final : à chaque échec, un fichier **de zéro octet**
> restait dans `backups/`, impossible à distinguer d'une vraie sauvegarde, compté
> par la rotation, et chassant donc les vraies sauvegardes hors de la fenêtre de
> rétention. Cinq de ces fichiers ont été retrouvés dans une instance en marche.
> Le dump passe maintenant par un fichier temporaire et n'est publié que si
> `pg_dump` a réussi, que le fichier n'est pas vide, et qu'il se termine par le
> marqueur de fin que PostgreSQL écrit. La rotation ne s'exécute qu'après une
> réussite.

### Le contrôle qui vaut la peine d'être automatisé

Un fichier récent et non vide :

```bash
find backups -name 'tribe_*.sql' -mtime -1 -size +1k | head -1
# rien en sortie = aucune sauvegarde valide depuis 24 h
```

---

## 3. Sauvegarder à la demande

Avant toute opération risquée (migration, montée de version, import massif) :

```bash
docker compose exec -T db pg_dump -U tribe -d tribe > backups/avant_$(date +%Y%m%d_%H%M%S).sql
```

- `exec -T` : pas de pseudo-terminal, sinon le fichier récupère des retours
  chariot et devient inutilisable.
- La redirection se fait **sur votre poste**, pas dans le conteneur : le fichier
  est immédiatement à côté de vous.

Vérifiez toujours ce que vous venez d'écrire :

```bash
wc -c backups/avant_*.sql
tail -1 backups/avant_*.sql      # doit finir par : -- PostgreSQL database dump complete
```

---

## 4. Vérifier une sauvegarde sans toucher à la production

**C'est l'exercice à faire régulièrement**, et il ne présente aucun risque : on
restaure dans une base jetable, à côté, et on compare.

```bash
# 1. Une base vide, à côté de la vraie
docker compose exec -T db psql -U tribe -d postgres -q \
  -c "DROP DATABASE IF EXISTS tribe_drill;" \
  -c "CREATE DATABASE tribe_drill OWNER tribe;"

# 2. Y charger la sauvegarde a verifier
docker compose exec -T db psql -U tribe -d tribe_drill -q -v ON_ERROR_STOP=1 \
  < backups/tribe_20260827_095943.sql

# 3. Comparer ce qu'elle contient a la base vivante
for t in tribes squads users audit_log; do
  echo "$t  live=$(docker compose exec -T db psql -U tribe -d tribe       -t -c "SELECT count(*) FROM $t;" | tr -d ' \r') \
          drill=$(docker compose exec -T db psql -U tribe -d tribe_drill -t -c "SELECT count(*) FROM $t;" | tr -d ' \r')"
done

# 4. Jeter la base d'essai
docker compose exec -T db psql -U tribe -d postgres -q -c "DROP DATABASE tribe_drill;"
```

- `-v ON_ERROR_STOP=1` est **indispensable** : sans lui, `psql` continue après une
  erreur et vous laisse une base à moitié restaurée en annonçant un succès.
- L'application n'est pas arrêtée, ne voit rien, et continue de servir : la base
  d'essai est un autre catalogue sur le même serveur.

### L'exercice qui prouve vraiment quelque chose

Comparer des compteurs prouve que le fichier est lisible. Pour prouver que la
chaîne complète fonctionne, utilisez un **témoin** :

1. Créez un objet reconnaissable dans l'application (une tribu `TEMOIN-<date>`).
2. Prenez une sauvegarde.
3. Supprimez le témoin dans l'application.
4. Restaurez la sauvegarde dans la base d'essai (§4).
5. Le témoin doit être **présent** dans la base restaurée et **absent** de la base
   vivante.

C'est exactement ce protocole qui a validé la procédure de ce document.

---

## 5. Restaurer pour de vrai

À ne faire que quand la base vivante est perdue ou corrompue. **Cette opération
détruit l'état actuel.**

```bash
# 0. TOUJOURS : une sauvegarde de securite de l'etat actuel, aussi mauvais soit-il.
#    Vous en aurez besoin si la restauration se passe mal.
docker compose exec -T db pg_dump -U tribe -d tribe > backups/AVANT_RESTAURATION_$(date +%Y%m%d_%H%M%S).sql

# 1. Arreter l'application, pour que rien n'ecrive pendant l'operation.
#    La base reste allumee : c'est elle qui recoit la restauration.
docker compose stop app

# 2. Vider le schema, puis le recreer.
docker compose exec -T db psql -U tribe -d tribe -v ON_ERROR_STOP=1 \
  -c "DROP SCHEMA public CASCADE;" \
  -c "CREATE SCHEMA public;" \
  -c "GRANT ALL ON SCHEMA public TO tribe;"

# 3. Charger la sauvegarde.
docker compose exec -T db psql -U tribe -d tribe -q -v ON_ERROR_STOP=1 \
  < backups/tribe_AAAAMMJJ_HHMMSS.sql

# 4. Redemarrer l'application. L'entrypoint applique les migrations Alembic :
#    si la sauvegarde vient d'une version anterieure, le schema est mis a niveau.
docker compose up -d app
docker compose logs app --tail 20

# 5. Verifier avant d'annoncer que c'est fini.
curl -s http://localhost:8000/api/health
```

Puis, dans l'application : connectez-vous, ouvrez le tableau de bord, et vérifiez
**Administration > Audit** : les dernières entrées doivent être celles d'avant
l'incident, ce qui vous dit précisément à quel instant vous êtes revenu.

> **Sur `DROP SCHEMA public CASCADE`.** C'est la commande qui efface tout. Les
> dumps produits ici ne contiennent pas `--clean`, donc les charger par-dessus des
> données existantes échouerait sur des doublons de clés. Vider d'abord est la
> façon fiable ; c'est aussi la raison pour laquelle l'étape 0 n'est pas
> facultative.

---

## 6. Ce que la restauration ne rend pas

Le dump contient la base, et **seulement** la base. Ne sont pas dedans :

| Ce qui manque | Où c'est | Conséquence |
|---|---|---|
| `SECRET_KEY` | variable d'environnement | restaurer avec une autre clé **déconnecte tout le monde** (les cookies de session ne sont plus vérifiables). Ce n'est pas une perte de données, mais prévenez. |
| Le certificat TLS | `CERT_DIR` (`TLS_ENABLED=true`) ou l'infrastructure | à réinstaller séparément si l'application terminait le TLS elle-même |
| Le modèle PPTX téléversé | dans la base (`app_settings`) | **est** restauré |
| Les fichiers de `backups/` | volume monté sur l'hôte | si vous perdez la machine, vous perdez les sauvegardes : voir §8 |

---

## 7. Sur une base managée (Cloud SQL, RDS, Azure)

Les dumps logiques restent utiles (ils sont portables, lisibles, et permettent de
remonter ailleurs), mais votre fournisseur offre mieux pour l'urgence :

- **Sauvegardes automatiques** quotidiennes, à activer, avec leur propre rétention.
- **PITR** (restauration à un instant précis) : ramène la base à une seconde près
  dans une fenêtre de plusieurs jours. C'est ce qui fait passer le RPO de 24 h à
  quelques secondes, et c'est le vrai levier si ces 24 h vous gênent.
- **Réplique de lecture** dans une autre zone, promouvable en cas de panne zonale.

Dans ce cas, le sidecar `backup` garde un rôle : il produit un dump **portable**,
que vous pouvez stocker ailleurs que chez le fournisseur, et recharger sur
n'importe quel PostgreSQL. Gardez les deux ; ils ne protègent pas de la même chose.

---

## 8. Les points faibles connus de la configuration livrée

Écrits ici plutôt que tus, pour que la décision soit prise sciemment.

| Point | Risque | Ce qu'il faut faire |
|---|---|---|
| Les sauvegardes vivent sur la **même machine** que la base | un incident matériel emporte les deux | copier `backups/` ailleurs : un bucket, un partage, une autre machine |
| Elles ne sont **pas chiffrées** | un dump contient toutes les données de l'organisation | chiffrer au repos, ou déposer dans un stockage qui le fait |
| Rien n'**alerte** si la sauvegarde échoue plusieurs jours | on découvre le problème le jour où on en a besoin | surveiller la commande `find` du §2, ou la remonter en métrique ([17](17-observabilite.md)) |
| L'exercice de restauration est **manuel** | il finit par ne plus être fait | le mettre à l'agenda, une fois par trimestre, avec le protocole du témoin (§4) |

---

## 9. En cas d'incident : l'ordre des gestes

1. **Ne restaurez pas tout de suite.** Prenez d'abord une sauvegarde de l'état
   actuel (§5 étape 0). Un état corrompu contient souvent des données récentes que
   la dernière sauvegarde n'a pas.
2. **Déterminez ce qui est cassé.** Une application qui ne démarre pas n'est
   presque jamais un problème de base : regardez `docker compose logs app`, les
   migrations, la connectivité. Le [runbook d'exploitation](06-operations-runbook.md)
   liste les symptômes courants.
3. **Choisissez le point de retour.** Listez les sauvegardes disponibles et leur
   date. Prenez la plus récente **antérieure à l'incident**, pas simplement la plus
   récente.
4. **Vérifiez-la d'abord dans une base d'essai** (§4). Cela coûte deux minutes et
   évite de découvrir un fichier illisible après avoir effacé le schéma.
5. **Restaurez** (§5), puis vérifiez par le journal d'audit à quel instant vous
   êtes revenu.
6. **Dites ce qui a été perdu.** Entre la dernière sauvegarde et l'incident, il y a
   un trou. Les personnes concernées doivent savoir lequel.
