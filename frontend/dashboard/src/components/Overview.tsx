import type { Health, Stats } from "../api";

const TIER_BAR: Record<string, string> = {
  SIMPLE: "bg-emerald-400/70",
  MEDIUM: "bg-sky-400/70",
  COMPLEX: "bg-orange-400/70",
  REASONING: "bg-violet-400/70",
};
const TIER_DOT: Record<string, string> = {
  SIMPLE: "bg-emerald-400",
  MEDIUM: "bg-sky-400",
  COMPLEX: "bg-orange-400",
  REASONING: "bg-violet-400",
};
const TIER_LABEL: Record<string, string> = {
  SIMPLE: "text-emerald-300/80",
  MEDIUM: "text-sky-300/80",
  COMPLEX: "text-orange-300/80",
  REASONING: "text-violet-300/80",
};

interface Props {
  stats: Stats | null;
  health: Health | null;
}

function money(value: number | null | undefined): string {
  if (value == null) return "—";
  return `$${value.toFixed(4)}`;
}

function percent(value: number | null | undefined): string {
  if (value == null) return "—";
  return `${(value * 100).toFixed(1)}%`;
}

export default function Overview({ stats, health }: Props) {
  const total = stats?.total_requests ?? 0;

  if (total === 0) return <Onboarding />;

  const sessionCount = health?.sessions?.count ?? 0;
  const latency = stats?.avg_latency_ms != null ? `${stats.avg_latency_ms.toFixed(1)}ms` : "—";
  const baselineCost = stats?.total_baseline_cost ?? 0;
  const actualCost = stats?.total_actual_cost ?? 0;
  const saved = stats?.total_savings_absolute ?? 0;
  const savedRatio = stats?.total_savings_ratio ?? 0;
  const cacheSavings = stats?.total_cache_savings ?? 0;
  const compactionSavings = stats?.total_compaction_savings ?? 0;
  const breakpoints = stats?.total_cache_breakpoints ?? 0;
  const nativeAnthropic = stats?.by_transport?.["anthropic-messages"]?.count ?? 0;
  const promptCacheKey = stats?.by_cache_mode?.prompt_cache_key?.count ?? 0;
  const cacheControl = stats?.by_cache_mode?.cache_control?.count ?? 0;

  const tiers = ["SIMPLE", "MEDIUM", "COMPLEX", "REASONING"]
    .map((name) => ({ name, count: stats?.by_tier?.[name]?.count ?? 0 }))
    .filter((tier) => tier.count > 0);

  const models = Object.entries(stats?.by_model ?? {})
    .sort(([, a], [, b]) => b.count - a.count)
    .slice(0, 6);
  const maxModelCount = models.length > 0 ? models[0][1].count : 1;

  return (
    <div className="space-y-14">
      <section className="rounded-[28px] border border-white/[0.07] bg-[radial-gradient(circle_at_top_left,_rgba(255,255,255,0.08),_transparent_45%),linear-gradient(180deg,_rgba(255,255,255,0.04),_rgba(255,255,255,0.01))] px-8 py-8">
        <div className="grid grid-cols-1 xl:grid-cols-[1.35fr_1fr] gap-10">
          <div>
            <p className="text-[12px] font-medium text-[#7b7b80] uppercase tracking-[0.12em] mb-3">Cost Delta</p>
            <div className="flex items-end gap-4 flex-wrap">
              <div>
                <p className="text-[14px] text-[#7b7b80] mb-1">Would Have Paid</p>
                <p className="text-[44px] font-semibold text-white tracking-tighter leading-none">{money(baselineCost)}</p>
              </div>
              <div className="text-[28px] text-[#4b4b4f] pb-1">→</div>
              <div>
                <p className="text-[14px] text-[#7b7b80] mb-1">Actually Paid</p>
                <p className="text-[44px] font-semibold text-emerald-300 tracking-tighter leading-none">{money(actualCost)}</p>
              </div>
            </div>
            <div className="mt-5 flex items-end gap-4 flex-wrap">
              <div>
                <p className="text-[12px] text-[#7b7b80] uppercase tracking-[0.08em]">Saved</p>
                <p className="text-[28px] font-semibold text-white font-mono tracking-tight">{money(saved)}</p>
              </div>
              <div>
                <p className="text-[12px] text-[#7b7b80] uppercase tracking-[0.08em]">Reduction</p>
                <p className="text-[28px] font-semibold text-sky-300 font-mono tracking-tight">{percent(savedRatio)}</p>
              </div>
            </div>
            <p className="mt-4 text-[13px] text-[#6e6e72] max-w-2xl leading-relaxed">
              Baseline uses fully uncached Claude Opus 4.6 list pricing on the full request context, without UncommonRoute routing or prompt shrinking. Actual spend includes side-channel compression cost.
            </p>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <MetricCard label="Cache Delta" value={money(cacheSavings)} note="net cached-read minus cache-write effect" accent="text-sky-300" />
            <MetricCard label="Prompt Shrink" value={money(compactionSavings)} note={`${stats?.total_input_tokens_before?.toLocaleString() ?? "0"} → ${stats?.total_input_tokens_after?.toLocaleString() ?? "0"} input tokens`} accent="text-emerald-300" />
            <MetricCard label="Requests" value={total.toLocaleString()} note={`${sessionCount} active sessions`} />
            <MetricCard label="Avg Latency" value={latency} note={`${breakpoints.toLocaleString()} cache breakpoints`} />
          </div>
        </div>
      </section>

      <section>
        <p className="text-[12px] font-medium text-[#6e6e72] uppercase tracking-[0.08em] mb-5">Savings Breakdown</p>
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
          <MiniStat label="Router Total" value={money(saved)} sub={percent(savedRatio)} />
          <MiniStat label="Cache Savings" value={money(cacheSavings)} sub={`${(((stats?.avg_cache_hit_ratio ?? 0) * 100)).toFixed(1)}% avg cache hit`} />
          <MiniStat label="Compaction Savings" value={money(compactionSavings)} sub={`${((stats?.avg_input_reduction_ratio ?? 0) * 100).toFixed(1)}% avg shrink`} />
          <MiniStat label="Cache Routing" value={`${(nativeAnthropic + promptCacheKey + cacheControl).toLocaleString()}`} sub={`${nativeAnthropic} native / ${cacheControl} cache_control / ${promptCacheKey} prompt_cache_key`} />
        </div>
      </section>

      <section>
        <p className="text-[12px] font-medium text-[#6e6e72] uppercase tracking-[0.08em] mb-5">Tier Distribution</p>

        <div className="h-[6px] w-full rounded-full overflow-hidden flex bg-white/[0.06] mb-5">
          {tiers.map((tier) => (
            <div
              key={tier.name}
              className={`h-full ${TIER_BAR[tier.name]} first:rounded-l-full last:rounded-r-full`}
              style={{ width: `${(tier.count / total) * 100}%` }}
            />
          ))}
        </div>

        <div className="flex flex-wrap gap-x-6 gap-y-2">
          {tiers.map((tier) => (
            <div key={tier.name} className="flex items-center gap-2">
              <div className={`h-[8px] w-[8px] rounded-[2px] ${TIER_DOT[tier.name]}`} />
              <span className={`text-[13px] font-medium ${TIER_LABEL[tier.name]}`}>{tier.name}</span>
              <span className="text-[13px] font-mono text-[#6e6e72]">{tier.count}</span>
              <span className="text-[13px] font-mono text-[#4a4a4d]">{((tier.count / total) * 100).toFixed(0)}%</span>
            </div>
          ))}
        </div>
      </section>

      <section>
        <p className="text-[12px] font-medium text-[#6e6e72] uppercase tracking-[0.08em] mb-5">Model Usage</p>
        <div className="space-y-5">
          {models.map(([name, data]) => (
            <div key={name}>
              <div className="flex items-baseline justify-between mb-2">
                <span className="text-[14px] font-mono text-[#b4b4b7]">{name}</span>
                <div className="flex items-baseline gap-4">
                  <span className="text-[14px] font-mono text-[#8b8b8e]">{data.count}</span>
                  <span className="text-[12px] font-mono text-[#5a5a5d]">${data.total_cost.toFixed(4)}</span>
                </div>
              </div>
              <div className="h-[4px] w-full bg-white/[0.05] rounded-full overflow-hidden">
                <div className="h-full bg-white/[0.18] rounded-full" style={{ width: `${(data.count / maxModelCount) * 100}%` }} />
              </div>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}

function MetricCard({
  label,
  value,
  note,
  accent = "text-white",
}: {
  label: string;
  value: string;
  note: string;
  accent?: string;
}) {
  return (
    <div className="rounded-2xl border border-white/[0.06] bg-black/20 px-4 py-4">
      <p className="text-[11px] font-medium text-[#5a5a5d] uppercase tracking-[0.08em]">{label}</p>
      <p className={`mt-3 text-[24px] font-semibold font-mono tracking-tight ${accent}`}>{value}</p>
      <p className="mt-1 text-[12px] text-[#5a5a5d]">{note}</p>
    </div>
  );
}

function MiniStat({ label, value, sub }: { label: string; value: string; sub: string }) {
  return (
    <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] px-4 py-4">
      <p className="text-[11px] font-medium text-[#5a5a5d] uppercase tracking-[0.08em]">{label}</p>
      <p className="mt-3 text-[22px] font-semibold text-white font-mono tracking-tight">{value}</p>
      <p className="mt-1 text-[12px] font-mono text-[#5a5a5d]">{sub}</p>
    </div>
  );
}

function Onboarding() {
  return (
    <div className="max-w-lg pt-8">
      <h1 className="text-[22px] font-semibold text-white tracking-tight mb-3">Waiting for requests</h1>
      <p className="text-[14px] text-[#8b8b8e] leading-relaxed mb-10">
        Point your client to the proxy and set the model to <code className="font-mono text-[#b4b4b7]">uncommon-route/auto</code>.
      </p>
      <pre className="text-[12px] font-mono text-[#7a7a7d] leading-[1.7] bg-[#0c0c0e] border border-white/[0.06] rounded-lg p-5 overflow-x-auto">
{`from openai import OpenAI

client = OpenAI(
    base_url="http://127.0.0.1:8403/v1",
    api_key="your-upstream-key",
)
resp = client.chat.completions.create(
    model="uncommon-route/auto",
    messages=[{"role": "user", "content": "hello"}],
)`}
      </pre>
    </div>
  );
}
