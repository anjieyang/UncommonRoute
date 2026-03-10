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
  routing_config?: { source: string; editable: boolean };
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
  avg_latency_ms: number;
  avg_input_reduction_ratio: number;
  avg_cache_hit_ratio: number;
  total_estimated_cost: number;
  total_baseline_cost: number;
  total_actual_cost: number;
  total_savings_absolute: number;
  total_savings_ratio: number;
  total_cache_savings: number;
  total_compaction_savings: number;
  total_cache_breakpoints: number;
  total_input_tokens_before: number;
  total_input_tokens_after: number;
  by_tier: Record<string, TierStats>;
  by_model: Record<string, ModelStats>;
  by_transport: Record<string, ModelStats>;
  by_cache_mode: Record<string, ModelStats>;
  by_cache_family: Record<string, ModelStats>;
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

export interface RoutingTierConfig {
  primary: string;
  fallback: string[];
  overridden: boolean;
  hard_pin: boolean;
  selection_mode: "adaptive" | "hard-pin";
}

export interface RoutingProfileConfig {
  tiers: Record<string, RoutingTierConfig>;
}

export interface RoutingConfigState {
  source: string;
  editable: boolean;
  profiles: Record<string, RoutingProfileConfig>;
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
export const fetchRoutingConfig = () => get<RoutingConfigState>("/v1/routing-config");

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

export async function setRoutingTier(
  profile: string,
  tier: string,
  primary: string,
  fallback: string[],
  selectionMode: "adaptive" | "hard-pin",
): Promise<RoutingConfigState | null> {
  try {
    const res = await fetch("/v1/routing-config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: "set-tier", profile, tier, primary, fallback, selection_mode: selectionMode }),
    });
    return res.ok ? ((await res.json()) as RoutingConfigState) : null;
  } catch {
    return null;
  }
}

export async function resetRoutingTier(
  profile: string,
  tier: string,
): Promise<RoutingConfigState | null> {
  try {
    const res = await fetch("/v1/routing-config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: "reset-tier", profile, tier }),
    });
    return res.ok ? ((await res.json()) as RoutingConfigState) : null;
  } catch {
    return null;
  }
}

export async function resetRoutingConfig(): Promise<RoutingConfigState | null> {
  try {
    const res = await fetch("/v1/routing-config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: "reset" }),
    });
    return res.ok ? ((await res.json()) as RoutingConfigState) : null;
  } catch {
    return null;
  }
}

export interface RecentRequest {
  request_id: string;
  timestamp: number;
  model: string;
  tier: string;
  method: string;
  cost: number;
  savings: number;
  transport: string;
  cache_mode: string;
  cache_family: string;
  cache_breakpoints: number;
  prompt_preview: string;
  feedback_pending: boolean;
}

export interface FeedbackResult {
  ok: boolean;
  action: string;
  from_tier: string;
  to_tier: string;
  reason?: string;
  total_updates: number;
}

export const fetchRecent = (limit = 30) =>
  get<RecentRequest[]>(`/v1/stats/recent?limit=${limit}`);

export async function submitFeedback(
  requestId: string,
  signal: "ok" | "weak" | "strong",
): Promise<FeedbackResult | null> {
  try {
    const res = await fetch("/v1/feedback", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ request_id: requestId, signal }),
    });
    return res.ok ? ((await res.json()) as FeedbackResult) : null;
  } catch {
    return null;
  }
}
