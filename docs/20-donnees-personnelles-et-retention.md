# 20 - Données personnelles et rétention

Cette application décrit une organisation : des personnes, leurs rôles, ce
qu'elles livrent, et leurs absences. C'est du traitement de données personnelles,
au sens du RGPD, même si personne ne l'a jamais appelé comme ça.

Ce document dit **quelles données sont stockées**, **combien de temps**, **qui les
voit**, et **comment répondre** quand quelqu'un demande à consulter ou à effacer
les siennes. Il ne remplace pas l'avis de votre délégué à la protection des
données ; il lui donne les faits techniques dont il a besoin.

---

## 1. Ce qui est stocké, et pourquoi

### Données identifiantes

| Donnée | Où | Pourquoi elle existe |
|---|---|---|
| Email, nom affiché | `users` | identifier le compte, l'associer à l'identité SSO, envoyer les rapports |
| Rôle, tribu, squads menées | `users`, `squads` | décider ce que la personne a le droit de voir |
| Date de dernière connexion | `users.last_login_at` | repérer les comptes dormants |
| Empreinte du mot de passe (Argon2) | `users.password_hash` | connexion locale. Ce n'est **pas** le mot de passe : il est irréversible. Vide sur un compte purement SSO. |
| Nom et intitulé de poste | `org_members` | l'organigramme, y compris pour des personnes **sans compte** |

> `org_members` mérite l'attention : on peut y décrire quelqu'un qui n'a jamais
> ouvert l'application et n'en a jamais entendu parler. C'est légitime pour un
> organigramme interne, mais cette personne a les mêmes droits que les autres sur
> ces données.

### Données sensibles par leur contexte

| Donnée | Où | Qui la voit |
|---|---|---|
| **Absences** (type, dates) | `leaves` | tout le monde dans la tribu de la personne |
| **Motif d'absence** (texte libre) | `leaves.comment` | la personne, son responsable de squad, le tribe leader, les admins |
| Commentaire de décision | `leaves.decision_comment` | idem |

Le motif d'une absence est le champ le plus délicat de l'application : un texte
libre où quelqu'un peut écrire une raison médicale ou familiale. Il est déjà
restreint (voir [05 - Sécurité](05-security.md)), mais **la meilleure protection
reste de ne pas en écrire**. Dites-le à vos utilisateurs, et envisagez de
supprimer le champ si votre organisation n'en a pas besoin.

### Traces d'activité

| Donnée | Où | Contenu |
|---|---|---|
| Journal d'audit | `audit_log` | qui a fait quoi, quand, sur quelle entité. Contient des identifiants d'utilisateurs et parfois leur email dans le `detail`. |
| Messages du fil | `feed_posts`, `feed_replies`, `feed_reactions` | texte libre écrit par des personnes, avec leur identité |
| Journaux applicatifs | stdout du conteneur | adresses IP dans les lignes d'accès uvicorn, emails dans certains messages |

---

## 2. Combien de temps

| Donnée | Rétention par défaut | Réglage |
|---|---|---|
| Journal d'audit | **conservé indéfiniment** | `AUDIT_RETENTION_DAYS` (variable d'environnement). 0 = tout garder. |
| Messages du fil | **conservés indéfiniment** | Administration > Réglages > « Rétention des messages ». 0 = tout garder. |
| Absences | **conservées indéfiniment** | aucun réglage : à purger à la main (§5) |
| Comptes utilisateurs | jusqu'à suppression | Administration > Utilisateurs |
| Sauvegardes | 14 fichiers glissants | `BACKUP_KEEP` ([19](19-plan-de-reprise.md)) |
| Journaux du conteneur | selon votre collecteur | hors application |

Les deux purges configurables tournent dans le **planificateur horaire** de
l'application (`app/maintenance.py`), sur la réplique qui détient le verrou.

> **Ce que ce réglage faisait avant, et ne fait plus.** « Rétention des messages »
> ne faisait que **masquer** les messages anciens de la liste : ils restaient en
> base, et dans chaque sauvegarde, pour toujours. Un administrateur qui l'avait
> réglé pour satisfaire une politique de conservation n'avait rien satisfait du
> tout. Depuis, les messages dépassant la fenêtre sont **réellement supprimés**,
> avec leurs réponses et leurs réactions. Les messages **épinglés** sont exemptés :
> épingler, c'est décider que celui-là reste.

**Choisir une durée** : la question n'est pas « combien de temps ça peut nous
servir », mais « pendant combien de temps avons-nous une raison de le garder ».
Pour le journal d'audit, la raison est la traçabilité de sécurité, ce qui justifie
typiquement 6 à 24 mois. Pour le fil, c'est de la conversation : quelques mois
suffisent presque toujours.

---

## 3. Qui voit quoi

Le détail est dans [05 - Sécurité](05-security.md) ; le résumé utile ici :

- **La visibilité est cloisonnée par tribu.** Un membre d'une tribu ne voit pas les
  personnes ni les absences d'une autre.
- **Le motif d'absence** n'est visible que de la personne, de sa hiérarchie
  d'équipe et des administrateurs.
- **Le journal d'audit est réservé aux administrateurs.**
- **Les clés d'API** ne donnent accès à aucune donnée personnelle : leurs
  périmètres couvrent le dashboard, la roadmap, l'organigramme et les rapports.

---

## 4. Répondre à une demande d'accès

Quelqu'un demande ce que l'application sait de lui. Depuis la racine du dépôt,
avec l'application en marche :

```bash
docker compose exec -T db psql -U tribe -d tribe -x -c "
  SELECT id, email, display_name, role, tribe_id, status, last_login_at, created_at
  FROM users WHERE email = 'la.personne@example.com';"
```

Puis ce qui s'y rattache (remplacez `<id>` par l'identifiant obtenu) :

```bash
docker compose exec -T db psql -U tribe -d tribe -c "
  SELECT start_date, end_date, status, detail, comment FROM leaves WHERE user_id = <id>;"

docker compose exec -T db psql -U tribe -d tribe -c "
  SELECT created_at, kind, content FROM feed_posts WHERE author_user_id = <id>;"

docker compose exec -T db psql -U tribe -d tribe -c "
  SELECT timestamp, action, entity, entity_id FROM audit_log WHERE user_id = <id> ORDER BY timestamp DESC;"

docker compose exec -T db psql -U tribe -d tribe -c "
  SELECT full_name, role_title FROM org_members WHERE full_name ILIKE '%Nom Prenom%';"
```

- `-x` affiche une ligne par champ, ce qui est bien plus lisible pour un
  enregistrement unique.
- `org_members` se cherche par **nom**, pas par identifiant : ces entrées peuvent
  n'être liées à aucun compte.

---

## 5. Répondre à une demande d'effacement

Il n'y a pas de bouton « tout effacer », et c'est délibéré : effacer une personne
d'un système qui décrit une organisation demande de décider, cas par cas, ce qui
disparaît et ce qui doit rester. Voici les décisions, et la raison de chacune.

### Ce qui s'efface sans discussion

```sql
-- Absences : personnelles, sans valeur au-dela de la personne.
DELETE FROM leaves WHERE user_id = <id>;

-- Messages du fil et reactions.
DELETE FROM feed_reactions WHERE user_id = <id>;
DELETE FROM feed_replies   WHERE author_user_id = <id>;
DELETE FROM feed_posts     WHERE author_user_id = <id>;

-- Presence dans l'organigramme.
DELETE FROM org_members WHERE full_name = 'Nom Prenom';
```

### Le compte lui-même

Passez par **Administration > Utilisateurs**, qui gère les rattachements (une
squad dont la personne était responsable se retrouve sans responsable, ce que
l'écran vous montre). Une suppression directe en base laisserait ces liens dans un
état incohérent.

### Le journal d'audit : à anonymiser, pas à effacer

```sql
-- Detache les entrees de la personne sans detruire la trace elle-meme.
UPDATE audit_log SET user_id = NULL WHERE user_id = <id>;
```

Le journal d'audit répond à un intérêt légitime distinct : la traçabilité de
sécurité. Le détruire ferait disparaître la preuve que telle action a eu lieu.
Le détacher conserve le fait tout en supprimant l'identification, ce que le schéma
prévoit explicitement : `audit_log.user_id` est nullable pour cette raison, et
l'écran d'audit affiche alors « compte supprimé » au lieu d'un identifiant.

Attention : le champ `detail` de certaines entrées contient un email. Pour un
effacement complet :

```sql
UPDATE audit_log SET detail = detail - 'email'
WHERE detail ? 'email' AND detail->>'email' = 'la.personne@example.com';
```

### Et les sauvegardes

Une personne effacée aujourd'hui **reste dans les sauvegardes** jusqu'à ce que
celles-ci sortent de la fenêtre de rétention (14 jours par défaut). C'est admis :
la rétention est limitée, documentée, et restaurer une sauvegarde ancienne est un
acte exceptionnel. **Notez la demande** pour ne pas ressusciter la personne sans
s'en rendre compte lors d'une restauration.

---

## 6. Les points à trancher avec votre organisation

Écrits ici plutôt que passés sous silence.

| Point | État | Ce qu'il reste à faire |
|---|---|---|
| Durée de conservation du journal d'audit | illimitée par défaut | choisir une durée et poser `AUDIT_RETENTION_DAYS` |
| Durée de conservation du fil | illimitée par défaut | choisir une durée dans Administration > Réglages |
| Absences | aucune purge automatique | décider d'une durée et purger, ou l'automatiser |
| Motif d'absence en texte libre | présent, restreint | décider si votre organisation en a besoin ; sinon, le retirer est plus sûr que le protéger |
| Sauvegardes non chiffrées | voir [19](19-plan-de-reprise.md) §8 | chiffrer au repos |
| Information des personnes | hors application | dire aux utilisateurs ce qui est collecté et pourquoi |
| Sous-traitance (hébergeur, IdP, SMTP) | hors application | les accords de traitement relèvent de vos contrats |

---

## 7. Ce que l'application ne fait pas

- **Aucun traçage, aucune analytique tierce.** Pas de cookie publicitaire, pas de
  script externe : la [politique de sécurité de contenu](05-security.md) les
  bloquerait de toute façon.
- **Aucune donnée ne sort**, sauf ce que vous configurez explicitement : emails via
  votre SMTP, export du journal d'audit vers syslog / GCS / BigQuery si vous
  l'activez.
- **Le cookie de session** est un cookie technique, nécessaire au fonctionnement :
  il ne demande pas de consentement.
- **Les métriques Prometheus** ([17](17-observabilite.md)) ne contiennent aucune
  donnée personnelle, par construction : elles comptent des requêtes par gabarit de
  route, jamais par utilisateur.
