"""End-to-end functional test of Tribe Cockpit against the running app."""
import json
import urllib.request
import urllib.error
import http.cookiejar

BASE = "http://localhost:8080"
results = []


def session():
    cj = http.cookiejar.CookieJar()
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))


def req(op, method, path, body=None, expect=None):
    url = BASE + path
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, method=method)
    if data is not None:
        r.add_header("Content-Type", "application/json")
    try:
        resp = op.open(r, timeout=20)
        status = resp.status
        raw = resp.read().decode()
    except urllib.error.HTTPError as e:
        status = e.code
        raw = e.read().decode()
    payload = None
    if raw:
        try:
            payload = json.loads(raw)
        except Exception:
            payload = raw
    return status, payload


def check(name, cond, detail=""):
    results.append((name, bool(cond), detail))
    print(("PASS" if cond else "FAIL"), name, ("" if cond else "-> " + str(detail)))


def login(op, email, pw):
    s, _ = req(op, "POST", "/api/auth/login", {"email": email, "password": pw})
    return s == 200


# ---- sessions ----
admin = session(); tribe = session(); sara = session(); hugo = session()
check("login admin", login(admin, "admin@local", "changeme-admin"))
check("login tribe leader", login(tribe, "nadia.n1@local", "demo"))
check("login squad leader (sara/GCP)", login(sara, "sara.gcp@local", "demo"))
check("login member (hugo)", login(hugo, "hugo.member@local", "demo"))

# ---- public config & auth config ----
s, cfg = req(admin, "GET", "/api/config")
check("public config app_name", s == 200 and cfg.get("app_name") == "Tribe Cockpit", cfg)
check("public config default_year", cfg.get("default_year") == 2026, cfg)
s, ac = req(admin, "GET", "/api/auth/config")
check("auth config both off", ac == {"oidc_enabled": False, "saml_enabled": False}, ac)

# ---- tribes (multi-tenant) ----
s, tribes = req(admin, "GET", "/api/tribes")
check("admin lists tribes >=2", s == 200 and len(tribes) >= 2, tribes)
tA = tribes[0]["id"]
s, ov = req(admin, "GET", "/api/tribes/org-overview")
check("admin org-overview all tribes", s == 200 and len(ov) >= 2 and "tree" in ov[0], s)
s, _ = req(tribe, "GET", "/api/tribes/org-overview")
check("tribe leader cannot see org-overview", s == 403, s)
s, mine = req(tribe, "GET", "/api/tribes")
check("tribe leader can browse all tribes (for org charts)", s == 200 and len(mine) >= 2, mine)
s, nt = req(admin, "POST", "/api/tribes", {"name": "ZZ Tribe"})
check("admin creates tribe", s == 201, s)
if s == 201:
    req(admin, "DELETE", f"/api/tribes/{nt['id']}")
s, _ = req(tribe, "POST", "/api/tribes", {"name": "x"})
check("tribe leader cannot create tribe", s == 403, s)

# ---- dashboard ----
s, d = req(admin, "GET", "/api/dashboard")
check("dashboard 200 + 9 squads", s == 200 and d["summary"]["squads_total"] == 9, d.get("summary"))
gcp = next((c for c in d["cards"] if c["name"] == "GCP"), None)
check("GCP card has annual_progress", gcp and "annual_progress" in gcp, gcp and list(gcp.keys()))
check("GCP card blocked>0 + quarter_breakdowns", gcp and gcp["blocked_count"] >= 1 and "2" in gcp["quarter_breakdowns"], gcp and gcp.get("blocked_count"))
check("dashboard summary has avg/blocked/atrisk", all(k in d["summary"] for k in ("avg_progress", "blocked_jalons", "at_risk_jalons")), d["summary"])
check("admin dashboard sees all 9 squads", d["summary"]["squads_total"] == 9, d["summary"])
gid = gcp["squad_id"]
# tribe leader dashboard is scoped to own tribe
s, dt = req(tribe, "GET", "/api/dashboard")
check("tribe leader dashboard scoped (<9)", s == 200 and 0 < len(dt["cards"]) < 9, len(dt["cards"]) if s == 200 else s)

# ---- squad detail: rich jalon, members hierarchy, kpis_enabled ----
s, sd = req(admin, "GET", f"/api/squads/{gid}?year=2026")
check("squad detail annual_progress", "annual_progress" in sd, list(sd.keys()))
pipeline = next((r for r in sd["roadmap_items"] if r["title"].startswith("Pipeline")), None)
check("jalon has rich fields", pipeline and pipeline["description"] and pipeline["risks"] and pipeline["owner"], pipeline)
yuki = next((m for m in sd["members"] if m["full_name"] == "Yuki Tanaka"), None)
check("member hierarchy (Yuki has manager)", yuki and yuki["manager_id"] is not None, yuki)
check("GCP kpis_enabled True", sd["kpis_enabled"] is True, sd["kpis_enabled"])

# onboarding kpis disabled
s, onb = req(admin, "GET", "/api/squads")
onb_id = next(x["id"] for x in onb if x["name"] == "Onboarding")
s, ond = req(admin, "GET", f"/api/squads/{onb_id}")
check("Onboarding kpis_enabled False", ond["kpis_enabled"] is False, ond["kpis_enabled"])

# ---- roadmap CRUD (squad leader on own squad) ----
s, j = req(sara, "POST", "/api/roadmap-items", {"squad_id": gid, "year": 2026, "quarter": 3, "title": "Test jalon",
           "theme": "Landing Zones", "status": "blocked", "owner": "Noah Blanc", "description": "desc", "success_criteria": "ok", "risks": "r"})
check("squad leader create rich jalon", s == 201 and j.get("status") == "blocked", (s, j))
jid = j["id"] if s == 201 else None
s, j2 = req(sara, "PUT", f"/api/roadmap-items/{jid}", {"status": "done"})
check("update jalon status", s == 200 and j2["status"] == "done", (s, j2))
s, _ = req(sara, "DELETE", f"/api/roadmap-items/{jid}")
check("delete jalon", s == 204, s)
# squad leader cannot edit other squad
s, _ = req(sara, "POST", "/api/roadmap-items", {"squad_id": onb_id, "year": 2026, "quarter": 1, "title": "x", "theme": "Landing Zones"})
check("squad leader blocked on other squad", s == 403, s)

# ---- objectives: squad leader forbidden, tribe allowed ----
s, _ = req(sara, "POST", "/api/objectives", {"squad_id": gid, "year": 2026, "title": "x"})
check("squad leader cannot set objective", s == 403, s)
s, o = req(tribe, "POST", "/api/objectives", {"squad_id": gid, "year": 2026, "title": "Obj test", "rag_status": "amber"})
check("tribe leader sets objective", s == 201, (s, o))
if s == 201:
    req(tribe, "DELETE", f"/api/objectives/{o['id']}")

# ---- members ----
s, m = req(sara, "POST", "/api/members", {"squad_id": gid, "full_name": "Temp Member", "role_title": "Dev"})
check("squad leader adds member (own)", s == 201, (s, m))
if s == 201:
    req(sara, "DELETE", f"/api/members/{m['id']}")
s, _ = req(sara, "POST", "/api/members", {"squad_id": onb_id, "full_name": "x"})
check("squad leader cannot add member other squad", s == 403, s)

# ---- quarter progress ----
s, qp = req(sara, "PUT", f"/api/squads/{gid}/quarter-progress", {"year": 2026, "quarter": 3, "progress_pct": 25})
check("set quarter progress", s == 200 and qp["progress_pct"] == 25, (s, qp))

# ---- snapshots ----
s, snap = req(sara, "POST", f"/api/squads/{gid}/snapshots", {"year": 2026})
check("submit cycle (snapshot)", s == 201, s)
s, hist = req(admin, "GET", f"/api/squads/{gid}/snapshots")
check("snapshot history >=1", s == 200 and len(hist) >= 1, len(hist) if s == 200 else s)
if hist:
    s, cmp = req(admin, "GET", f"/api/squads/{gid}/snapshots/{hist[0]['id']}/compare")
    check("snapshot compare", s == 200 and "diff" in cmp, s)

# ---- org chart (entities + squads) ----
s, tree = req(admin, "GET", "/api/org")
check("org tree root", s == 200 and tree and tree[0]["title"] == "Direction de la tribu", tree and tree[0]["title"])
domains = tree[0]["children"] if tree else []
check("org has domain entities", any(c["title"].startswith("Domaine") for c in domains), [c["title"] for c in domains])
s, node = req(tribe, "POST", "/api/org", {"title": "Entité test"})
check("tribe creates org node", s == 201, s)
if s == 201:
    req(tribe, "DELETE", f"/api/org/{node['id']}")
s, _ = req(sara, "POST", "/api/org", {"title": "x"})
check("squad leader cannot edit org", s == 403, s)

# ---- feed (tweet zone) ----
s, feed = req(admin, "GET", "/api/feed")
check("feed list >=3", s == 200 and len(feed) >= 3, len(feed) if s == 200 else s)
pinned = [p for p in feed if p["is_pinned"]]
check("feed has a pinned incident", any(p["kind"] == "incident" for p in pinned), [p["kind"] for p in pinned])
s, _ = req(hugo, "POST", "/api/feed", {"content": "x", "kind": "info"})
check("member cannot post (scope leaders)", s == 403, s)
pid = feed[0]["id"]
s, _ = req(hugo, "POST", f"/api/feed/{pid}/replies", {"content": "member reply"})
check("member can reply", s == 201, s)
s, rp = req(hugo, "POST", f"/api/feed/{pid}/reactions", {"kind": "like"})
check("member can react", s == 200 and rp["reactions"]["like"] >= 1, rp.get("reactions") if s == 200 else s)
req(hugo, "POST", f"/api/feed/{pid}/reactions", {"kind": "like"})  # toggle off
s, np = req(sara, "POST", "/api/feed", {"content": "Live test from squad leader", "kind": "success", "squad_id": gid})
check("squad leader posts", s == 201, s)
npid = np["id"] if s == 201 else None
s, _ = req(sara, "PUT", f"/api/feed/{npid}/pin", {"is_pinned": True})
check("squad leader pins", s == 200, s)
s, _ = req(admin, "DELETE", f"/api/feed/{npid}")
check("admin deletes (moderation)", s == 204, s)

# ---- admin: users, settings, auth-config, audit ----
s, users = req(admin, "GET", "/api/admin/users")
check("admin list users", s == 200 and len(users) >= 10, len(users) if s == 200 else s)
s, nu = req(admin, "POST", "/api/admin/users", {"email": "temp@test", "display_name": "Temp", "role": "member", "password": "pw"})
check("admin create user", s == 201, s)
if s == 201:
    s2, _ = req(admin, "PUT", f"/api/admin/users/{nu['id']}", {"role": "squad_leader"})
    check("admin update user role", s2 == 200, s2)
    s3, _ = req(admin, "DELETE", f"/api/admin/users/{nu['id']}")
    check("admin delete user", s3 == 204, s3)
s, _ = req(tribe, "GET", "/api/admin/users")
check("tribe leader blocked from admin users", s == 403, s)

s, gset = req(admin, "GET", "/api/admin/settings")
check("admin settings has all keys", all(k in gset for k in ("app_name", "default_lang", "default_year", "feed_post_scope", "staleness_threshold_days")), list(gset.keys()))
s, gset2 = req(admin, "PUT", "/api/admin/settings", {"app_subtitle": "Test", "feed_retention_days": 0})
check("admin save settings", s == 200 and gset2["app_subtitle"] == "Test", s)

s, _ = req(admin, "PUT", "/api/admin/auth-config", {"oidc_enabled": False, "group_role_mappings": [{"group": "g", "role": "tribe_leader"}]})
check("admin save auth-config", s == 200, s)
s, audit = req(admin, "GET", "/api/audit-log")
check("audit log not empty", s == 200 and len(audit) > 0, len(audit) if s == 200 else s)

# ---- SAML metadata generation (enable, fetch, disable) ----
req(admin, "PUT", "/api/admin/auth-config", {"saml_enabled": True, "saml_sp_entity_id": "http://localhost:8080/api/auth/saml/metadata", "saml_acs_url": "http://localhost:8080/api/auth/saml/acs"})
s, md = req(admin, "GET", "/api/auth/saml/metadata")
check("SAML SP metadata generated", s == 200 and "EntityDescriptor" in str(md), s)
req(admin, "PUT", "/api/admin/auth-config", {"saml_enabled": False})

# ---- exports ----
s, csv1 = req(admin, "GET", "/api/exports/dashboard.csv")
check("dashboard CSV", s == 200 and "squad" in str(csv1), s)
s, csv2 = req(admin, "GET", f"/api/exports/squad/{gid}.csv")
check("squad CSV", s == 200, s)

# ---- member read-only ----
s, _ = req(hugo, "GET", "/api/dashboard")
check("member reads dashboard", s == 200, s)
s, _ = req(hugo, "POST", "/api/objectives", {"squad_id": gid, "year": 2026, "title": "x"})
check("member cannot write", s == 403, s)

# ---- delete squad with references (throwaway) ----
s, ts = req(admin, "POST", "/api/squads", {"name": "ZZ TestDelete", "tribe_id": tA})
tsid = ts["id"] if s == 201 else None
check("admin creates squad in a tribe", s == 201, (s, ts))
req(admin, "POST", "/api/org", {"title": "ZZ", "squad_id": tsid, "tribe_id": tA})
req(admin, "POST", "/api/feed", {"content": "ref", "kind": "info", "squad_id": tsid})
s, _ = req(admin, "DELETE", f"/api/squads/{tsid}")
check("delete squad with org+feed refs", s == 204, s)

# ---- notifications & preferences ----
s, prefs = req(hugo, "GET", "/api/me/preferences")
check("get preferences", s == 200 and "notify_tweets" in prefs, prefs)
s, n = req(hugo, "GET", "/api/notifications")
check("member has seed notifications", s == 200 and n["unread_count"] >= 2, n.get("unread_count") if s == 200 else s)
before = n["unread_count"]
req(sara, "POST", "/api/feed", {"content": "notif test", "kind": "info"})  # sara is tribe A
s, n2 = req(hugo, "GET", "/api/notifications")
check("new tweet creates a notification", s == 200 and n2["unread_count"] > before, (before, n2.get("unread_count")))
req(hugo, "POST", "/api/notifications/read-all")
s, n3 = req(hugo, "GET", "/api/notifications")
check("mark all read", n3["unread_count"] == 0, n3.get("unread_count"))
s, p2 = req(hugo, "PUT", "/api/me/preferences", {"email_notifications": True})
check("update preference", s == 200 and p2["email_notifications"] is True, p2)

# ---- SMTP config + email export ----
s, smtp = req(admin, "GET", "/api/admin/smtp-config")
check("admin reads smtp config", s == 200 and "enabled" in smtp, list(smtp.keys()) if s == 200 else s)
s, _ = req(admin, "PUT", "/api/admin/smtp-config", {"host": "smtp.example", "port": 587})
check("admin saves smtp config", s == 200, s)
s, cfg2 = req(admin, "GET", "/api/config")
check("smtp_enabled in public config", "smtp_enabled" in cfg2, cfg2)
s, _ = req(admin, "POST", "/api/exports/dashboard/email", {"to": "someone@example.com"})
check("email export blocked when SMTP off", s == 400, s)
s, _ = req(hugo, "GET", "/api/admin/smtp-config")
check("non-admin cannot read smtp config", s == 403, s)

# ---- cross-tribe org viewing (everyone read-only) ----
tB = tribes[1]["id"]
s, otherorg = req(tribe, "GET", f"/api/org?tribe_id={tB}")  # nadia (tribe A) views tribe B
check("any user can view another tribe's org", s == 200 and isinstance(otherorg, list), s)
s, allt = req(tribe, "GET", "/api/tribes")
check("non-admin lists all tribes", s == 200 and len(allt) >= 2, len(allt) if s == 200 else s)
# nadia (tribe A) cannot modify a node that belongs to tribe B
foreign_node = otherorg[0]["id"] if otherorg else None
s, _ = req(tribe, "PUT", f"/api/org/{foreign_node}", {"title": "hack"})
check("cannot edit another tribe's org node", s == 403, s)

# ---- print SPA routes ----
for path in ("/", "/fil", "/organigramme", "/tribus", "/preferences", "/saisie", "/admin", "/print/dashboard", f"/print/squad/{gid}", "/docs"):
    s, _ = req(admin, "GET", path)
    check(f"route {path}", s == 200, s)

# ---- summary ----
passed = sum(1 for _, ok, _ in results if ok)
print("\n==== %d/%d checks passed ====" % (passed, len(results)))
fails = [n for n, ok, _ in results if not ok]
if fails:
    print("FAILURES:", fails)
