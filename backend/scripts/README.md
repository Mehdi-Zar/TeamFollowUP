# backend/scripts

One-shot operational scripts. They act on the **live database** and are
**destructive** - review before running on a populated instance.

| Script | What it does |
|---|---|
| `seed_real_org.py` | Wipes org content (tribes, squads, objectives, roadmap, KPIs, budgets, key messages, feed, snapshots, members…) **keeping user accounts**, then creates the real *Cloud Foundations Tribe* + its squads with products/hardware (from `Orga.pptx`). |
| `prune_users.py` | Keeps the admin + exactly one impersonation account per role (tribe_leader, squad_leader, member), scopes them to the real tribe, and makes the squad leader lead one squad. Deletes all other users. |

## Run

From the project root, against the running container:

```bash
docker compose exec -T app python - < backend/scripts/seed_real_org.py
docker compose exec -T app python - < backend/scripts/prune_users.py
```

Each prints what it deleted/created. Take a database backup first if the data
matters.
