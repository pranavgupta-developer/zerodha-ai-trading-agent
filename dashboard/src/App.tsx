import { useState, useEffect, useRef } from 'react';
import { AlertTriangle, CheckCircle2 } from 'lucide-react';
import type { 
  WatchlistItem, 
  PositionItem, 
  AutonomousTrade, 
  AuditLogItem, 
  FeedbackMessage 
} from './types';
import { ZerodhaAuthModal } from './components/ZerodhaAuthModal';
import { Sidebar } from './components/Sidebar';
import { HeaderBar } from './components/HeaderBar';
import { MetricsGrid } from './components/MetricsGrid';
import { AutonomousStream } from './components/AutonomousStream';
import { WatchlistML } from './components/WatchlistML';
import { PositionsTable } from './components/PositionsTable';
import { AuditLogStream } from './components/AuditLogStream';
import { PaperReportModal } from './components/PaperReportModal';

const API_BASE = "http://localhost:8000/api/v1";
const WS_URL = "ws://localhost:8000/ws/candidate-trades";

export default function App() {
  const [systemState, setSystemState] = useState('LIVE');
  const [wsConnected, setWsConnected] = useState(false);
  const [watchlist, setWatchlist] = useState<WatchlistItem[]>([]);
  const [positions, setPositions] = useState<PositionItem[]>([]);
  const [margin, setMargin] = useState(0);
  const [pnl, setPnl] = useState(0);
  const [dayRealizedPnl, setDayRealizedPnl] = useState(0);
  const [dayUnrealizedPnl, setDayUnrealizedPnl] = useState(0);
  const [autonomousTrades, setAutonomousTrades] = useState<AutonomousTrade[]>([]);
  const [securityEvents, setSecurityEvents] = useState(0);
  const [auditLogs, setAuditLogs] = useState<AuditLogItem[]>([]);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [feedbackMsg, setFeedbackMsg] = useState<FeedbackMessage | null>(null);
  const [zerodhaAuth, setZerodhaAuth] = useState(false);
  const [zerodhaLoginUrl, setZerodhaLoginUrl] = useState('');
  const [marketOpen, setMarketOpen] = useState(false);
  const [marketStatus, setMarketStatus] = useState('CLOSED');
  const [marketHours, setMarketHours] = useState('09:30 - 15:30 IST');
  const [showTokenModal, setShowTokenModal] = useState(false);
  const [showPaperReportModal, setShowPaperReportModal] = useState(false);
  const [tokenInput, setTokenInput] = useState('');
  const [submittingToken, setSubmittingToken] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    fetchSystemStatus();
    fetchPortfolio();
    fetchAuditLogs();
    connectWebSocket();

    const auditTimer = setInterval(fetchAuditLogs, 4000);
    const statusTimer = setInterval(fetchSystemStatus, 10000);
    return () => {
      clearInterval(auditTimer);
      clearInterval(statusTimer);
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
      setZerodhaAuth(Boolean(data.zerodha_authenticated));
      setZerodhaLoginUrl(data.login_url || '');
      setMarketOpen(Boolean(data.market_open));
      setMarketStatus(data.market_status || 'CLOSED');
      setMarketHours(data.market_hours || '09:30 - 15:30 IST');
    } catch (e) {
      console.error("Failed to fetch system status", e);
    }
  };

  const handleConnectToken = async () => {
    if (!tokenInput.trim()) return;
    setSubmittingToken(true);
    try {
      const res = await fetch(`${API_BASE}/auth/token`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token: tokenInput.trim() })
      });
      const data = await res.json();
      if (res.ok && data.status === 'success') {
        showToast('Zerodha session verified & live feed connected!', 'success');
        setZerodhaAuth(true);
        setShowTokenModal(false);
        setTokenInput('');
        fetchPortfolio();
        fetchSystemStatus();
      } else {
        showToast(data.detail || 'Failed to authenticate token with Zerodha', 'danger');
      }
    } catch (e) {
      showToast('Error sending token to server', 'danger');
    } finally {
      setSubmittingToken(false);
    }
  };

  const fetchPortfolio = async () => {
    try {
      const res = await fetch(`${API_BASE}/portfolio`);
      const data = await res.json();
      if (data) {
        setWatchlist(data.watchlist || []);
        setPositions(data.positions || []);
        setMargin(data.account_stats?.margin || 0);
        if (data.autonomous_trades && Array.isArray(data.autonomous_trades)) {
          setAutonomousTrades(data.autonomous_trades);
        }
        const realized = Number(data.account_stats?.realized_pnl || 0);
        const holdingsPnl = (data.holdings || []).reduce((acc: number, h: any) => acc + (h.pnl || 0), 0);
        const posPnl = (data.positions || []).reduce((acc: number, p: any) => acc + (p.pnl || 0), 0);
        const unrealized = (data.account_stats?.unrealized_pnl !== undefined) 
          ? Number(data.account_stats.unrealized_pnl) 
          : (holdingsPnl + posPnl);
        
        setDayRealizedPnl(realized);
        setDayUnrealizedPnl(unrealized);
        setPnl(realized);
      }
    } catch (e) {
      console.error("Failed to fetch initial portfolio", e);
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
          
          const realized = Number(data.account_stats?.realized_pnl || 0);
          const holdingsPnl = (data.holdings || []).reduce((acc: number, h: any) => acc + (h.pnl || 0), 0);
          const posPnl = (data.positions || []).reduce((acc: number, p: any) => acc + (p.pnl || 0), 0);
          const unrealized = (data.account_stats?.unrealized_pnl !== undefined) 
            ? Number(data.account_stats.unrealized_pnl) 
            : (holdingsPnl + posPnl);
          
          setDayRealizedPnl(realized);
          setDayUnrealizedPnl(unrealized);
          setPnl(realized);

          if (data.autonomous_trades && Array.isArray(data.autonomous_trades)) {
            setAutonomousTrades(data.autonomous_trades);
          }
        } else if (data.type === 'autonomous_trade') {
          setAutonomousTrades(prev => {
            if (prev.find(t => t.id === data.trade.id)) return prev;
            return [data.trade, ...prev].slice(0, 30);
          });
          showToast(`⚡ Auto-Executed: ${data.trade.action} ${data.trade.qty}x ${data.trade.symbol} @ ₹${Number(data.trade.price).toFixed(2)}`);
          fetchAuditLogs();
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

      {/* Zerodha Auth Modal */}
      <ZerodhaAuthModal
        show={showTokenModal}
        loginUrl={zerodhaLoginUrl}
        tokenInput={tokenInput}
        submittingToken={submittingToken}
        onTokenChange={setTokenInput}
        onClose={() => setShowTokenModal(false)}
        onSubmit={handleConnectToken}
      />

      {/* 3-7 Day Paper Forward Validation Report Modal */}
      <PaperReportModal
        show={showPaperReportModal}
        onClose={() => setShowPaperReportModal(false)}
        onShowToast={showToast}
      />

      {/* Sidebar */}
      <Sidebar
        systemState={systemState}
        zerodhaAuth={zerodhaAuth}
        zerodhaLoginUrl={zerodhaLoginUrl}
        wsConnected={wsConnected}
        marketOpen={marketOpen}
        marketStatus={marketStatus}
        marketHours={marketHours}
        onOpenTokenModal={() => setShowTokenModal(true)}
        onEmergencyStop={handleEmergencyStop}
        onOpenPaperReport={() => setShowPaperReportModal(true)}
      />

      {/* Main Content */}
      <main className="main-content">
        <HeaderBar pnl={pnl} margin={margin} onOpenPaperReport={() => setShowPaperReportModal(true)} />

        <div className="dashboard-grid">
          {/* Key Metrics */}
          <MetricsGrid
            pnl={pnl}
            dayRealizedPnl={dayRealizedPnl}
            dayUnrealizedPnl={dayUnrealizedPnl}
            positionsCount={positions.length}
            autonomousTradesCount={autonomousTrades.length}
            securityEventsCount={securityEvents}
          />

          {/* Autonomous AI Execution Stream */}
          <AutonomousStream systemState={systemState} trades={autonomousTrades} />

          {/* Watchlist & ML Predictions */}
          <WatchlistML watchlist={watchlist} />

          {/* Active Positions with Automated SL/TP and Square-off */}
          <PositionsTable
            positions={positions}
            actionLoading={actionLoading}
            onSquareOff={handleSquareOff}
            onSquareOffAll={handleSquareOffAll}
          />

          {/* Live Recent Audit Logs */}
          <AuditLogStream logs={auditLogs} onRefresh={fetchAuditLogs} />
        </div>
      </main>
    </div>
  );
}
