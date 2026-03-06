import {
  Card,
  Callout,
  Metric,
  Text,
  Title,
  Grid,
  Badge,
  Table,
  TableHead,
  TableHeaderCell,
  TableBody,
  TableRow,
  TableCell,
} from "@tremor/react";
import type { Mapping } from "../api";

interface Props {
  mapping: Mapping | null;
}

export default function Models({ mapping }: Props) {
  const discovered = mapping?.discovered ?? false;
  const upCount = mapping?.upstream_model_count ?? 0;
  const mapped = mapping?.mappings?.filter((r) => r.mapped).length ?? 0;
  const unresolved = mapping?.unresolved?.length ?? 0;
  const rows = mapping?.mappings ?? [];

  return (
    <div className="mt-6 space-y-6">
      <Grid numItemsMd={2} numItemsLg={4} className="gap-4">
        <Card>
          <Text>Upstream Models</Text>
          <Metric className="mt-1">{discovered ? upCount : "—"}</Metric>
        </Card>
        <Card>
          <Text>Mapped</Text>
          <Metric className="mt-1">{mapped}</Metric>
        </Card>
        <Card>
          <Text>Unresolved</Text>
          <Metric
            className="mt-1"
            color={unresolved > 0 ? "red" : undefined}
          >
            {unresolved}
          </Metric>
        </Card>
        <Card>
          <Text>Provider</Text>
          <Metric className="mt-1 text-2xl">
            {mapping?.provider ?? "—"}
          </Metric>
          {mapping?.is_gateway && (
            <Badge color="blue" size="xs" className="mt-1">
              gateway
            </Badge>
          )}
        </Card>
      </Grid>

      {!discovered && (
        <Callout title="Model discovery pending" color="gray" className="mb-4">
          The proxy discovers upstream models on startup. If no upstream is
          configured, or the API key is missing, discovery will be skipped.
          Run{" "}
          <code className="rounded bg-gray-800 px-1 text-xs">
            uncommon-route doctor
          </code>{" "}
          to diagnose.
        </Callout>
      )}

      <Card>
        <Title>Model Mapping</Title>
        <Table className="mt-4">
          <TableHead>
            <TableRow>
              <TableHeaderCell>Internal Name</TableHeaderCell>
              <TableHeaderCell>Resolved (Upstream)</TableHeaderCell>
              <TableHeaderCell>Status</TableHeaderCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {rows.length > 0 ? (
              rows.map((r) => (
                <TableRow key={r.internal}>
                  <TableCell className="font-mono text-xs">
                    {r.internal}
                  </TableCell>
                  <TableCell
                    className={`font-mono text-xs ${r.mapped ? "text-blue-400" : ""}`}
                  >
                    {r.resolved}
                  </TableCell>
                  <TableCell>
                    {r.available === true && (
                      <Badge color="emerald" size="xs">
                        available
                      </Badge>
                    )}
                    {r.available === false && (
                      <Badge color="red" size="xs">
                        not found
                      </Badge>
                    )}
                    {r.available === null && (
                      <Badge color="gray" size="xs">
                        unknown
                      </Badge>
                    )}
                  </TableCell>
                </TableRow>
              ))
            ) : (
              <TableRow>
                <TableCell colSpan={3}>
                  <Text className="text-center text-gray-500">
                    Start the proxy with an upstream to see model mapping
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
