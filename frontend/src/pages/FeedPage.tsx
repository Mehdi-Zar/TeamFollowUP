/**
 * FeedPage - the team activity feed (announcements / incidents / info / success).
 *
 * Shows a chronological list of posts, optionally filtered by squad and by kind.
 * Writers (see `isWriter`) get a composer to publish posts and can pin/unpin;
 * everyone else reads only. Reactions, replies, pinning and post kinds are each
 * gated behind a "feed" module feature flag so an admin can turn them off.
 * The list live-refreshes every 5 seconds.
 */
import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { useAuth } from "../auth";
import { useI18n } from "../i18n";
import { useModule } from "../config";
import { FeedKind, FeedPost, Role, Squad } from "../types";
import { Spinner, ErrorBanner, EmptyState } from "../components/ui";
import { useSetPageChrome } from "../components/pageChrome";
import { isWriter } from "../perms";

const KINDS: FeedKind[] = ["incident", "info", "success"];

/** Build the avatar initials (up to 2 letters) from a display name; "?" if none. */
function initials(name?: string | null): string {
  if (!name) return "?";
  return name.split(" ").filter(Boolean).slice(0, 2).map((w) => w[0]?.toUpperCase()).join("");
}

/**
 * Feed root page: composer + filters + post list.
 * Access: any authenticated user can read; only "writers" (admin / tribe leader /
 * squad leader, per `isWriter`) may post and pin. Reactions/replies/pin/kinds are
 * each toggled by their "feed" module feature flag.
 */
export default function FeedPage() {
  const { user, effectiveRole } = useAuth();
  const { t, formatDateTime } = useI18n();
  // effectiveRole may be a previewed role; fall back to the least-privileged one.
  const role = (effectiveRole ?? "member") as Role;
  const canPost = isWriter(role);
  const canPin = isWriter(role);
  const moduleOn = useModule();
  const kindsOn = moduleOn("feed", "kinds");
  const reactionsOn = moduleOn("feed", "reactions");
  const repliesOn = moduleOn("feed", "replies");
  const pinOn = moduleOn("feed", "pin");

  const [posts, setPosts] = useState<FeedPost[] | null>(null);
  const [squads, setSquads] = useState<Squad[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [squadFilter, setSquadFilter] = useState<string>("");
  const [kindFilter, setKindFilter] = useState<string>("");

  // composer
  const [content, setContent] = useState("");
  const [kind, setKind] = useState<FeedKind>("info");
  const [squadId, setSquadId] = useState<string>("");

  // Keep the current filters in a ref so the interval-driven load() (below) always
  // reads the latest values without re-registering the interval on every change.
  const filterRef = useRef({ squadFilter, kindFilter });
  filterRef.current = { squadFilter, kindFilter };

  function buildUrl() {
    const p = new URLSearchParams();
    if (filterRef.current.squadFilter) p.set("squad_id", filterRef.current.squadFilter);
    if (filterRef.current.kindFilter) p.set("kind", filterRef.current.kindFilter);
    const qs = p.toString();
    return `/api/feed${qs ? `?${qs}` : ""}`;
  }
  function load() {
    api.get<FeedPost[]>(buildUrl()).then(setPosts).catch((e) => setError(e.message));
  }

  useEffect(() => {
    api.get<Squad[]>("/api/squads").then(setSquads).catch(() => {});
  }, []);
  useEffect(() => {
    load();
  }, [squadFilter, kindFilter]);
  // Live refresh: re-fetch every 5s so new posts/replies appear without reload.
  useEffect(() => {
    const id = setInterval(load, 5000);
    return () => clearInterval(id);
  }, []);

  async function publish() {
    if (!content.trim()) return;
    await api.post("/api/feed", { content: content.trim(), kind, squad_id: squadId ? Number(squadId) : null });
    setContent("");
    setSquadId("");
    setKind("info");
    load();
  }

  useSetPageChrome(
    {
      tabs: kindsOn
        ? [
            { key: "", label: t("feed.filter_kind") },
            ...KINDS.map((k) => ({ key: k, label: t(`feed.kind.${k}`) })),
          ]
        : undefined,
      activeTab: kindFilter,
      onTab: (k) => setKindFilter(k),
      actions: (
        <select className="w-auto" value={squadFilter} onChange={(e) => setSquadFilter(e.target.value)}>
          <option value="">{t("feed.filter_squad")}</option>
          {squads.map((s) => (
            <option key={s.id} value={s.id}>
              {s.name}
            </option>
          ))}
        </select>
      ),
    },
    [kindFilter, squadFilter, squads, t, kindsOn]
  );

  if (error) return <ErrorBanner message={error} />;

  return (
    <div className="stack" style={{ gap: 16 }}>
      {canPost ? (
        <div className="card">
          <textarea rows={2} placeholder={t("feed.placeholder")} value={content} onChange={(e) => setContent(e.target.value)} />
          <div className="between" style={{ marginTop: 10 }}>
            <div className="inline">
              {kindsOn && (
                <select className="w-auto" value={kind} onChange={(e) => setKind(e.target.value as FeedKind)}>
                  {KINDS.map((k) => (<option key={k} value={k}>{t(`feed.kind.${k}`)}</option>))}
                </select>
              )}
              <select className="w-auto" value={squadId} onChange={(e) => setSquadId(e.target.value)}>
                <option value="">{t("feed.attach_squad")}</option>
                {squads.map((s) => (<option key={s.id} value={s.id}>{s.name}</option>))}
              </select>
            </div>
            <button onClick={publish} disabled={!content.trim()}>{t("feed.post")}</button>
          </div>
        </div>
      ) : (
        <div className="banner">{t("feed.cannot_post")}</div>
      )}

      {!posts ? (
        <Spinner />
      ) : posts.length === 0 ? (
        <EmptyState message={t("feed.empty")} />
      ) : (
        posts.map((p) => (
          // canDelete: the post's own author, or a moderator (admin / tribe leader).
          <PostCard key={p.id} post={p} canPin={canPin && pinOn} reactionsOn={reactionsOn} repliesOn={repliesOn}
                    canDelete={p.author?.id === user?.id || role === "admin" || role === "tribe_leader"}
                    userId={user?.id} onChange={load} t={t} formatDateTime={formatDateTime} />
        ))
      )}
    </div>
  );
}

/**
 * A single feed post with its actions (react / reply / pin / delete) and reply list.
 * The action buttons are shown according to the flags passed in by the parent:
 * `reactionsOn`/`repliesOn` (module features), `canPin` and `canDelete` (permissions).
 * A reply can only be deleted by its own author (`r.author?.id === userId`).
 */
function PostCard({ post, canPin, reactionsOn, repliesOn, canDelete, userId, onChange, t, formatDateTime }: any) {
  const [reply, setReply] = useState("");

  async function react(kind: string) {
    await api.post(`/api/feed/${post.id}/reactions`, { kind });
    onChange();
  }
  async function sendReply() {
    if (!reply.trim()) return;
    await api.post(`/api/feed/${post.id}/replies`, { content: reply.trim() });
    setReply("");
    onChange();
  }
  async function togglePin() {
    await api.put(`/api/feed/${post.id}/pin`, { is_pinned: !post.is_pinned });
    onChange();
  }
  async function del() {
    await api.del(`/api/feed/${post.id}`);
    onChange();
  }
  async function delReply(id: number) {
    await api.del(`/api/feed/replies/${id}`);
    onChange();
  }

  return (
    <div className={`card feed-post k-${post.kind}`}>
      <div className="inline" style={{ alignItems: "flex-start", gap: 12 }}>
        <div className="feed-avatar">{initials(post.author?.display_name)}</div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div className="between">
            <div className="inline" style={{ gap: 8, flexWrap: "wrap" }}>
              <span className="strong">{post.author?.display_name || "?"}</span>
              <span className={`feed-kind k-${post.kind}`}>{t(`feed.kind.${post.kind}`)}</span>
              {post.squad_name && <span className="pill-cat">{post.squad_name}</span>}
              {post.is_pinned && <span className="badge badge-navy">{t("feed.pinned")}</span>}
            </div>
            <span className="small muted">{formatDateTime(post.created_at)}</span>
          </div>
          <div style={{ marginTop: 6, whiteSpace: "pre-wrap" }}>{post.content}</div>

          <div className="inline" style={{ gap: 8, marginTop: 10, flexWrap: "wrap" }}>
            {reactionsOn && (
              <>
                <button className={`feed-react ${post.my_reactions.includes("like") ? "active" : ""}`} onClick={() => react("like")}>
                  ♥ {t("feed.like")} {post.reactions.like || 0}
                </button>
                <button className={`feed-react ${post.my_reactions.includes("ack") ? "active" : ""}`} onClick={() => react("ack")}>
                  ✓ {t("feed.ack")} {post.reactions.ack || 0}
                </button>
              </>
            )}
            {canPin && <button className="feed-react" onClick={togglePin}>{post.is_pinned ? t("feed.unpin") : t("feed.pin")}</button>}
            {canDelete && <button className="feed-react" onClick={del}>{t("action.delete")}</button>}
          </div>

          {repliesOn && post.replies.length > 0 && (
            <div className="stack" style={{ marginTop: 12, gap: 8 }}>
              {post.replies.map((r: any) => (
                <div key={r.id} className="feed-reply">
                  <div className="between">
                    <span className="small"><span className="strong">{r.author?.display_name || "?"}</span> · {r.content}</span>
                    <span className="inline" style={{ gap: 6 }}>
                      <span className="small muted">{formatDateTime(r.created_at)}</span>
                      {(r.author?.id === userId) && <button className="btn-ghost btn-sm" aria-label={t("action.delete")} onClick={() => delReply(r.id)}>✕</button>}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}

          {repliesOn && (
            <div className="inline" style={{ marginTop: 10 }}>
              <input placeholder={t("feed.reply_ph")} value={reply} onChange={(e) => setReply(e.target.value)} onKeyDown={(e) => e.key === "Enter" && sendReply()} />
              <button className="btn-secondary btn-sm" onClick={sendReply}>{t("feed.reply")}</button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
