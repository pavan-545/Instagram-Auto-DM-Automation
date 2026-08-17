import React, { useState, useEffect } from "react";
import {
  Activity,
  Zap,
  MessageSquare,
  Send,
  ShieldCheck,
  Cpu,
  Plus,
  Trash2,
  RefreshCw,
  CheckCircle2,
  XCircle,
  Clock,
  AlertTriangle,
  SendHorizontal,
  Layers,
  Database,
  Play
} from "lucide-react";

const API_BASE = "http://localhost:8000";

interface Stats {
  sent: number;
  failed: number;
  queued: number;
  duplicates_blocked: number;
}

interface Rule {
  rule_id: string;
  keyword: string;
  dm_message: string;
}

interface EventItem {
  id: number;
  event_id: string;
  event_type: string;
  comment_id: string;
  user_id: string;
  username: string;
  text: string;
  received_at: string;
}

interface TaskItem {
  id: number;
  event_id: string;
  comment_id: string;
  user_id: string;
  rule_id: string;
  keyword: string;
  status: string;
  attempts: number;
  dm_id?: string;
  last_error?: string;
  created_at: string;
  updated_at: string;
}

interface HealthData {
  status: string;
  worker_running: boolean;
  rate_limit_usage: string;
  total_webhook_events: number;
  total_dm_tasks: number;
  timestamp: string;
}

export default function App() {
  const [activeTab, setActiveTab] = useState<"overview" | "rules" | "events" | "tasks" | "health" | "simulator">("overview");
  const [stats, setStats] = useState<Stats>({ sent: 0, failed: 0, queued: 0, duplicates_blocked: 0 });
  const [rules, setRules] = useState<Rule[]>([]);
  const [events, setEvents] = useState<EventItem[]>([]);
  const [tasks, setTasks] = useState<TaskItem[]>([]);
  const [health, setHealth] = useState<HealthData | null>(null);
  const [autoRefresh, setAutoRefresh] = useState<boolean>(true);
  const [toast, setToast] = useState<{ message: string; type: "success" | "error" } | null>(null);

  // New Rule Form State
  const [newKeyword, setNewKeyword] = useState("");
  const [newDmMessage, setNewDmMessage] = useState("");
  const [isSubmittingRule, setIsSubmittingRule] = useState(false);

  // Simulator Form State
  const [simUserId, setSimUserId] = useState("usr_demo_100");
  const [simUsername] = useState("creator_pro");
  const [simText, setSimText] = useState("Can I get the PRICE details please?");
  const [simEventType, setSimEventType] = useState("comment.created");
  const [simCommentId, setSimCommentId] = useState(`cmt_${Date.now()}`);
  const [simEventId, setSimEventId] = useState(`evt_${Date.now()}`);
  const [isSimulating, setIsSimulating] = useState(false);

  const showToast = (message: string, type: "success" | "error" = "success") => {
    setToast({ message, type });
    setTimeout(() => setToast(null), 3500);
  };

  const fetchAllData = async () => {
    try {
      const [resStats, resRules, resEvents, resTasks, resHealth] = await Promise.all([
        fetch(`${API_BASE}/stats`).then(r => r.json()),
        fetch(`${API_BASE}/api/rules`).then(r => r.json()),
        fetch(`${API_BASE}/api/events`).then(r => r.json()),
        fetch(`${API_BASE}/api/tasks`).then(r => r.json()),
        fetch(`${API_BASE}/api/health`).then(r => r.json())
      ]);

      setStats(resStats);
      setRules(resRules);
      setEvents(resEvents);
      setTasks(resTasks);
      setHealth(resHealth);
    } catch (err) {
      console.error("Error fetching backend data:", err);
    }
  };

  useEffect(() => {
    fetchAllData();
    if (!autoRefresh) return;
    const interval = setInterval(fetchAllData, 3000);
    return () => clearInterval(interval);
  }, [autoRefresh]);

  const handleCreateRule = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newKeyword.trim() || !newDmMessage.trim()) return;

    setIsSubmittingRule(true);
    try {
      const res = await fetch(`${API_BASE}/rules`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ keyword: newKeyword.trim(), dm_message: newDmMessage.trim() })
      });

      if (!res.ok) throw new Error("Failed to create rule");

      const created = await res.json();
      showToast(`Rule "${created.keyword}" created successfully!`);
      setNewKeyword("");
      setNewDmMessage("");
      fetchAllData();
    } catch (err: any) {
      showToast(err.message || "Failed to create rule", "error");
    } finally {
      setIsSubmittingRule(false);
    }
  };

  const handleDeleteRule = async (ruleId: string) => {
    try {
      const res = await fetch(`${API_BASE}/api/rules/${ruleId}`, { method: "DELETE" });
      if (!res.ok) throw new Error("Failed to delete rule");
      showToast(`Rule deleted`);
      fetchAllData();
    } catch (err: any) {
      showToast(err.message || "Failed to delete rule", "error");
    }
  };

  const handleRunSimulator = async () => {
    setIsSimulating(true);
    try {
      const payload = {
        event_id: simEventId.trim() || `evt_${Date.now()}`,
        event_type: simEventType,
        sent_at: new Date().toISOString(),
        data: {
          comment_id: simCommentId.trim() || `cmt_${Date.now()}`,
          text: simText,
          from: { user_id: simUserId.trim(), username: simUsername.trim() }
        }
      };

      const res = await fetch(`${API_BASE}/webhook`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });

      if (!res.ok) throw new Error(`Webhook error: ${res.statusText}`);

      const data = await res.json();
      showToast(data.message ? `ACK 200: ${data.message}` : "Webhook event ingested successfully!");
      
      // Regenerate fresh IDs for next simulator run
      setSimEventId(`evt_${Date.now()}`);
      setSimCommentId(`cmt_${Date.now()}`);
      
      setTimeout(fetchAllData, 800);
    } catch (err: any) {
      showToast(err.message || "Webhook simulation failed", "error");
    } finally {
      setIsSimulating(false);
    }
  };

  const getStatusBadge = (statusStr: string) => {
    switch (statusStr) {
      case "delivered":
        return <span className="px-2.5 py-1 text-xs font-semibold rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 flex items-center gap-1 w-fit"><CheckCircle2 className="w-3 h-3" /> Delivered</span>;
      case "queued":
      case "sending":
      case "sent_awaiting_reconciliation":
        return <span className="px-2.5 py-1 text-xs font-semibold rounded-full bg-amber-500/10 text-amber-400 border border-amber-500/20 flex items-center gap-1 w-fit"><Clock className="w-3 h-3 animate-spin" /> {statusStr === "sent_awaiting_reconciliation" ? "Awaiting 202 Reconciliation" : statusStr}</span>;
      case "failed":
        return <span className="px-2.5 py-1 text-xs font-semibold rounded-full bg-rose-500/10 text-rose-400 border border-rose-500/20 flex items-center gap-1 w-fit"><XCircle className="w-3 h-3" /> Failed</span>;
      case "blocked_duplicate":
        return <span className="px-2.5 py-1 text-xs font-semibold rounded-full bg-purple-500/10 text-purple-400 border border-purple-500/20 flex items-center gap-1 w-fit"><ShieldCheck className="w-3 h-3" /> Blocked Duplicate</span>;
      case "cancelled":
        return <span className="px-2.5 py-1 text-xs font-semibold rounded-full bg-slate-500/10 text-slate-400 border border-slate-500/20 flex items-center gap-1 w-fit"><AlertTriangle className="w-3 h-3" /> Deleted Comment</span>;
      default:
        return <span className="px-2.5 py-1 text-xs font-semibold rounded-full bg-slate-800 text-slate-300">{statusStr}</span>;
    }
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col font-sans">
      {/* Toast Notification */}
      {toast && (
        <div className={`fixed bottom-6 right-6 z-50 px-4 py-3 rounded-lg shadow-xl border flex items-center gap-3 transition-all transform translate-y-0 ${
          toast.type === "success" 
            ? "bg-slate-900 border-emerald-500/30 text-emerald-300" 
            : "bg-slate-900 border-rose-500/30 text-rose-300"
        }`}>
          {toast.type === "success" ? <CheckCircle2 className="w-5 h-5 text-emerald-400" /> : <AlertTriangle className="w-5 h-5 text-rose-400" />}
          <span className="text-sm font-medium">{toast.message}</span>
        </div>
      )}

      {/* Top Header */}
      <header className="border-b border-slate-800/80 bg-slate-900/60 backdrop-blur-md sticky top-0 z-40">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-indigo-600 via-purple-600 to-pink-500 flex items-center justify-center shadow-lg shadow-indigo-500/20">
              <Zap className="w-5 h-5 text-white" />
            </div>
            <div>
              <h1 className="text-lg font-bold bg-gradient-to-r from-white via-slate-200 to-slate-400 bg-clip-text text-transparent">
                LinkPlease
              </h1>
              <p className="text-xs text-slate-400 font-mono">PseudoGram DM Automation Engine</p>
            </div>
          </div>

          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2 bg-slate-900 border border-slate-800 rounded-full px-3 py-1.5 text-xs">
              <span className={`w-2 h-2 rounded-full ${health?.worker_running ? "bg-emerald-400 animate-pulse" : "bg-rose-500"}`} />
              <span className="text-slate-300 font-medium">{health?.worker_running ? "Worker Active" : "Worker Offline"}</span>
            </div>

            <button
              onClick={() => setAutoRefresh(!autoRefresh)}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium border transition-all flex items-center gap-1.5 ${
                autoRefresh 
                  ? "bg-indigo-500/10 border-indigo-500/30 text-indigo-400" 
                  : "bg-slate-900 border-slate-800 text-slate-400 hover:text-slate-200"
              }`}
            >
              <RefreshCw className={`w-3.5 h-3.5 ${autoRefresh ? "animate-spin" : ""}`} />
              {autoRefresh ? "Live Sync (3s)" : "Paused"}
            </button>

            <button
              onClick={fetchAllData}
              className="p-2 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg text-xs transition"
              title="Manual Refresh"
            >
              <RefreshCw className="w-4 h-4" />
            </button>
          </div>
        </div>
      </header>

      {/* Main Navigation Tabs */}
      <div className="border-b border-slate-800 bg-slate-900/40">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex space-x-1 overflow-x-auto">
          {[
            { id: "overview", label: "Overview", icon: Activity },
            { id: "rules", label: "Automation Rules", icon: Zap, count: rules.length },
            { id: "events", label: "Comment Events", icon: MessageSquare, count: events.length },
            { id: "tasks", label: "DM Queue & Deliveries", icon: SendHorizontal, count: tasks.length },
            { id: "health", label: "System & Rate Limits", icon: Cpu },
            { id: "simulator", label: "Test Console", icon: Play }
          ].map(tab => {
            const Icon = tab.icon;
            const isActive = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id as any)}
                className={`py-3.5 px-4 font-medium text-sm border-b-2 flex items-center gap-2 whitespace-nowrap transition-all ${
                  isActive
                    ? "border-indigo-500 text-indigo-400 bg-indigo-500/5"
                    : "border-transparent text-slate-400 hover:text-slate-200 hover:border-slate-700"
                }`}
              >
                <Icon className={`w-4 h-4 ${isActive ? "text-indigo-400" : "text-slate-400"}`} />
                {tab.label}
                {tab.count !== undefined && (
                  <span className={`px-2 py-0.5 text-xs rounded-full font-semibold ${
                    isActive ? "bg-indigo-500/20 text-indigo-300" : "bg-slate-800 text-slate-400"
                  }`}>
                    {tab.count}
                  </span>
                )}
              </button>
            );
          })}
        </div>
      </div>

      {/* Tab Contents */}
      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* OVERVIEW TAB */}
        {activeTab === "overview" && (
          <div className="space-y-8">
            {/* Live Stats Row */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-5">
              <div className="glass-card glass-card-hover p-6 rounded-2xl relative overflow-hidden border border-slate-800">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium text-slate-400">Delivered DMs</span>
                  <div className="w-10 h-10 rounded-xl bg-emerald-500/10 text-emerald-400 flex items-center justify-center">
                    <CheckCircle2 className="w-5 h-5" />
                  </div>
                </div>
                <div className="mt-4">
                  <div className="text-3xl font-extrabold text-white tracking-tight">{stats.sent}</div>
                  <p className="text-xs text-slate-400 mt-1">Confirmed delivered by PseudoGram</p>
                </div>
              </div>

              <div className="glass-card glass-card-hover p-6 rounded-2xl relative overflow-hidden border border-slate-800">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium text-slate-400">Pending / Queued</span>
                  <div className="w-10 h-10 rounded-xl bg-amber-500/10 text-amber-400 flex items-center justify-center">
                    <Clock className="w-5 h-5" />
                  </div>
                </div>
                <div className="mt-4">
                  <div className="text-3xl font-extrabold text-white tracking-tight">{stats.queued}</div>
                  <p className="text-xs text-slate-400 mt-1">Queued or awaiting 202 reconciliation</p>
                </div>
              </div>

              <div className="glass-card glass-card-hover p-6 rounded-2xl relative overflow-hidden border border-slate-800">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium text-slate-400">Duplicates Blocked</span>
                  <div className="w-10 h-10 rounded-xl bg-purple-500/10 text-purple-400 flex items-center justify-center">
                    <ShieldCheck className="w-5 h-5" />
                  </div>
                </div>
                <div className="mt-4">
                  <div className="text-3xl font-extrabold text-white tracking-tight">{stats.duplicates_blocked}</div>
                  <p className="text-xs text-slate-400 mt-1">Single DM per user/rule enforced</p>
                </div>
              </div>

              <div className="glass-card glass-card-hover p-6 rounded-2xl relative overflow-hidden border border-slate-800">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium text-slate-400">Failed DMs</span>
                  <div className="w-10 h-10 rounded-xl bg-rose-500/10 text-rose-400 flex items-center justify-center">
                    <XCircle className="w-5 h-5" />
                  </div>
                </div>
                <div className="mt-4">
                  <div className="text-3xl font-extrabold text-white tracking-tight">{stats.failed}</div>
                  <p className="text-xs text-slate-400 mt-1">Failed after retries or 400 error</p>
                </div>
              </div>
            </div>

            {/* Quick Activity Summary & Health */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
              <div className="lg:col-span-2 glass-card rounded-2xl p-6 border border-slate-800">
                <div className="flex items-center justify-between mb-6">
                  <h3 className="text-base font-semibold text-white flex items-center gap-2">
                    <Layers className="w-4 h-4 text-indigo-400" /> Recent DM Delivery Tasks
                  </h3>
                  <button onClick={() => setActiveTab("tasks")} className="text-xs text-indigo-400 hover:text-indigo-300 font-medium">
                    View All →
                  </button>
                </div>

                {tasks.length === 0 ? (
                  <div className="py-12 text-center text-slate-500 text-sm">
                    No DM tasks generated yet. Try triggering a webhook event!
                  </div>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full text-left text-xs">
                      <thead>
                        <tr className="border-b border-slate-800 text-slate-400 uppercase tracking-wider font-semibold">
                          <th className="pb-3">Recipient ID</th>
                          <th className="pb-3">Keyword</th>
                          <th className="pb-3">Status</th>
                          <th className="pb-3">Attempts</th>
                          <th className="pb-3">Updated</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-800/60 font-mono">
                        {tasks.slice(0, 5).map(task => (
                          <tr key={task.id} className="hover:bg-slate-900/40">
                            <td className="py-3 text-slate-200 font-medium">{task.user_id}</td>
                            <td className="py-3 text-indigo-300 font-semibold">{task.keyword}</td>
                            <td className="py-3">{getStatusBadge(task.status)}</td>
                            <td className="py-3 text-slate-400">{task.attempts}</td>
                            <td className="py-3 text-slate-400">{task.updated_at ? new Date(task.updated_at).toLocaleTimeString() : "-"}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>

              {/* System Rate Limit Meter */}
              <div className="glass-card rounded-2xl p-6 border border-slate-800 flex flex-col justify-between">
                <div>
                  <h3 className="text-base font-semibold text-white mb-2 flex items-center gap-2">
                    <Cpu className="w-4 h-4 text-indigo-400" /> PseudoGram Rate Limiter
                  </h3>
                  <p className="text-xs text-slate-400 mb-6">
                    Strict rolling 60-second window rate limit (Max 10 requests / 60s).
                  </p>

                  <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 mb-4">
                    <div className="flex justify-between items-center text-xs font-semibold mb-2">
                      <span className="text-slate-400">Current 60s Window Usage</span>
                      <span className="text-indigo-400">{health?.rate_limit_usage || "0/10 req/60s"}</span>
                    </div>
                    <div className="w-full bg-slate-800 h-2.5 rounded-full overflow-hidden">
                      <div 
                        className="bg-gradient-to-r from-indigo-500 to-purple-500 h-full rounded-full transition-all duration-500" 
                        style={{ width: `${Math.min(100, (parseInt(health?.rate_limit_usage?.split("/")[0] || "0") / 10) * 100)}%` }}
                      />
                    </div>
                  </div>
                </div>

                <div className="space-y-3 pt-4 border-t border-slate-800 text-xs text-slate-400">
                  <div className="flex justify-between">
                    <span>Persistent Background Worker:</span>
                    <span className="text-emerald-400 font-medium">Running</span>
                  </div>
                  <div className="flex justify-between">
                    <span>Idempotency Protection:</span>
                    <span className="text-indigo-400 font-medium">PostgreSQL Unique Constraint</span>
                  </div>
                  <div className="flex justify-between">
                    <span>500 Retry Strategy:</span>
                    <span className="text-slate-300 font-medium">Exponential Backoff</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* AUTOMATION RULES TAB */}
        {activeTab === "rules" && (
          <div className="space-y-8">
            {/* Create Rule Form */}
            <div className="glass-card rounded-2xl p-6 border border-slate-800">
              <h3 className="text-base font-semibold text-white mb-4 flex items-center gap-2">
                <Plus className="w-4 h-4 text-indigo-400" /> Create New Automation Rule
              </h3>
              <form onSubmit={handleCreateRule} className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div>
                  <label className="block text-xs font-semibold text-slate-300 uppercase tracking-wider mb-2">
                    Keyword (Case-Insensitive)
                  </label>
                  <input
                    type="text"
                    value={newKeyword}
                    onChange={e => setNewKeyword(e.target.value)}
                    placeholder="e.g. PRICE, LINK, DISCOUNT"
                    className="w-full bg-slate-900 border border-slate-800 rounded-xl px-4 py-2.5 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-indigo-500"
                    required
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-slate-300 uppercase tracking-wider mb-2">
                    Auto-DM Message
                  </label>
                  <input
                    type="text"
                    value={newDmMessage}
                    onChange={e => setNewDmMessage(e.target.value)}
                    placeholder="e.g. Thanks! Here is your link: https://example.com"
                    className="w-full bg-slate-900 border border-slate-800 rounded-xl px-4 py-2.5 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-indigo-500"
                    required
                  />
                </div>
                <div className="flex items-end">
                  <button
                    type="submit"
                    disabled={isSubmittingRule}
                    className="w-full bg-indigo-600 hover:bg-indigo-500 text-white font-medium px-5 py-2.5 rounded-xl text-sm transition shadow-lg shadow-indigo-600/25 disabled:opacity-50 flex items-center justify-center gap-2"
                  >
                    {isSubmittingRule ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />}
                    Add Automation Rule
                  </button>
                </div>
              </form>
            </div>

            {/* Active Rules List */}
            <div className="glass-card rounded-2xl p-6 border border-slate-800">
              <h3 className="text-base font-semibold text-white mb-6 flex items-center gap-2">
                <Zap className="w-4 h-4 text-indigo-400" /> Active Automation Rules ({rules.length})
              </h3>

              {rules.length === 0 ? (
                <div className="py-12 text-center text-slate-500 text-sm">
                  No automation rules configured yet. Add your first rule above!
                </div>
              ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                  {rules.map(rule => (
                    <div key={rule.rule_id} className="bg-slate-900 border border-slate-800 rounded-xl p-5 relative group hover:border-indigo-500/40 transition">
                      <div className="flex items-center justify-between mb-3">
                        <span className="px-3 py-1 bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 rounded-full font-mono text-xs font-bold">
                          "{rule.keyword}"
                        </span>
                        <button
                          onClick={() => handleDeleteRule(rule.rule_id)}
                          className="text-slate-500 hover:text-rose-400 p-1.5 rounded-lg transition"
                          title="Delete Rule"
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </div>
                      <p className="text-xs text-slate-300 bg-slate-950/60 p-3 rounded-lg border border-slate-800/80 font-mono">
                        {rule.dm_message}
                      </p>
                      <div className="mt-3 text-[10px] text-slate-500 font-mono">
                        Rule ID: {rule.rule_id}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}

        {/* WEBHOOK EVENTS TAB */}
        {activeTab === "events" && (
          <div className="glass-card rounded-2xl p-6 border border-slate-800">
            <div className="flex items-center justify-between mb-6">
              <div>
                <h3 className="text-base font-semibold text-white flex items-center gap-2">
                  <MessageSquare className="w-4 h-4 text-indigo-400" /> Webhook Events Feed
                </h3>
                <p className="text-xs text-slate-400">Ingested Instagram comment webhooks with HMAC-SHA256 signature validation.</p>
              </div>
              <button onClick={fetchAllData} className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs rounded-lg flex items-center gap-1.5 transition">
                <RefreshCw className="w-3.5 h-3.5" /> Refresh Feed
              </button>
            </div>

            {events.length === 0 ? (
              <div className="py-12 text-center text-slate-500 text-sm">
                No webhook events received yet. Use the Test Console to trigger sample events!
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs font-mono">
                  <thead>
                    <tr className="border-b border-slate-800 text-slate-400 uppercase tracking-wider font-semibold">
                      <th className="pb-3">Event ID</th>
                      <th className="pb-3">Event Type</th>
                      <th className="pb-3">Comment ID</th>
                      <th className="pb-3">User ID</th>
                      <th className="pb-3">Comment Text</th>
                      <th className="pb-3">Received At</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/60">
                    {events.map(evt => (
                      <tr key={evt.id} className="hover:bg-slate-900/40">
                        <td className="py-3 text-indigo-300 font-medium">{evt.event_id}</td>
                        <td className="py-3">
                          <span className={`px-2 py-0.5 rounded text-[10px] font-semibold ${
                            evt.event_type === "comment.deleted" ? "bg-rose-500/10 text-rose-400 border border-rose-500/20" : "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
                          }`}>
                            {evt.event_type}
                          </span>
                        </td>
                        <td className="py-3 text-slate-300">{evt.comment_id}</td>
                        <td className="py-3 text-slate-300">{evt.user_id || "-"}</td>
                        <td className="py-3 text-slate-100 max-w-xs truncate">{evt.text || "-"}</td>
                        <td className="py-3 text-slate-400">{evt.received_at ? new Date(evt.received_at).toLocaleTimeString() : "-"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}

        {/* DM QUEUE & DELIVERIES TAB */}
        {activeTab === "tasks" && (
          <div className="glass-card rounded-2xl p-6 border border-slate-800">
            <div className="flex items-center justify-between mb-6">
              <div>
                <h3 className="text-base font-semibold text-white flex items-center gap-2">
                  <SendHorizontal className="w-4 h-4 text-indigo-400" /> Persistent DM Task Queue
                </h3>
                <p className="text-xs text-slate-400">Queue surviving process restarts, with 202 status reconciliation and rate-limit backoff.</p>
              </div>
              <button onClick={fetchAllData} className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs rounded-lg flex items-center gap-1.5 transition">
                <RefreshCw className="w-3.5 h-3.5" /> Refresh Queue
              </button>
            </div>

            {tasks.length === 0 ? (
              <div className="py-12 text-center text-slate-500 text-sm">
                No DM tasks queued or executed yet.
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs font-mono">
                  <thead>
                    <tr className="border-b border-slate-800 text-slate-400 uppercase tracking-wider font-semibold">
                      <th className="pb-3">Task ID</th>
                      <th className="pb-3">Recipient User ID</th>
                      <th className="pb-3">Rule Keyword</th>
                      <th className="pb-3">Status</th>
                      <th className="pb-3">Attempts</th>
                      <th className="pb-3">PseudoGram DM ID</th>
                      <th className="pb-3">Last Error / Note</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/60 font-mono">
                    {tasks.map(t => (
                      <tr key={t.id} className="hover:bg-slate-900/40">
                        <td className="py-3 text-slate-400">#{t.id}</td>
                        <td className="py-3 text-slate-200 font-medium">{t.user_id}</td>
                        <td className="py-3 text-indigo-300 font-semibold">{t.keyword}</td>
                        <td className="py-3">{getStatusBadge(t.status)}</td>
                        <td className="py-3 text-slate-300">{t.attempts}</td>
                        <td className="py-3 text-slate-400">{t.dm_id || "-"}</td>
                        <td className="py-3 text-slate-400 max-w-xs truncate">{t.last_error || "-"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}

        {/* SYSTEM HEALTH TAB */}
        {activeTab === "health" && (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
            <div className="glass-card rounded-2xl p-6 border border-slate-800 space-y-6">
              <h3 className="text-base font-semibold text-white flex items-center gap-2">
                <ShieldCheck className="w-4 h-4 text-emerald-400" /> Operational & Reliability Controls
              </h3>

              <div className="space-y-4">
                <div className="bg-slate-900 p-4 rounded-xl border border-slate-800">
                  <div className="text-xs font-semibold text-slate-300 mb-1">Idempotency & Concurrency</div>
                  <p className="text-xs text-slate-400">
                    PostgreSQL unique constraints enforce single DM delivery per <span className="text-indigo-400 font-mono">(rule_id, user_id)</span> regardless of comment frequency or concurrent worker instances.
                  </p>
                </div>

                <div className="bg-slate-900 p-4 rounded-xl border border-slate-800">
                  <div className="text-xs font-semibold text-slate-300 mb-1">Sliding-Window Rate Limiting</div>
                  <p className="text-xs text-slate-400">
                    Database-backed token bucket limits <span className="text-indigo-400 font-mono">POST /v1/dm/send</span> to maximum 10 requests per rolling 60 seconds.
                  </p>
                </div>

                <div className="bg-slate-900 p-4 rounded-xl border border-slate-800">
                  <div className="text-xs font-semibold text-slate-300 mb-1">202 Status Reconciliation</div>
                  <p className="text-xs text-slate-400">
                    Asynchronous polling loop checks <span className="text-indigo-400 font-mono">GET /v1/dm/{`{dm_id}`}</span> without burning rate limit capacity until delivery is confirmed.
                  </p>
                </div>

                <div className="bg-slate-900 p-4 rounded-xl border border-slate-800">
                  <div className="text-xs font-semibold text-slate-300 mb-1">Comment Deletion Handling</div>
                  <p className="text-xs text-slate-400">
                    <span className="text-indigo-400 font-mono">comment.deleted</span> events instantly cancel matching queued or sending DM tasks before dispatch.
                  </p>
                </div>
              </div>
            </div>

            <div className="glass-card rounded-2xl p-6 border border-slate-800 space-y-6">
              <h3 className="text-base font-semibold text-white flex items-center gap-2">
                <Database className="w-4 h-4 text-indigo-400" /> Database & Queue Health
              </h3>

              <div className="bg-slate-900 p-5 rounded-xl border border-slate-800 space-y-3 font-mono text-xs">
                <div className="flex justify-between py-2 border-b border-slate-800">
                  <span className="text-slate-400">Total Ingested Webhooks:</span>
                  <span className="text-white font-bold">{health?.total_webhook_events || 0}</span>
                </div>
                <div className="flex justify-between py-2 border-b border-slate-800">
                  <span className="text-slate-400">Total DM Tasks Created:</span>
                  <span className="text-white font-bold">{health?.total_dm_tasks || 0}</span>
                </div>
                <div className="flex justify-between py-2 border-b border-slate-800">
                  <span className="text-slate-400">Rate Limit Status:</span>
                  <span className="text-indigo-400 font-bold">{health?.rate_limit_usage}</span>
                </div>
                <div className="flex justify-between py-2">
                  <span className="text-slate-400">Backend Status:</span>
                  <span className="text-emerald-400 font-bold">{health?.status?.toUpperCase()}</span>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* SIMULATOR / TEST CONSOLE TAB */}
        {activeTab === "simulator" && (
          <div className="glass-card rounded-2xl p-6 border border-slate-800 max-w-3xl mx-auto space-y-6">
            <div>
              <h3 className="text-base font-semibold text-white flex items-center gap-2 mb-1">
                <Play className="w-4 h-4 text-indigo-400" /> Interactive Webhook Simulator
              </h3>
              <p className="text-xs text-slate-400">
                Trigger synthetic Instagram webhooks to test async ingestion, rule matching, duplicate suppression, and 202 reconciliation live!
              </p>
            </div>

            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-semibold text-slate-300 uppercase tracking-wider mb-2">
                    Event Type
                  </label>
                  <select
                    value={simEventType}
                    onChange={e => setSimEventType(e.target.value)}
                    className="w-full bg-slate-900 border border-slate-800 rounded-xl px-4 py-2.5 text-sm text-slate-100 focus:outline-none focus:border-indigo-500"
                  >
                    <option value="comment.created">comment.created</option>
                    <option value="comment.deleted">comment.deleted</option>
                  </select>
                </div>
                <div>
                  <label className="block text-xs font-semibold text-slate-300 uppercase tracking-wider mb-2">
                    User ID (Identity)
                  </label>
                  <input
                    type="text"
                    value={simUserId}
                    onChange={e => setSimUserId(e.target.value)}
                    className="w-full bg-slate-900 border border-slate-800 rounded-xl px-4 py-2.5 text-sm text-slate-100 font-mono focus:outline-none focus:border-indigo-500"
                  />
                </div>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-300 uppercase tracking-wider mb-2">
                  Comment Text
                </label>
                <input
                  type="text"
                  value={simText}
                  onChange={e => setSimText(e.target.value)}
                  className="w-full bg-slate-900 border border-slate-800 rounded-xl px-4 py-2.5 text-sm text-slate-100 focus:outline-none focus:border-indigo-500"
                />
              </div>

              <div className="grid grid-cols-2 gap-4 text-xs font-mono">
                <div>
                  <label className="block font-semibold text-slate-400 uppercase tracking-wider mb-1">
                    Event ID
                  </label>
                  <input
                    type="text"
                    value={simEventId}
                    onChange={e => setSimEventId(e.target.value)}
                    className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-slate-300"
                  />
                </div>
                <div>
                  <label className="block font-semibold text-slate-400 uppercase tracking-wider mb-1">
                    Comment ID
                  </label>
                  <input
                    type="text"
                    value={simCommentId}
                    onChange={e => setSimCommentId(e.target.value)}
                    className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-slate-300"
                  />
                </div>
              </div>

              <div className="pt-4 flex gap-3">
                <button
                  onClick={handleRunSimulator}
                  disabled={isSimulating}
                  className="flex-1 bg-gradient-to-r from-indigo-600 to-purple-600 hover:from-indigo-500 hover:to-purple-500 text-white font-medium px-5 py-3 rounded-xl text-sm transition shadow-lg shadow-indigo-600/25 flex items-center justify-center gap-2 disabled:opacity-50"
                >
                  {isSimulating ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
                  Post Webhook to /webhook
                </button>
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
