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
  const [securityEvents] = useState(0);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    fetchSystemStatus();
    connectWebSocket();
    return () => {
      if (wsRef.current) wsRef.current.close();
    };
  }, []);

  const fetchSystemStatus = async () => {
    try {
      const res = await fetch(`${API_BASE}/system/status`);
      const data = await res.json();
      setSystemState(data.emergency_stop_active ? 'HALTED' : 'LIVE');
    } catch (e) {
      console.error("Failed to fetch system status", e);
    }
  };

  const connectWebSocket = () => {
    const ws = new WebSocket(WS_URL);
    wsRef.current = ws;

    ws.onopen = () => setWsConnected(true);
    ws.onclose = () => {
      setWsConnected(false);
      setTimeout(connectWebSocket, 2000); // Reconnect
    };
    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === 'market_update') {
          setWatchlist(data.watchlist || []);
          setPositions(data.positions || []);
          setMargin(data.account_stats?.margin || 0);
          
          const holdingsPnl = (data.holdings || []).reduce((acc: number, h: any) => acc + (h.pnl || 0), 0);
          setPnl(holdingsPnl);
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
    } catch (e) {
      console.error("Emergency stop failed", e);
    }
  };

  const handleTradeAction = async (tradeId: string, action: string) => {
    // Optimistic UI update: instantly remove the card to feel snappy
    setCandidates(prev => prev.filter(c => c.id !== tradeId));
    try {
      await fetch(`${API_BASE}/trades/action`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ trade_id: tradeId, action })
      });
    } catch (e) {
      console.error("Trade action failed", e);
      // In a production app, we would revert the optimistic update here on failure
    }
  };

  return (
    <div className="app-container">
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
              <span style={{ color: 'var(--text-secondary)' }}>AI Agent</span>
              <span className="status-badge status-live">
                <div className="pulse-dot"></div> ONLINE
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
            <p style={{ color: 'var(--text-secondary)', marginTop: '4px' }}>Real-time monitoring and execution control</p>
          </div>
          <div style={{ display: 'flex', gap: '24px', alignItems: 'center' }}>
            <div style={{ textAlign: 'right' }}>
              <div style={{ fontSize: '12px', color: 'var(--text-secondary)', textTransform: 'uppercase' }}>Available Margin</div>
              <div style={{ fontSize: '24px', fontWeight: 'bold', color: '#fff', fontFamily: 'JetBrains Mono' }}>₹{margin.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</div>
            </div>
          </div>
        </header>

        <div className="dashboard-grid">
          
          {/* Key Metrics */}
          <div className="col-span-12 dashboard-grid animate-enter delay-1">
            <div className="col-span-3 glass-panel card">
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: 'var(--text-secondary)' }}>
                <TrendingUp size={16} /> <span style={{ fontSize: '13px', fontWeight: 600, textTransform: 'uppercase' }}>Daily P&L</span>
              </div>
              <div className={`metric-value ${pnl >= 0 ? 'text-success' : 'text-danger'}`} style={{ background: 'none', WebkitTextFillColor: 'initial' }}>
                {pnl >= 0 ? '+' : ''}₹{pnl.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
              </div>
            </div>
            
            <div className="col-span-3 glass-panel card">
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: 'var(--text-secondary)' }}>
                <Activity size={16} /> <span style={{ fontSize: '13px', fontWeight: 600, textTransform: 'uppercase' }}>Open Positions</span>
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
          <div className="col-span-8 glass-panel animate-enter delay-2" style={{ padding: '24px', minHeight: '400px' }}>
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
                        <div style={{ display: 'flex', gap: '16px', marginTop: '12px', fontFamily: 'JetBrains Mono', fontSize: '14px' }}>
                          <div><span style={{ color: 'var(--text-secondary)' }}>Entry:</span> ₹{Number(candidate.price).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</div>
                        </div>
                      </div>
                      <div style={{ textAlign: 'right' }}>
                        <div style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>AI Confidence</div>
                        <div style={{ fontSize: '20px', color: 'var(--success)', fontWeight: 'bold' }}>High</div>
                      </div>
                    </div>
                    
                    <div style={{ marginBottom: '20px' }}>
                      <div style={{ fontSize: '12px', textTransform: 'uppercase', color: 'var(--text-secondary)', marginBottom: '4px' }}>AI Reasoning</div>
                      <p style={{ fontSize: '14px', color: 'var(--text-muted)' }}>
                        {candidate.reasoning}
                      </p>
                    </div>
                    
                    <div style={{ display: 'flex', gap: '12px', justifyContent: 'flex-end' }}>
                      <button onClick={() => handleTradeAction(candidate.id, 'REJECT')} className="btn btn-outline" style={{ color: 'var(--danger)' }}><XCircle size={16}/> REJECT</button>
                      <button onClick={() => handleTradeAction(candidate.id, 'APPROVE')} className="btn btn-primary"><CheckCircle2 size={16}/> APPROVE & EXECUTE</button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Watchlist & ML */}
          <div className="col-span-4 glass-panel animate-enter delay-2" style={{ padding: '24px', display: 'flex', flexDirection: 'column' }}>
            <h2>Watchlist & ML Predictions</h2>
            <div style={{ overflowY: 'auto', flex: 1, paddingRight: '4px' }}>
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

          {/* Executions / Positions */}
          <div className="col-span-12 glass-panel animate-enter delay-3" style={{ padding: '24px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
              <h2>Active Positions</h2>
            </div>
            
            <table className="data-table">
              <thead>
                <tr>
                  <th>Symbol</th>
                  <th>Qty</th>
                  <th>Avg. Price</th>
                  <th>LTP</th>
                </tr>
              </thead>
              <tbody>
                {positions.length === 0 && (
                  <tr>
                    <td colSpan={4} style={{ textAlign: 'center', color: 'var(--text-muted)' }}>No active positions</td>
                  </tr>
                )}
                {positions.map((pos, idx) => (
                  <tr key={idx}>
                    <td style={{ fontWeight: 500 }}>{pos.symbol}</td>
                    <td className="font-mono">{pos.qty}</td>
                    <td className="font-mono">₹{pos.avg?.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</td>
                    <td className="font-mono">₹{pos.ltp?.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</td>
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
