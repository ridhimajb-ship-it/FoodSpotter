import { createContext, ReactNode, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";

const KEY = "foodspotter.compare";
const MAX = 3;
interface Ctx { ids: number[]; add: (id: number) => boolean; remove: (id: number) => void; toggle: (id: number) => boolean; clear: () => void; has: (id: number) => boolean; full: boolean }
const CompareCtx = createContext<Ctx | null>(null);

function load(): number[] {
  try {
    const v = JSON.parse(localStorage.getItem(KEY) ?? "[]");
    return Array.isArray(v) ? v.filter((x) => Number.isInteger(x)).slice(0, MAX) : [];
  } catch { return []; }
}

export function CompareProvider({ children }: { children: ReactNode }) {
  const [ids, setIds] = useState<number[]>(load);
  useEffect(() => { try { localStorage.setItem(KEY, JSON.stringify(ids)); } catch { /* storage unavailable */ } }, [ids]);
  const idsRef = useRef(ids);   // synchronous view of the latest list, so add() can report the real outcome
  const commit = useCallback((next: number[]) => { idsRef.current = next; setIds(next); }, []);
  const add = useCallback((id: number) => {
    const cur = idsRef.current;
    if (cur.includes(id)) return true;
    if (cur.length >= MAX) return false;
    commit([...cur, id]);
    return true;
  }, [commit]);
  const remove = useCallback((id: number) => commit(idsRef.current.filter((x) => x !== id)), [commit]);
  const value = useMemo<Ctx>(() => ({
    ids, add, remove, clear: () => commit([]), has: (id) => ids.includes(id), full: ids.length >= MAX,
    toggle: (id) => { if (ids.includes(id)) { remove(id); return true; } return add(id); },
  }), [ids, add, remove, commit]);
  return <CompareCtx.Provider value={value}>{children}</CompareCtx.Provider>;
}

export function useCompare(): Ctx {
  const c = useContext(CompareCtx);
  if (!c) throw new Error("useCompare must be used inside <CompareProvider>");
  return c;
}
