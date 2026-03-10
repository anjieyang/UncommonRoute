interface Props {
  current: string;
  onChange: (page: string) => void;
  upstream: string;
  isUp: boolean;
  version: string;
  feedbackPending: number;
}

const NAV = [
  { id: "overview", label: "Overview" },
  { id: "routing", label: "Routing" },
  { id: "config", label: "Config" },
  { id: "models", label: "Models" },
  { id: "sessions", label: "Sessions" },
  { id: "spend", label: "Spend" },
  { id: "feedback", label: "Feedback" },
];

export default function Sidebar({ current, onChange, upstream, isUp, version, feedbackPending }: Props) {
  return (
    <aside className="fixed top-0 left-0 h-full w-[220px] border-r border-white/[0.07] bg-[#111113] flex flex-col z-50">
      {/* Logo */}
      <div className="px-5 h-14 flex items-center border-b border-white/[0.07]">
        <span className="text-[15px] font-semibold text-white/90 tracking-tight">UncommonRoute</span>
      </div>

      {/* Nav */}
      <nav className="flex-1 py-4 px-3">
        {NAV.map((item) => (
          <button
            key={item.id}
            onClick={() => onChange(item.id)}
            className={`w-full text-left px-3 py-2 rounded-lg text-[14px] transition-colors flex items-center justify-between mb-0.5 ${
              current === item.id
                ? "text-white bg-white/[0.08] font-medium"
                : "text-[#8b8b8e] hover:text-white/80 hover:bg-white/[0.04]"
            }`}
          >
            {item.label}
            {item.id === "feedback" && feedbackPending > 0 && (
              <span className="text-[11px] font-mono font-semibold bg-blue-500/80 text-white rounded-full h-5 min-w-5 flex items-center justify-center px-1.5">
                {feedbackPending}
              </span>
            )}
          </button>
        ))}
      </nav>

      {/* Footer */}
      <div className="px-5 py-4 border-t border-white/[0.07]">
        <div className="flex items-center gap-2 text-[12px] text-[#5a5a5d]">
          <div className={`h-[7px] w-[7px] rounded-full flex-shrink-0 ${isUp ? "bg-emerald-400/80" : "bg-[#5a5a5d]"}`} />
          <span className="truncate">{upstream || "No upstream"}</span>
        </div>
        <div className="text-[11px] font-mono text-[#3a3a3d] mt-1.5">v{version}</div>
      </div>
    </aside>
  );
}
