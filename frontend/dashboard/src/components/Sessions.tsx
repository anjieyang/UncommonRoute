import {
  Card,
  Metric,
  Text,
  Title,
  Badge,
  Table,
  TableHead,
  TableHeaderCell,
  TableBody,
  TableRow,
  TableCell,
} from "@tremor/react";
import type { Session } from "../api";

const TIER_COLORS: Record<string, "emerald" | "blue" | "amber" | "violet"> = {
  SIMPLE: "emerald",
  MEDIUM: "blue",
  COMPLEX: "amber",
  REASONING: "violet",
};

function fmtAge(s: number): string {
  if (s < 60) return `${s}s`;
  if (s < 3600) return `${Math.floor(s / 60)}m`;
  return `${Math.floor(s / 3600)}h`;
}

interface Props {
  data: { count: number; sessions: Session[] } | null;
}

export default function Sessions({ data }: Props) {
  const count = data?.count ?? 0;
  const sessions = data?.sessions ?? [];

  return (
    <div className="mt-6 space-y-6">
      <Card>
        <Text>Active Sessions</Text>
        <Metric className="mt-1">{count}</Metric>
      </Card>

      <Card>
        <Title>Session List</Title>
        <Table className="mt-4">
          <TableHead>
            <TableRow>
              <TableHeaderCell>Session ID</TableHeaderCell>
              <TableHeaderCell>Model</TableHeaderCell>
              <TableHeaderCell>Tier</TableHeaderCell>
              <TableHeaderCell className="text-right">
                Requests
              </TableHeaderCell>
              <TableHeaderCell className="text-right">Age</TableHeaderCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {sessions.length > 0 ? (
              sessions.map((s) => (
                <TableRow key={s.id}>
                  <TableCell className="font-mono text-xs">{s.id}</TableCell>
                  <TableCell className="font-mono text-xs">
                    {s.model}
                  </TableCell>
                  <TableCell>
                    <Badge color={TIER_COLORS[s.tier] ?? "gray"} size="xs">
                      {s.tier}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-right font-mono">
                    {s.requests}
                  </TableCell>
                  <TableCell className="text-right font-mono">
                    {fmtAge(s.age_s)}
                  </TableCell>
                </TableRow>
              ))
            ) : (
              <TableRow>
                <TableCell colSpan={5}>
                  <Text className="text-center text-gray-500">
                    No active sessions
                  </Text>
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </Card>
    </div>
  );
}
