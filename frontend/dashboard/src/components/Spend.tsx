import { useState } from "react";
import {
  Card,
  Metric,
  Text,
  Title,
  Badge,
  Button,
  Table,
  TableHead,
  TableHeaderCell,
  TableBody,
  TableRow,
  TableCell,
  Select,
  SelectItem,
  NumberInput,
  Grid,
} from "@tremor/react";
import { setSpendLimit, clearSpendLimit, type Spend } from "../api";

const WINDOWS = ["per_request", "hourly", "daily", "session"];

interface Props {
  spend: Spend | null;
  onRefresh: () => void;
}

export default function SpendPanel({ spend, onRefresh }: Props) {
  const [window, setWindow] = useState("hourly");
  const [amount, setAmount] = useState<number>(5);
  const [busy, setBusy] = useState(false);

  const limits = spend?.limits ?? {};
  const spent = spend?.spent ?? {};
  const remaining = spend?.remaining ?? {};
  const calls = spend?.calls ?? 0;

  const activeWindows = WINDOWS.filter((w) => limits[w] != null);

  async function handleSet() {
    setBusy(true);
    await setSpendLimit(window, amount);
    onRefresh();
    setBusy(false);
  }

  async function handleClear() {
    setBusy(true);
    await clearSpendLimit(window);
    onRefresh();
    setBusy(false);
  }

  return (
    <div className="mt-6 space-y-6">
      <Card>
        <Text>Total Calls</Text>
        <Metric className="mt-1">{calls}</Metric>
      </Card>

      <Card>
        <Title>Set Limit</Title>
        <div className="mt-4 flex flex-wrap items-end gap-3">
          <div>
            <Text className="mb-1">Window</Text>
            <Select value={window} onValueChange={setWindow}>
              {WINDOWS.map((w) => (
                <SelectItem key={w} value={w}>
                  {w}
                </SelectItem>
              ))}
            </Select>
          </div>
          <div>
            <Text className="mb-1">Amount ($)</Text>
            <NumberInput
              value={amount}
              onValueChange={setAmount}
              min={0}
              step={0.5}
              placeholder="0.00"
            />
          </div>
          <Button loading={busy} onClick={handleSet}>
            Set
          </Button>
          <Button variant="secondary" loading={busy} onClick={handleClear}>
            Clear
          </Button>
        </div>
      </Card>

      <Card>
        <Title>Current Limits</Title>
        <Table className="mt-4">
          <TableHead>
            <TableRow>
              <TableHeaderCell>Window</TableHeaderCell>
              <TableHeaderCell className="text-right">Limit</TableHeaderCell>
              <TableHeaderCell className="text-right">Spent</TableHeaderCell>
              <TableHeaderCell className="text-right">
                Remaining
              </TableHeaderCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {activeWindows.length > 0 ? (
              activeWindows.map((w) => (
                <TableRow key={w}>
                  <TableCell>
                    <Badge color="gray" size="xs">
                      {w}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-right font-mono">
                    ${limits[w].toFixed(2)}
                  </TableCell>
                  <TableCell className="text-right font-mono">
                    ${(spent[w] ?? 0).toFixed(4)}
                  </TableCell>
                  <TableCell className="text-right font-mono">
                    {remaining[w] != null
                      ? `$${remaining[w].toFixed(4)}`
                      : "—"}
                  </TableCell>
                </TableRow>
              ))
            ) : (
              <TableRow>
                <TableCell colSpan={4}>
                  <Text className="text-center text-gray-500">
                    No limits set
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
