import { useCallback, useEffect, useState } from "react";
import {
  TabGroup,
  TabList,
  Tab,
  TabPanels,
  TabPanel,
  Badge,
  Callout,
} from "@tremor/react";
import {
  fetchHealth,
  fetchStats,
  fetchMapping,
  fetchSessions,
  fetchSpend,
  type Health,
  type Stats,
  type Mapping,
  type Session,
  type Spend,
} from "./api";
import Overview from "./components/Overview";
import Routing from "./components/Routing";
import Models from "./components/Models";
import Sessions from "./components/Sessions";
import SpendPanel from "./components/Spend";

type AppState = "loading" | "unreachable" | "ready";

export default function App() {
  const [state, setState] = useState<AppState>("loading");
  const [health, setHealth] = useState<Health | null>(null);
  const [stats, setStats] = useState<Stats | null>(null);
  const [mapping, setMapping] = useState<Mapping | null>(null);
  const [sessions, setSessions] = useState<{
    count: number;
    sessions: Session[];
  } | null>(null);
  const [spend, setSpend] = useState<Spend | null>(null);

  const refresh = useCallback(async () => {
    const [h, st, m, ss, sp] = await Promise.all([
      fetchHealth(),
      fetchStats(),
      fetchMapping(),
      fetchSessions(),
      fetchSpend(),
    ]);
    if (h) {
      setHealth(h);
      setState("ready");
    } else if (state !== "ready") {
      setState("unreachable");
    }
    if (st) setStats(st);
    if (m) setMapping(m);
    if (ss) setSessions(ss);
    if (sp) setSpend(sp);
  }, [state]);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, 5000);
    return () => clearInterval(id);
  }, [refresh]);

  /* ── Loading ── */
  if (state === "loading") {
    return (
      <div className="flex min-h-screen items-center justify-center bg-gray-950">
        <div className="text-center">
          <div className="mx-auto mb-4 h-8 w-8 animate-spin rounded-full border-2 border-gray-700 border-t-blue-500" />
          <p className="text-sm text-gray-400">Connecting to proxy...</p>
        </div>
      </div>
    );
  }

  /* ── Unreachable ── */
  if (state === "unreachable") {
    return (
      <div className="flex min-h-screen items-center justify-center bg-gray-950 px-6">
        <div className="max-w-md text-center">
          <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-red-950">
            <span className="text-xl text-red-400">!</span>
          </div>
          <h2 className="mb-2 text-lg font-semibold text-white">
            Cannot reach proxy
          </h2>
          <p className="mb-6 text-sm leading-relaxed text-gray-400">
            The dashboard needs a running UncommonRoute proxy to display data.
          </p>
          <pre className="rounded-lg bg-gray-900 px-4 py-3 text-left text-xs leading-relaxed text-gray-300">
            <code>uncommon-route serve</code>
          </pre>
          <p className="mt-4 text-xs text-gray-500">
            Retrying automatically...
          </p>
        </div>
      </div>
    );
  }

  /* ── Ready ── */
  const upstream = health?.upstream
    ? health.upstream.replace(/^https?:\/\//, "").replace(/\/v1$/, "")
    : "";
  const mm = health?.model_mapper;
  const isUp = mm?.discovered ?? false;
  const noUpstream = !health?.upstream;

  return (
    <div className="min-h-screen bg-gray-950 px-6 py-5 text-gray-100">
      <div className="mx-auto max-w-7xl">
        {/* Header */}
        <div className="mb-6 flex items-center justify-between border-b border-gray-800 pb-4">
          <div className="flex items-center gap-3">
            <h1 className="text-lg font-bold tracking-tight text-white">
              UncommonRoute
            </h1>
            {health && (
              <Badge color="gray" size="xs">
                v{health.version}
              </Badge>
            )}
          </div>
          <div className="flex items-center gap-4 text-xs text-gray-400">
            <span className="flex items-center gap-1.5">
              <span
                className={`inline-block h-1.5 w-1.5 rounded-full ${isUp ? "bg-emerald-400" : noUpstream ? "bg-gray-500" : "bg-amber-400"}`}
              />
              {upstream || "no upstream"}
            </span>
            {mm && mm.discovered && (
              <span>
                {mm.provider}
                {mm.is_gateway ? " (gateway)" : ""} · {mm.upstream_models}{" "}
                models
              </span>
            )}
          </div>
        </div>

        {/* No-upstream warning */}
        {noUpstream && (
          <Callout title="No upstream configured" color="amber" className="mb-4">
            Routing is disabled — requests will return 503. Set{" "}
            <code className="rounded bg-gray-800 px-1 text-xs">
              UNCOMMON_ROUTE_UPSTREAM
            </code>{" "}
            and{" "}
            <code className="rounded bg-gray-800 px-1 text-xs">
              UNCOMMON_ROUTE_API_KEY
            </code>
            , then restart the proxy.
          </Callout>
        )}

        {/* Tabs */}
        <TabGroup>
          <TabList variant="solid" color="gray">
            <Tab>Overview</Tab>
            <Tab>Routing</Tab>
            <Tab>Models</Tab>
            <Tab>Sessions</Tab>
            <Tab>Spend</Tab>
          </TabList>
          <TabPanels>
            <TabPanel>
              <Overview stats={stats} health={health} />
            </TabPanel>
            <TabPanel>
              <Routing stats={stats} />
            </TabPanel>
            <TabPanel>
              <Models mapping={mapping} />
            </TabPanel>
            <TabPanel>
              <Sessions data={sessions} />
            </TabPanel>
            <TabPanel>
              <SpendPanel spend={spend} onRefresh={refresh} />
            </TabPanel>
          </TabPanels>
        </TabGroup>
      </div>
    </div>
  );
}
