"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";

import { listCities } from "@/lib/api";
import type { City } from "@/lib/types";

export interface Cities {
  /** The supported cities; null until the backend has answered, or when it failed. */
  cities: City[] | null;
  failed: boolean;
  /** Ask again after a failure. */
  retry: () => void;
}

const CitiesContext = createContext<Cities | null>(null);

/** The cities plans can be made for (GET /cities), read once for every page. */
export function CitiesProvider({ children }: { children: ReactNode }) {
  const [cities, setCities] = useState<City[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let cancelled = false;
    listCities()
      .then((list) => {
        if (cancelled) return;
        setCities(list);
        setFailed(false);
      })
      .catch(() => {
        if (!cancelled) setFailed(true);
      });
    return () => {
      cancelled = true;
    };
  }, [attempt]);

  const retry = useCallback(() => {
    setFailed(false);
    setAttempt((n) => n + 1);
  }, []);
  const value = useMemo(() => ({ cities, failed, retry }), [cities, failed, retry]);
  return <CitiesContext value={value}>{children}</CitiesContext>;
}

export function useCities(): Cities {
  const cities = useContext(CitiesContext);
  if (!cities) throw new Error("useCities needs a <CitiesProvider>");
  return cities;
}
