import { useCallback, useEffect, useState } from "react";
import {
  fetchHealth,
  fetchRoutingConfig,
  fetchStats,
  fetchMapping,
  fetchSessions,
  fetchSpend,
  type Health,
  type RoutingConfigState,
  type Stats,
  type Mapping,
  type Session,
  type Spend,
} from "./api";
import Sidebar from "./components/Sidebar";
import Overview from "./components/Overview";
import Routing from "./components/Routing";
import RoutingConfig from "./components/RoutingConfig";
import Models from "./components/Models";
import Sessions from "./components/Sessions";
import SpendPanel from "./components/Spend";
import Feedback from "./components/Feedback";

type Page = "overview" | "routing" | "config" | "models" | "sessions" | "spend" | "feedback";

export default function App() {
  const [page, setPage] = useState<Page>("overview");
  const [health, setHealth] = useState<Health | null>(null);
  const [stats, setStats] = useState<Stats | null>(null);
  const [mapping, setMapping] = useState<Mapping | null>(null);
  const [sessions, setSessions] = useState<{ count: number; sessions: Session[] } | null>(null);
  const [spend, setSpend] = useState<Spend | null>(null);
  const [routingConfig, setRoutingConfig] = useState<RoutingConfigState | null>(null);
  const [ready, setReady] = useState(false);

  const refresh = useCallback(async () => {
    const [h, st, m, ss, sp, rc] = await Promise.all([
      fetchHealth(), fetchStats(), fetchMapping(), fetchSessions(), fetchSpend(), fetchRoutingConfig(),
    ]);
    if (h) { setHealth(h); setReady(true); }
    if (st) setStats(st);
    if (m) setMapping(m);
    if (ss) setSessions(ss);
    if (sp) setSpend(sp);
    if (rc) setRoutingConfig(rc);
  }, []);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, 5000);
    return () => clearInterval(id);
  }, [refresh]);

  const upstream = health?.upstream?.replace(/^https?:\/\//, "").replace(/\/v1$/, "") ?? "";
  const isUp = health?.model_mapper?.discovered ?? false;
  const version = health?.version ?? "—";
  const feedbackPending = health?.feedback?.pending ?? 0;

  if (!ready) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <div className="h-3 w-3 rounded-full bg-white/10 animate-pulse" />
      </div>
    );
  }

  return (
    <div className="min-h-screen">
      <Sidebar
        current={page}
        onChange={(p) => setPage(p as Page)}
        upstream={upstream}
        isUp={isUp}
        version={version}
        feedbackPending={feedbackPending}
      />

      <main className="ml-[220px] min-h-screen">
        <div className="max-w-4xl px-10 py-10">
          {page === "overview" && <Overview stats={stats} health={health} />}
          {page === "routing" && <Routing stats={stats} />}
          {page === "config" && <RoutingConfig data={routingConfig} onRefresh={refresh} />}
          {page === "models" && <Models mapping={mapping} />}
          {page === "sessions" && <Sessions data={sessions} />}
          {page === "spend" && <SpendPanel spend={spend} onRefresh={refresh} />}
          {page === "feedback" && <Feedback />}
        </div>
      </main>
    </div>
  );
}
