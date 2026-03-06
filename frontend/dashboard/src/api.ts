export interface Health {
  status: string;
  version: string;
  upstream: string;
  sessions: { count: number; sessions: Session[] };
  spending: {
    limits: Record<string, number>;
    spent: Record<string, number>;
    remaining: Record<string, number>;
    calls: number;
  };
  providers: { count: number; names: string[]; keyed_models: string[] };
  model_mapper: {
    provider: string;
    is_gateway: boolean;
    discovered: boolean;
    upstream_models: number;
    unresolved: string[];
  };
  stats: { total_requests: number };
  feedback: { pending: number; total_updates: number; online_model: boolean };
}

export interface TierStats {
  count: number;
  avg_confidence: number;
  avg_savings: number;
  total_cost: number;
}

export interface ModelStats {
  count: number;
  total_cost: number;
}

export interface Stats {
  total_requests: number;
  time_range_s: number;
  avg_confidence: number;
  avg_savings: number;
  avg_latency_us: number;
  total_estimated_cost: number;
  total_actual_cost: number;
  by_tier: Record<string, TierStats>;
  by_model: Record<string, ModelStats>;
  by_method: Record<string, number>;
}

export interface MappingRow {
  internal: string;
  resolved: string;
  mapped: boolean;
  available: boolean | null;
}

export interface Mapping {
  provider: string;
  is_gateway: boolean;
  discovered: boolean;
  upstream_model_count: number;
  mappings: MappingRow[];
  unresolved: string[];
}

export interface Session {
  id: string;
  model: string;
  tier: string;
  requests: number;
  age_s: number;
}

export interface Spend {
  limits: Record<string, number>;
  spent: Record<string, number>;
  remaining: Record<string, number>;
  calls: number;
}

async function get<T>(path: string): Promise<T | null> {
  try {
    const res = await fetch(path);
    return res.ok ? ((await res.json()) as T) : null;
  } catch {
    return null;
  }
}

export const fetchHealth = () => get<Health>("/health");
export const fetchStats = () => get<Stats>("/v1/stats");
export const fetchMapping = () => get<Mapping>("/v1/models/mapping");
export const fetchSessions = () =>
  get<{ count: number; sessions: Session[] }>("/v1/sessions");
export const fetchSpend = () => get<Spend>("/v1/spend");

export async function setSpendLimit(
  window: string,
  amount: number,
): Promise<boolean> {
  try {
    const res = await fetch("/v1/spend", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: "set", window, amount }),
    });
    return res.ok;
  } catch {
    return false;
  }
}

export async function clearSpendLimit(window: string): Promise<boolean> {
  try {
    const res = await fetch("/v1/spend", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: "clear", window }),
    });
    return res.ok;
  } catch {
    return false;
  }
}
