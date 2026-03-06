import {
  Card,
  Title,
  Table,
  TableHead,
  TableHeaderCell,
  TableBody,
  TableRow,
  TableCell,
  Badge,
  Text,
  Grid,
} from "@tremor/react";
import type { Stats } from "../api";

const TIER_COLORS: Record<string, "emerald" | "blue" | "amber" | "violet"> = {
  SIMPLE: "emerald",
  MEDIUM: "blue",
  COMPLEX: "amber",
  REASONING: "violet",
};

interface Props {
  stats: Stats | null;
}

export default function Routing({ stats }: Props) {
  const total = stats?.total_requests ?? 1;
  const tiers = ["SIMPLE", "MEDIUM", "COMPLEX", "REASONING"];

  const models = Object.entries(stats?.by_model ?? {}).sort(
    ([, a], [, b]) => b.count - a.count,
  );
  const methods = Object.entries(stats?.by_method ?? {}).sort(
    ([, a], [, b]) => b - a,
  );

  return (
    <div className="mt-6 space-y-6">
      <Card>
        <Title>By Tier</Title>
        <Table className="mt-4">
          <TableHead>
            <TableRow>
              <TableHeaderCell>Tier</TableHeaderCell>
              <TableHeaderCell className="text-right">Count</TableHeaderCell>
              <TableHeaderCell className="text-right">%</TableHeaderCell>
              <TableHeaderCell className="text-right">
                Avg Confidence
              </TableHeaderCell>
              <TableHeaderCell className="text-right">
                Avg Savings
              </TableHeaderCell>
              <TableHeaderCell className="text-right">Cost</TableHeaderCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {tiers.map((t) => {
              const d = stats?.by_tier?.[t];
              if (!d) return null;
              return (
                <TableRow key={t}>
                  <TableCell>
                    <Badge color={TIER_COLORS[t]}>{t}</Badge>
                  </TableCell>
                  <TableCell className="text-right font-mono">
                    {d.count}
                  </TableCell>
                  <TableCell className="text-right font-mono">
                    {((d.count / total) * 100).toFixed(1)}%
                  </TableCell>
                  <TableCell className="text-right font-mono">
                    {d.avg_confidence.toFixed(3)}
                  </TableCell>
                  <TableCell className="text-right font-mono">
                    {(d.avg_savings * 100).toFixed(0)}%
                  </TableCell>
                  <TableCell className="text-right font-mono">
                    ${d.total_cost.toFixed(4)}
                  </TableCell>
                </TableRow>
              );
            })}
            {!tiers.some((t) => stats?.by_tier?.[t]) && (
              <TableRow>
                <TableCell colSpan={6}>
                  <Text className="text-center text-gray-500">
                    No data yet
                  </Text>
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </Card>

      <Grid numItemsMd={2} className="gap-4">
        <Card>
          <Title>By Model</Title>
          <Table className="mt-4">
            <TableHead>
              <TableRow>
                <TableHeaderCell>Model</TableHeaderCell>
                <TableHeaderCell className="text-right">Count</TableHeaderCell>
                <TableHeaderCell className="text-right">Cost</TableHeaderCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {models.length > 0 ? (
                models.map(([m, d]) => (
                  <TableRow key={m}>
                    <TableCell className="font-mono text-xs">{m}</TableCell>
                    <TableCell className="text-right font-mono">
                      {d.count}
                    </TableCell>
                    <TableCell className="text-right font-mono">
                      ${d.total_cost.toFixed(4)}
                    </TableCell>
                  </TableRow>
                ))
              ) : (
                <TableRow>
                  <TableCell colSpan={3}>
                    <Text className="text-center text-gray-500">No data</Text>
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </Card>

        <Card>
          <Title>By Method</Title>
          <Table className="mt-4">
            <TableHead>
              <TableRow>
                <TableHeaderCell>Method</TableHeaderCell>
                <TableHeaderCell className="text-right">Count</TableHeaderCell>
                <TableHeaderCell className="text-right">%</TableHeaderCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {methods.length > 0 ? (
                methods.map(([m, c]) => (
                  <TableRow key={m}>
                    <TableCell className="font-mono text-xs">{m}</TableCell>
                    <TableCell className="text-right font-mono">{c}</TableCell>
                    <TableCell className="text-right font-mono">
                      {((c / total) * 100).toFixed(1)}%
                    </TableCell>
                  </TableRow>
                ))
              ) : (
                <TableRow>
                  <TableCell colSpan={3}>
                    <Text className="text-center text-gray-500">No data</Text>
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </Card>
      </Grid>
    </div>
  );
}
