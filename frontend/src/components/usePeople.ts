// Les personnes qu'on peut nommer dans un champ (porteur, participant, destinataire).
import { useEffect, useState } from "react";
import { api } from "../api";

export type Person = { id: number; name: string; email: string; tribe_id: number | null };

let cache: Promise<Person[]> | null = null;

/** Active accounts of one's tribe (all of them for an admin), from
 *  GET /api/tribes/people, fetched once per page load. Empty while loading or
 *  when the call fails: the fields then simply take free text. */
export function usePeople(): Person[] {
  const [people, setPeople] = useState<Person[]>([]);
  useEffect(() => {
    if (!cache) cache = api.get<Person[]>("/api/tribes/people").catch(() => { cache = null; return []; });
    let alive = true;
    cache.then((p) => { if (alive) setPeople(p); });
    return () => { alive = false; };
  }, []);
  return people;
}
