import { useEffect, useState } from "react";
import {
  fetchRoutingConfig,
  resetRoutingConfig,
  resetRoutingTier,
  setRoutingTier,
  type RoutingConfigState,
} from "../api";

const PROFILES = ["free", "eco", "auto", "premium", "agentic"];
const TIERS = ["SIMPLE", "MEDIUM", "COMPLEX", "REASONING"];

interface Props {
  data: RoutingConfigState | null;
  onRefresh: () => void;
}

interface DraftRow {
  primary: string;
  fallback: string;
  selectionMode: "adaptive" | "hard-pin";
}

function buildDrafts(data: RoutingConfigState | null): Record<string, DraftRow> {
  const next: Record<string, DraftRow> = {};
  for (const profile of PROFILES) {
    const tiers = data?.profiles?.[profile]?.tiers ?? {};
    for (const tier of TIERS) {
      const row = tiers[tier];
      next[`${profile}:${tier}`] = {
        primary: row?.primary ?? "",
        fallback: row?.fallback?.join(", ") ?? "",
        selectionMode: row?.selection_mode ?? "adaptive",
      };
    }
  }
  return next;
}

export default function RoutingConfig({ data, onRefresh }: Props) {
  const [state, setState] = useState<RoutingConfigState | null>(data);
  const [drafts, setDrafts] = useState<Record<string, DraftRow>>(buildDrafts(data));
  const [busy, setBusy] = useState<string | null>(null);

  useEffect(() => {
    setState(data);
    setDrafts(buildDrafts(data));
  }, [data]);

  async function refreshLocal() {
    const latest = await fetchRoutingConfig();
    if (latest) {
      setState(latest);
      setDrafts(buildDrafts(latest));
    }
    onRefresh();
  }

  function setDraft(profile: string, tier: string, patch: Partial<DraftRow>) {
    const key = `${profile}:${tier}`;
    setDrafts((prev) => ({
      ...prev,
      [key]: { ...prev[key], ...patch },
    }));
  }

  async function handleSave(profile: string, tier: string) {
    const key = `${profile}:${tier}`;
    const row = drafts[key];
    if (!row?.primary.trim()) return;
    setBusy(key);
    const fallback = row.fallback
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean);
    const next = await setRoutingTier(profile, tier, row.primary.trim(), fallback, row.selectionMode);
    if (next) {
      setState(next);
      setDrafts(buildDrafts(next));
    }
    setBusy(null);
    onRefresh();
  }

  async function handleResetTier(profile: string, tier: string) {
    const key = `${profile}:${tier}`;
    setBusy(key);
    const next = await resetRoutingTier(profile, tier);
    if (next) {
      setState(next);
      setDrafts(buildDrafts(next));
    }
    setBusy(null);
    onRefresh();
  }

  async function handleResetAll() {
    setBusy("all");
    const next = await resetRoutingConfig();
    if (next) {
      setState(next);
      setDrafts(buildDrafts(next));
    }
    setBusy(null);
    onRefresh();
  }

  const current = state ?? data;

  return (
    <div>
      <div className="flex items-baseline justify-between gap-4 mb-10">
        <div>
          <h1 className="text-[18px] font-semibold text-white tracking-tight">Routing Config</h1>
          <p className="text-[14px] text-[#6e6e72] mt-1.5">
            Override primary and fallback models per profile/tier. Changes here apply to the running proxy immediately.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-[12px] font-mono text-[#6e6e72]">
            {current?.source ?? "local-file"}
          </span>
          <button
            disabled={busy === "all"}
            onClick={handleResetAll}
            className="border border-white/[0.10] text-[#8b8b8e] px-4 py-2 rounded-lg text-[13px] font-medium hover:text-white hover:border-white/20 transition-colors disabled:opacity-40"
          >
            Reset All
          </button>
        </div>
      </div>

      <div className="space-y-10">
        {PROFILES.map((profile) => (
          <section key={profile}>
            <div className="flex items-center gap-3 mb-4">
              <h2 className="text-[14px] font-semibold uppercase tracking-[0.12em] text-white/85">{profile}</h2>
              <span className="text-[11px] font-mono text-[#4a4a4d]">profile</span>
            </div>
            <div className="border border-white/[0.07] rounded-2xl overflow-hidden">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-white/[0.07] bg-white/[0.02]">
                    <th className="text-left text-[11px] font-medium text-[#5a5a5d] uppercase tracking-[0.06em] py-3 px-4 w-28">Tier</th>
                    <th className="text-left text-[11px] font-medium text-[#5a5a5d] uppercase tracking-[0.06em] py-3 px-4">Primary</th>
                    <th className="text-left text-[11px] font-medium text-[#5a5a5d] uppercase tracking-[0.06em] py-3 px-4">Fallback</th>
                    <th className="text-right text-[11px] font-medium text-[#5a5a5d] uppercase tracking-[0.06em] py-3 px-4 w-40">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {TIERS.map((tier) => {
                    const key = `${profile}:${tier}`;
                    const row = current?.profiles?.[profile]?.tiers?.[tier];
                    const draft = drafts[key] ?? { primary: "", fallback: "", selectionMode: "adaptive" as const };
                    const rowBusy = busy === key;
                    return (
                      <tr key={key} className="border-b last:border-b-0 border-white/[0.04] hover:bg-white/[0.02] transition-colors">
                        <td className="px-4 py-3.5">
                          <div className="text-[12px] font-mono text-[#b4b4b7]">{tier}</div>
                          {row?.overridden && (
                            <div className="text-[11px] font-mono text-sky-400/80 mt-1">override</div>
                          )}
                        </td>
                        <td className="px-4 py-3.5">
                          <div className="space-y-2">
                            <input
                              value={draft.primary}
                              onChange={(e) => setDraft(profile, tier, { primary: e.target.value })}
                              className="w-full bg-transparent border border-white/[0.10] text-[#b4b4b7] rounded-lg px-3 py-2 text-[13px] font-mono"
                            />
                            <div className="flex items-center gap-2">
                              <button
                                type="button"
                                onClick={() => setDraft(profile, tier, { selectionMode: "adaptive" })}
                                className={`px-2.5 py-1 rounded-full text-[11px] font-medium transition-colors ${
                                  draft.selectionMode === "adaptive"
                                    ? "bg-white/90 text-[#111113]"
                                    : "border border-white/[0.10] text-[#8b8b8e] hover:text-white"
                                }`}
                              >
                                Adaptive
                              </button>
                              <button
                                type="button"
                                onClick={() => setDraft(profile, tier, { selectionMode: "hard-pin" })}
                                className={`px-2.5 py-1 rounded-full text-[11px] font-medium transition-colors ${
                                  draft.selectionMode === "hard-pin"
                                    ? "bg-sky-400/90 text-[#111113]"
                                    : "border border-white/[0.10] text-[#8b8b8e] hover:text-white"
                                }`}
                              >
                                Hard Pin
                              </button>
                            </div>
                          </div>
                        </td>
                        <td className="px-4 py-3.5">
                          <input
                            value={draft.fallback}
                            onChange={(e) => setDraft(profile, tier, { fallback: e.target.value })}
                            className="w-full bg-transparent border border-white/[0.10] text-[#8b8b8e] rounded-lg px-3 py-2 text-[13px] font-mono"
                            placeholder="model-a, model-b, model-c"
                          />
                        </td>
                        <td className="px-4 py-3.5">
                          <div className="flex justify-end gap-2">
                            <button
                              disabled={rowBusy}
                              onClick={() => handleSave(profile, tier)}
                              className="bg-white/90 text-[#111113] px-3.5 py-2 rounded-lg text-[12px] font-medium hover:bg-white transition-colors disabled:opacity-40"
                            >
                              Save
                            </button>
                            <button
                              disabled={rowBusy}
                              onClick={() => handleResetTier(profile, tier)}
                              className="border border-white/[0.10] text-[#8b8b8e] px-3.5 py-2 rounded-lg text-[12px] font-medium hover:text-white hover:border-white/20 transition-colors disabled:opacity-40"
                            >
                              Reset
                            </button>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </section>
        ))}
      </div>

      <div className="mt-8">
        <button
          onClick={refreshLocal}
          className="text-[12px] font-medium text-[#8b8b8e] hover:text-white transition-colors"
        >
          Refresh
        </button>
      </div>
    </div>
  );
}
