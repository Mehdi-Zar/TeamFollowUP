// Les personnes qu'on peut nommer dans un champ (porteur, participant, destinataire).
import { useEffect, useState } from "react";
import { api } from "../api";

export type Person = { id: number; name: string; email: string | null; tribe_id: number | null };

/** "tribe": one's own tribe (all of it for an admin), the bound of the mail
 *  recipients. "all": every active account of the application, for the fields
 *  that only name someone (owners, people of the org chart). */
export type PeopleScope = "tribe" | "all";

const cache: Partial<Record<PeopleScope, { at: number; list: Promise<Person[]> }>> = {};
// A list older than this is fetched again: accounts are created while the app is open.
const TTL_MS = 2 * 60 * 1000;

/** Forget the lists: called after an account is created, changed, approved or
 *  removed, so the next picker shows it without reloading the page. */
export function invalidatePeople(): void {
  delete cache.tribe;
  delete cache.all;
}

/** Active accounts from GET /api/tribes/people, shared by every picker of the
 *  page and refreshed after TTL_MS or invalidatePeople(). Empty while loading or
 *  when the call fails: the fields then simply take free text. */
export function usePeople(scope: PeopleScope = "tribe"): Person[] {
  const [people, setPeople] = useState<Person[]>([]);
  useEffect(() => {
    const hit = cache[scope];
    if (!hit || Date.now() - hit.at > TTL_MS) {
      cache[scope] = {
        at: Date.now(),
        list: api.get<Person[]>(`/api/tribes/people?scope=${scope}`)
          .catch(() => { delete cache[scope]; return []; }),
      };
    }
    let alive = true;
    cache[scope]!.list.then((p) => { if (alive) setPeople(p); });
    return () => { alive = false; };
  }, [scope]);
  return people;
}
