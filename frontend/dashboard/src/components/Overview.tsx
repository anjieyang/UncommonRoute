import {
  Card,
  Metric,
  Text,
  BarList,
  DonutChart,
  Grid,
  Title,
} from "@tremor/react";
import type { Health, Stats } from "../api";

const TIER_COLORS: Record<string, string> = {
  SIMPLE: "emerald",
  MEDIUM: "blue",
  COMPLEX: "amber",
  REASONING: "violet",
};

interface Props {
  stats: Stats | null;
  health: Health | null;
}

export default function Overview({ stats, health }: Props) {
  const total = stats?.total_requests ?? 0;

  if (total === 0) {
    return <Onboarding />;
  }

  const savings =
    stats?.avg_savings != null
      ? `${(stats.avg_savings * 100).toFixed(0)}%`
      : "—";
  const latency =
    stats?.avg_latency_us != null
      ? `${Math.round(stats.avg_latency_us)}µs`
      : "—";
  const sessionCount = health?.sessions?.count ?? 0;
  const cost =
    stats?.total_actual_cost != null
      ? `$${stats.total_actual_cost.toFixed(4)}`
      : "—";

  const tierData = ["SIMPLE", "MEDIUM", "COMPLEX", "REASONING"]
    .map((t) => {
      const d = stats?.by_tier?.[t];
      return d ? { name: t, value: d.count } : null;
    })
    .filter(Boolean) as { name: string; value: number }[];

  const modelData = Object.entries(stats?.by_model ?? {})
    .sort(([, a], [, b]) => b.count - a.count)
    .slice(0, 8)
    .map(([name, d]) => ({ name, value: d.count }));

  return (
    <div className="mt-6 space-y-6">
      <Grid numItemsMd={3} numItemsLg={5} className="gap-4">
        <KPI label="Total Requests" value={total.toLocaleString()} />
        <KPI label="Avg Savings" value={savings} />
        <KPI label="Avg Latency" value={latency} />
        <KPI label="Active Sessions" value={sessionCount.toString()} />
        <KPI label="Total Cost" value={cost} />
      </Grid>

      <Grid numItemsMd={2} className="gap-4">
        <Card decoration="top" decorationColor="blue">
          <Title>Tier Distribution</Title>
          {tierData.length > 0 ? (
            <DonutChart
              className="mt-4 h-48"
              data={tierData}
              category="value"
              index="name"
              colors={tierData.map((t) => TIER_COLORS[t.name] ?? "gray")}
              showAnimation
              showTooltip
              valueFormatter={(v) =>
                `${v} (${total ? ((v / total) * 100).toFixed(1) : 0}%)`
              }
            />
          ) : (
            <Text className="mt-8 text-center text-gray-500">No data yet</Text>
          )}
        </Card>

        <Card decoration="top" decorationColor="blue">
          <Title>Top Models</Title>
          {modelData.length > 0 ? (
            <BarList data={modelData} className="mt-4" color="blue" />
          ) : (
            <Text className="mt-8 text-center text-gray-500">No data yet</Text>
          )}
        </Card>
      </Grid>
    </div>
  );
}

function KPI({ label, value }: { label: string; value: string }) {
  return (
    <Card>
      <Text>{label}</Text>
      <Metric className="mt-1">{value}</Metric>
    </Card>
  );
}

function Onboarding() {
  return (
    <div className="mt-6">
      <Card className="mx-auto max-w-2xl">
        <Title>Getting Started</Title>
        <Text className="mt-2">
          UncommonRoute is running. Send requests through the proxy to see
          routing stats here.
        </Text>

        <div className="mt-6 space-y-4 text-sm">
          <Step n={1} title="Point your client to the proxy">
            <code className="text-blue-400">
              http://127.0.0.1:8403/v1
            </code>
          </Step>

          <Step n={2} title='Set model to "uncommon-route/auto"'>
            <span className="text-gray-400">
              The router picks the optimal model for each request.
            </span>
          </Step>

          <Step n={3} title="Python example">
            <pre className="mt-2 overflow-x-auto rounded-lg bg-gray-900 p-3 text-xs leading-relaxed text-gray-300">
{`from openai import OpenAI

client = OpenAI(
    base_url="http://127.0.0.1:8403/v1",
    api_key="your-upstream-key",
)
resp = client.chat.completions.create(
    model="uncommon-route/auto",
    messages=[{"role": "user", "content": "hello"}],
)
print(resp.choices[0].message.content)`}
            </pre>
          </Step>
        </div>

        <Text className="mt-6 text-xs text-gray-500">
          This page updates automatically once requests start flowing.
        </Text>
      </Card>
    </div>
  );
}

function Step({
  n,
  title,
  children,
}: {
  n: number;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex gap-3">
      <span className="flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-full bg-blue-950 text-xs font-semibold text-blue-400">
        {n}
      </span>
      <div>
        <p className="font-medium text-gray-200">{title}</p>
        <div className="mt-0.5 text-gray-400">{children}</div>
      </div>
    </div>
  );
}
