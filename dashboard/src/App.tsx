import { useState, useEffect, useRef } from 'react';
import { 
  Activity, 
  ShieldAlert, 
  TrendingUp, 
  AlertTriangle, 
  Power, 
  BarChart2, 
  CheckCircle2, 
  XCircle 
} from 'lucide-react';

const API_BASE = "http://localhost:8000/api/v1";
const WS_URL = "ws://localhost:8000/ws/candidate-trades";

export default function App() {
  const [systemState, setSystemState] = useState('LIVE');
  const [wsConnected, setWsConnected] = useState(false);
  const [watchlist, setWatchlist] = useState<any[]>([]);
  const [positions, setPositions] = useState<any[]>([]);
  const [margin, setMargin] = useState(0);
  const [pnl, setPnl] = useState(0);
  const [candidates, setCandidates] = useState<any[]>([]);
  const [securityEvents, setSecurityEvents] = useState(0);
  const [auditLogs, setAuditLogs] = useState<any[]>([]);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [feedbackMsg, setFeedbackMsg] = useState<{ text: string; type: 'success' | 'danger' } | null>(null);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    fetchSystemStatus();
    fetchAuditLogs();
    connectWebSocket();

    const auditTimer = setInterval(fetchAuditLogs, 4000);
    return () => {
      clearInterval(auditTimer);
      if (wsRef.current) wsRef.current.close();
    };
  }, []);

  const showToast = (text: string, type: 'success' | 'danger' = 'success') => {
    setFeedbackMsg({ text, type });
    setTimeout(() => setFeedbackMsg(null), 4000);
  };

  const fetchSystemStatus = async () => {
    try {
      const res = await fetch(`${API_BASE}/system/status`);
      const data = await res.json();
      setSystemState(data.emergency_stop_active ? 'HALTED' : 'LIVE');
    } catch (e) {
      console.error("Failed to fetch system status", e);
    }
  };

  const fetchAuditLogs = async () => {
    try {
      const res = await fetch(`${API_BASE}/audit-logs`);
      const data = await res.json();
      if (data && Array.isArray(data.logs)) {
        setAuditLogs(data.logs.slice(0, 15));
        const secCount = data.logs.filter((l: any) => l.event_type === 'SECURITY' || l.action === 'REJECT').length;
        setSecurityEvents(secCount);
      }
    } catch (e) {
      console.error("Failed to fetch audit logs", e);
    }
  };

  const connectWebSocket = () => {
    const ws = new WebSocket(WS_URL);
    wsRef.current = ws;

    ws.onopen = () => setWsConnected(true);
    ws.onclose = () => {
      setWsConnected(false);
      setTimeout(connectWebSocket, 2000);
    };
    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === 'market_update') {
          setWatchlist(data.watchlist || []);
          setPositions(data.positions || []);
          setMargin(data.account_stats?.margin || 0);
          
          const holdingsPnl = (data.holdings || []).reduce((acc: number, h: any) => acc + (h.pnl || 0), 0);
          const posPnl = (data.positions || []).reduce((acc: number, p: any) => acc + (p.pnl || 0), 0);
          setPnl(holdingsPnl + posPnl);
        } else if (data.type === 'candidate_trade') {
          setCandidates(prev => {
            if (prev.find(c => c.id === data.candidate.id)) return prev;
            return [...prev, data.candidate];
          });
        }
      } catch (e) {
        console.error("WS Parse error", e);
      }
    };
  };

  const handleEmergencyStop = async () => {
    try {
      await fetch(`${API_BASE}/system/emergency-stop`, { method: 'POST' });
      await fetchSystemStatus();
      showToast("Emergency Stop triggered! Algorithmic trading halted.", "danger");
      fetchAuditLogs();
    } catch (e) {
      console.error("Emergency stop failed", e);
      showToast("Emergency stop request failed", "danger");
    }
  };

  const handleTradeAction = async (tradeId: string, action: string) => {
    setCandidates(prev => prev.filter(c => c.id !== tradeId));
    try {
      const res = await fetch(`${API_BASE}/trades/action`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ trade_id: tradeId, action })
      });
      if (res.ok) {
        showToast(`Trade ${action === 'APPROVE' ? 'Approved & Submitted' : 'Rejected'}`);
      } else {
        const err = await res.json();
        showToast(err.detail || "Trade action rejected", "danger");
      }
      fetchAuditLogs();
    } catch (e) {
      console.error("Trade action failed", e);
      showToast("Trade action request failed", "danger");
    }
  };

  const handleSquareOff = async (symbol: string, quantity: number) => {
    setActionLoading(symbol);
    try {
      const res = await fetch(`${API_BASE}/trades/close`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ symbol, quantity })
      });
      if (res.ok) {
        showToast(`Square-off order placed for ${symbol}`);
        setPositions(prev => prev.filter(p => p.symbol !== symbol));
        fetchAuditLogs();
      } else {
        const err = await res.json();
        showToast(err.detail || `Failed to square off ${symbol}`, "danger");
      }
    } catch (e) {
      console.error("Square off failed", e);
      showToast(`Square off request failed for ${symbol}`, "danger");
    } finally {
      setActionLoading(null);
    }
  };

  const handleSquareOffAll = async () => {
    if (!window.confirm("Are you sure you want to square off all open positions immediately?")) {
      return;
    }
    setActionLoading('ALL');
    try {
      const res = await fetch(`${API_BASE}/trades/close-all`, { method: 'POST' });
      if (res.ok) {
        showToast("All open positions squared off successfully");
        setPositions([]);
        fetchAuditLogs();
      } else {
        const err = await res.json();
        showToast(err.detail || "Failed to square off all positions", "danger");
      }
    } catch (e) {
      console.error("Square off all failed", e);
      showToast("Request failed", "danger");
    } finally {
      setActionLoading(null);
    }
  };

  return (
    <div className="app-container">
      {/* Toast Notification Banner */}
      {feedbackMsg && (
        <div style={{
          position: 'fixed',
          top: '20px',
          right: '24px',
          zIndex: 9999,
          background: feedbackMsg.type === 'danger' ? 'rgba(239, 68, 68, 0.95)' : 'rgba(16, 185, 129, 0.95)',
          color: '#fff',
          padding: '12px 20px',
          borderRadius: '8px',
          boxShadow: '0 8px 24px rgba(0,0,0,0.3)',
          display: 'flex',
          alignItems: 'center',
          gap: '10px',
          fontWeight: 500,
          fontSize: '14px',
          backdropFilter: 'blur(8px)'
        }}>
          {feedbackMsg.type === 'danger' ? <AlertTriangle size={18} /> : <CheckCircle2 size={18} />}
          {feedbackMsg.text}
        </div>
      )}

      {/* Sidebar */}
      <aside className="sidebar glass-panel" style={{ borderRadius: 0, borderTop: 0, borderBottom: 0, borderLeft: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '16px' }}>
          <Activity color="var(--accent-primary)" size={28} />
          <h1 style={{ margin: 0 }}>OmniTrade</h1>
        </div>
        
        <div>
          <h3>System Health</h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '16px', marginTop: '16px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{ color: 'var(--text-secondary)' }}>Trading Engine</span>
              <span className={`status-badge ${systemState === 'LIVE' ? 'status-live' : 'status-halted'}`}>
                <div className={`pulse-dot ${systemState === 'HALTED' ? 'danger' : ''}`}></div>
                {systemState}
              </span>
            </div>
            
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{ color: 'var(--text-secondary)' }}>Broker WebSocket</span>
              <span className={`status-badge ${wsConnected ? 'status-live' : 'status-warning'}`}>
                <div className="pulse-dot"></div> {wsConnected ? 'CONNECTED' : 'DISCONNECTED'}
              </span>
            </div>
            
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{ color: 'var(--text-secondary)' }}>Exit Monitor</span>
              <span className="status-badge status-live">
                <div className="pulse-dot"></div> ACTIVE (SL/TP)
              </span>
            </div>
          </div>
        </div>

        <div style={{ marginTop: 'auto' }}>
          <button 
            className="btn btn-danger" 
            style={{ width: '100%', padding: '16px' }}
            onClick={handleEmergencyStop}
            disabled={systemState === 'HALTED'}
          >
            <Power size={18} />
            EMERGENCY STOP
          </button>
        </div>
      </aside>

      {/* Main Content */}
      <main className="main-content">
        <header className="header-bar animate-enter">
          <div>
            <h1 style={{ fontSize: '28px', color: '#fff' }}>Operator Dashboard</h1>
            <p style={{ color: 'var(--text-secondary)', marginTop: '4px' }}>Autonomous trade lifecycle & exit management</p>
          </div>
          <div style={{ display: 'flex', gap: '24px', alignItems: 'center' }}>
            <div style={{ textAlign: 'right' }}>
              <div style={{ fontSize: '12px', color: 'var(--text-secondary)', textTransform: 'uppercase' }}>Available Margin</div>
              <div style={{ fontSize: '24px', fontWeight: 'bold', color: '#fff', fontFamily: 'JetBrains Mono' }}>
                ₹{margin.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
              </div>
            </div>
          </div>
        </header>

        <div className="dashboard-grid">
          
          {/* Key Metrics */}
          <div className="col-span-12 dashboard-grid animate-enter delay-1">
            <div className="col-span-3 glass-panel card">
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: 'var(--text-secondary)' }}>
                <TrendingUp size={16} /> <span style={{ fontSize: '13px', fontWeight: 600, textTransform: 'uppercase' }}>Portfolio P&L</span>
              </div>
              <div className={`metric-value ${pnl >= 0 ? 'text-success' : 'text-danger'}`} style={{ background: 'none', WebkitTextFillColor: 'initial' }}>
                {pnl >= 0 ? '+' : ''}₹{pnl.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
              </div>
            </div>
            
            <div className="col-span-3 glass-panel card">
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: 'var(--text-secondary)' }}>
                <Activity size={16} /> <span style={{ fontSize: '13px', fontWeight: 600, textTransform: 'uppercase' }}>Active Positions</span>
              </div>
              <div className="metric-value">{positions.length}</div>
            </div>

            <div className="col-span-3 glass-panel card">
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: 'var(--text-secondary)' }}>
                <BarChart2 size={16} /> <span style={{ fontSize: '13px', fontWeight: 600, textTransform: 'uppercase' }}>Anomaly Score</span>
              </div>
              <div className="metric-value">-0.24</div>
              <div style={{ fontSize: '12px', color: 'var(--success)' }}>Normal bounds (Threshold: -0.50)</div>
            </div>

            <div className="col-span-3 glass-panel card" style={{ borderLeft: '4px solid var(--warning)' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: 'var(--text-secondary)' }}>
                <ShieldAlert size={16} color="var(--warning)" /> <span style={{ fontSize: '13px', fontWeight: 600, textTransform: 'uppercase' }}>Security Events</span>
              </div>
              <div className="metric-value">{securityEvents}</div>
            </div>
          </div>

          {/* Pending AI Approvals */}
          <div className="col-span-8 glass-panel animate-enter delay-2" style={{ padding: '24px', minHeight: '380px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
              <h2>AI Candidate Trades (Pending Approval)</h2>
              <span className="status-badge" style={{ background: 'var(--accent-primary-glow)', color: 'var(--accent-primary)' }}>{candidates.length} Pending</span>
            </div>
            
            {systemState === 'HALTED' ? (
              <div style={{ padding: '32px', textAlign: 'center', color: 'var(--danger)' }}>
                <AlertTriangle size={32} style={{ margin: '0 auto 12px' }} />
                <h3>TRADING HALTED</h3>
                <p style={{ marginTop: '8px', color: 'var(--text-muted)' }}>New trades cannot be executed while the system is halted.</p>
              </div>
            ) : candidates.length === 0 ? (
              <div style={{ padding: '32px', textAlign: 'center', color: 'var(--text-muted)' }}>
                No pending trades.
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                {candidates.map(candidate => (
                  <div key={candidate.id} style={{ background: 'rgba(0,0,0,0.2)', borderRadius: '12px', padding: '20px', border: '1px solid var(--border)' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', borderBottom: '1px solid var(--border)', paddingBottom: '16px', marginBottom: '16px' }}>
                      <div>
                        <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
                          <h3 style={{ fontSize: '20px', color: '#fff', margin: 0 }}>{candidate.symbol}</h3>
                          <span className="status-badge status-live">{candidate.action}</span>
                        </div>
                        <div style={{ display: 'flex', gap: '16px', marginTop: '12px', fontFamily: 'JetBrains Mono', fontSize: '13px', flexWrap: 'wrap', alignItems: 'center' }}>
                          <div><span style={{ color: 'var(--text-secondary)' }}>Entry:</span> ₹{Number(candidate.price).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</div>
                          <div><span style={{ color: 'var(--danger)' }}>Stop-Loss:</span> ₹{Number(candidate.stop_loss || candidate.price * 0.98).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</div>
                          <div><span style={{ color: 'var(--success)' }}>Target:</span> ₹{Number(candidate.take_target || candidate.price * 1.05).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</div>
                          <div style={{ background: 'rgba(56, 189, 248, 0.1)', padding: '2px 8px', borderRadius: '4px', border: '1px solid rgba(56, 189, 248, 0.2)' }}>
                            <span style={{ color: '#38bdf8', fontWeight: 600 }}>Qty:</span> {candidate.qty || 1} shares
                          </div>
                          {candidate.allocated_capital && (
                            <div style={{ background: 'rgba(168, 85, 247, 0.1)', padding: '2px 8px', borderRadius: '4px', border: '1px solid rgba(168, 85, 247, 0.2)' }}>
                              <span style={{ color: '#c084fc', fontWeight: 600 }}>Capital:</span> ₹{Number(candidate.allocated_capital).toLocaleString('en-IN')}
                            </div>
                          )}
                          {candidate.risk_budget && (
                            <div style={{ background: 'rgba(239, 68, 68, 0.1)', padding: '2px 8px', borderRadius: '4px', border: '1px solid rgba(239, 68, 68, 0.2)' }}>
                              <span style={{ color: '#f87171', fontWeight: 600 }}>Risk Budget:</span> ₹{Number(candidate.risk_budget).toLocaleString('en-IN')} ({candidate.risk_pct}%)
                            </div>
                          )}
                        </div>
                      </div>
                      <div style={{ textAlign: 'right' }}>
                        <div style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>AI Confidence</div>
                        <div style={{ fontSize: '20px', color: 'var(--success)', fontWeight: 'bold' }}>High</div>
                      </div>
                    </div>
                    
                    <div style={{ marginBottom: '16px' }}>
                      <div style={{ fontSize: '12px', textTransform: 'uppercase', color: 'var(--text-secondary)', marginBottom: '4px' }}>AI Reasoning</div>
                      <p style={{ fontSize: '14px', color: 'var(--text-muted)', margin: 0 }}>
                        {candidate.reasoning}
                      </p>
                    </div>

                    {candidate.sizing_rationale && (
                      <div style={{ marginBottom: '16px', background: 'rgba(255,255,255,0.03)', padding: '8px 12px', borderRadius: '6px', fontSize: '12px', fontFamily: 'JetBrains Mono', color: 'var(--text-secondary)' }}>
                        <span style={{ color: 'var(--accent-primary)', fontWeight: 600 }}>Dynamic Sizer:</span> {candidate.sizing_rationale}
                      </div>
                    )}
                    
                    <div style={{ display: 'flex', gap: '12px', justifyContent: 'flex-end' }}>
                      <button onClick={() => handleTradeAction(candidate.id, 'REJECT')} className="btn btn-outline" style={{ color: 'var(--danger)' }}><XCircle size={16}/> REJECT</button>
                      <button onClick={() => handleTradeAction(candidate.id, 'APPROVE')} className="btn btn-primary"><CheckCircle2 size={16}/> APPROVE {candidate.qty ? `${candidate.qty} SHARES` : '& EXECUTE'}</button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Watchlist & ML */}
          <div className="col-span-4 glass-panel animate-enter delay-2" style={{ padding: '24px', display: 'flex', flexDirection: 'column' }}>
            <h2>Watchlist & ML Predictions</h2>
            <div style={{ overflowY: 'auto', flex: 1, paddingRight: '4px', maxHeight: '420px' }}>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                {watchlist.length === 0 && <div style={{ color: 'var(--text-muted)' }}>Loading watchlist...</div>}
                {watchlist.map((item, idx) => (
                  <div key={idx} style={{ 
                    padding: '16px', 
                    background: 'rgba(255,255,255,0.02)', 
                    borderRadius: '8px', 
                    border: '1px solid var(--border)',
                    borderLeft: item.signal === 'BUY' ? '3px solid var(--success)' : item.signal === 'SELL' ? '3px solid var(--danger)' : ''
                  }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                      <span style={{ fontWeight: 600 }}>{item.symbol}</span>
                      <span style={{ fontFamily: 'JetBrains Mono', color: item.change >= 0 ? 'var(--success)' : 'var(--danger)' }}>
                        ₹{item.ltp?.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                      </span>
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px', marginBottom: '4px' }}>
                      <span style={{ color: 'var(--text-secondary)' }}>ML Predict: <span style={{ color: item.ml_predict === 'BULLISH' ? 'var(--success)' : item.ml_predict === 'BEARISH' ? 'var(--danger)' : 'var(--warning)' }}>{item.ml_predict || item.signal}</span></span>
                      <span style={{ color: 'var(--text-secondary)' }}>Change: {item.change >= 0 ? '+' : ''}{item.change?.toFixed(2)}%</span>
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px' }}>
                      <span style={{ color: 'var(--text-secondary)' }}>RSI: {(item.rsi || 0).toFixed(1)}</span>
                      <span style={{ color: 'var(--text-secondary)' }}>Signal: {item.signal}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Active Positions with Automated SL/TP and Square-off */}
          <div className="col-span-12 glass-panel animate-enter delay-3" style={{ padding: '24px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
              <div>
                <h2>Active Positions & Automated Exit Engine</h2>
                <p style={{ fontSize: '13px', color: 'var(--text-secondary)', marginTop: '2px' }}>
                  Live Stop-Loss and Target levels monitored continuously. Positions auto-exit upon breach.
                </p>
              </div>
              {positions.length > 0 && (
                <button 
                  onClick={handleSquareOffAll}
                  className="btn btn-outline"
                  style={{ color: 'var(--danger)', borderColor: 'var(--danger)', fontSize: '13px', padding: '8px 16px' }}
                  disabled={actionLoading === 'ALL'}
                >
                  <Power size={14} />
                  {actionLoading === 'ALL' ? 'Squaring Off All...' : 'Square Off All'}
                </button>
              )}
            </div>
            
            <table className="data-table">
              <thead>
                <tr>
                  <th>Symbol</th>
                  <th>Qty</th>
                  <th>Avg. Price</th>
                  <th>LTP</th>
                  <th>Unrealized P&L</th>
                  <th>Stop-Loss (Exit)</th>
                  <th>Target (TP)</th>
                  <th style={{ textAlign: 'right' }}>Action</th>
                </tr>
              </thead>
              <tbody>
                {positions.length === 0 && (
                  <tr>
                    <td colSpan={8} style={{ textAlign: 'center', color: 'var(--text-muted)', padding: '24px' }}>
                      No active positions. Approved candidate trades will appear here with active SL/TP monitors.
                    </td>
                  </tr>
                )}
                {positions.map((pos, idx) => (
                  <tr key={idx}>
                    <td style={{ fontWeight: 600 }}>{pos.symbol}</td>
                    <td className="font-mono">{pos.qty}</td>
                    <td className="font-mono">₹{pos.avg?.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</td>
                    <td className="font-mono">₹{pos.ltp?.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</td>
                    <td className="font-mono">
                      <span style={{ color: (pos.pnl || 0) >= 0 ? 'var(--success)' : 'var(--danger)', fontWeight: 600 }}>
                        {(pos.pnl || 0) >= 0 ? '+' : ''}₹{(pos.pnl || 0).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                        <span style={{ fontSize: '11px', marginLeft: '6px', opacity: 0.85 }}>
                          ({(pos.pnl_pct || 0) >= 0 ? '+' : ''}{(pos.pnl_pct || 0).toFixed(2)}%)
                        </span>
                      </span>
                    </td>
                    <td className="font-mono">
                      <span style={{ color: 'var(--danger)', background: 'var(--danger-bg)', padding: '3px 8px', borderRadius: '4px', fontSize: '12px' }}>
                        ₹{(pos.stop_loss || pos.avg * 0.98)?.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                      </span>
                    </td>
                    <td className="font-mono">
                      <span style={{ color: 'var(--success)', background: 'var(--success-bg)', padding: '3px 8px', borderRadius: '4px', fontSize: '12px' }}>
                        ₹{(pos.take_target || pos.avg * 1.05)?.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                      </span>
                    </td>
                    <td style={{ textAlign: 'right' }}>
                      <button
                        onClick={() => handleSquareOff(pos.symbol, pos.qty)}
                        className="btn btn-outline"
                        style={{ padding: '6px 14px', fontSize: '12px', color: 'var(--danger)', borderColor: 'rgba(239, 68, 68, 0.4)' }}
                        disabled={actionLoading === pos.symbol}
                      >
                        {actionLoading === pos.symbol ? 'Exiting...' : 'Square Off'}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Live Recent Audit Logs */}
          <div className="col-span-12 glass-panel animate-enter delay-3" style={{ padding: '24px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
              <div>
                <h2>Live Audit Log Stream</h2>
                <p style={{ fontSize: '13px', color: 'var(--text-secondary)', marginTop: '2px' }}>
                  Complete audit trail of signals, risk decisions, automated SL/TP exits, and order executions.
                </p>
              </div>
              <button onClick={fetchAuditLogs} className="btn btn-outline" style={{ fontSize: '12px', padding: '6px 12px' }}>
                Refresh
              </button>
            </div>

            <table className="data-table">
              <thead>
                <tr>
                  <th>Timestamp</th>
                  <th>Event Type</th>
                  <th>Symbol</th>
                  <th>Action / Result</th>
                  <th>Details</th>
                </tr>
              </thead>
              <tbody>
                {auditLogs.length === 0 && (
                  <tr>
                    <td colSpan={5} style={{ textAlign: 'center', color: 'var(--text-muted)' }}>No audit events logged yet.</td>
                  </tr>
                )}
                {auditLogs.map((log, idx) => (
                  <tr key={idx}>
                    <td className="font-mono" style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
                      {new Date(log.timestamp).toLocaleTimeString()}
                    </td>
                    <td>
                      <span className="status-badge" style={{
                        background: log.event_type === 'POSITION_EXIT' ? 'var(--danger-bg)' : 
                                    log.event_type === 'ORDER_EVENT' ? 'var(--success-bg)' : 
                                    'rgba(255,255,255,0.05)',
                        color: log.event_type === 'POSITION_EXIT' ? 'var(--danger)' : 
                               log.event_type === 'ORDER_EVENT' ? 'var(--success)' : 
                               'var(--text-primary)'
                      }}>
                        {log.event_type}
                      </span>
                    </td>
                    <td style={{ fontWeight: 600 }}>{log.symbol || '-'}</td>
                    <td>
                      <span style={{ 
                        color: log.action === 'APPROVE' || log.action === 'SUBMITTED' ? 'var(--success)' :
                               log.action === 'REJECT' || log.action === 'STOP_LOSS' ? 'var(--danger)' :
                               log.action === 'TAKE_PROFIT' ? 'var(--success)' : 'inherit',
                        fontWeight: 500
                      }}>
                        {log.action}
                      </span>
                    </td>
                    <td style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>{log.details}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

        </div>
      </main>
    </div>
  );
}
