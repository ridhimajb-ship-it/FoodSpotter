import { useEffect, useId, useRef, useState } from "react";
import { Building2, MapPin, Search, Utensils, X } from "lucide-react";
import { api } from "../services/api";
import { useDebounced } from "../hooks/useFetch";
import type { Suggestion } from "../types";

interface Props { value: string; onSubmit: (q: string) => void; onPick: (s: Suggestion) => void; placeholder?: string }

const ICON = { restaurant: Building2, neighborhood: MapPin, cuisine: Utensils } as const;

export default function SearchBox({ value, onSubmit, onPick, placeholder = "Search by restaurant, area or cuisine" }: Props) {
  const [text, setText] = useState(value);
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState<Suggestion[]>([]);
  const [active, setActive] = useState(-1);
  const [failed, setFailed] = useState(false);
  const debounced = useDebounced(text, 200);
  const id = useId();
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => setText(value), [value]);
  useEffect(() => {
    if (debounced.trim().length < 2) { setItems([]); return; }
    const ctl = new AbortController();
    api.suggest(debounced.trim(), ctl.signal).then((r) => { setItems(r.suggestions); setFailed(false); }).catch((e) => { if (e.name !== "AbortError") setFailed(true); });
    return () => ctl.abort();
  }, [debounced]);
  useEffect(() => {
    const close = (e: MouseEvent) => { if (!box.current?.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);

  const pick = (s: Suggestion) => { setOpen(false); setActive(-1); onPick(s); };
  const submit = () => { setOpen(false); onSubmit(text.trim()); };
  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") { e.preventDefault(); setOpen(true); setActive((a) => Math.min(items.length - 1, a + 1)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setActive((a) => Math.max(-1, a - 1)); }
    else if (e.key === "Enter") { e.preventDefault(); if (open && active >= 0 && items[active]) pick(items[active]); else submit(); }
    else if (e.key === "Escape") setOpen(false);
  };

  return (
    <div ref={box} className="relative" role="search">
      <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" aria-hidden />
      <input
        className="field pl-9 pr-9" type="search" value={text} placeholder={placeholder} aria-label="Search restaurants"
        role="combobox" aria-expanded={open && items.length > 0} aria-controls={`${id}-list`} aria-autocomplete="list"
        aria-activedescendant={active >= 0 ? `${id}-${active}` : undefined}
        onChange={(e) => { setText(e.target.value); setOpen(true); setActive(-1); }} onFocus={() => setOpen(true)} onKeyDown={onKey}
      />
      {text && (
        <button type="button" aria-label="Clear search" className="absolute right-2 top-1/2 -translate-y-1/2 rounded p-1 text-muted hover:text-ink" onClick={() => { setText(""); setItems([]); onSubmit(""); }}>
          <X className="h-4 w-4" aria-hidden />
        </button>
      )}
      {open && text.trim().length >= 2 && (
        <ul id={`${id}-list`} role="listbox" className="absolute left-0 right-0 top-full z-[1500] mt-1 max-h-80 overflow-auto rounded-xl border border-line bg-white py-1 shadow-lift">
          {failed && <li className="px-3 py-2 text-sm text-neg">Suggestions are unavailable right now. Press Enter to search anyway.</li>}
          {!failed && items.length === 0 && <li className="px-3 py-2 text-sm text-muted">No matches. Press Enter to search the full list.</li>}
          {items.map((s, i) => {
            const Icon = ICON[s.type];
            return (
              <li key={`${s.type}-${s.value}`} id={`${id}-${i}`} role="option" aria-selected={i === active}
                  className={`flex cursor-pointer items-center gap-2 px-3 py-2 text-sm ${i === active ? "bg-leaf-soft" : "hover:bg-paper"}`}
                  onMouseDown={(e) => { e.preventDefault(); pick(s); }} onMouseEnter={() => setActive(i)}>
                <Icon className="h-4 w-4 shrink-0 text-leaf" aria-hidden />
                <span className="truncate font-medium">{s.label}</span>
                <span className="ml-auto shrink-0 text-xs text-muted">{s.type === "restaurant" ? s.neighborhood_label ?? "Restaurant" : s.type === "neighborhood" ? "Area" : "Cuisine"}</span>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
