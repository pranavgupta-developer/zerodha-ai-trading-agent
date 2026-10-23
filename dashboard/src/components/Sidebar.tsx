import React from 'react';
import { Activity, Power, FileText } from 'lucide-react';

interface SidebarProps {
  systemState: string;
  zerodhaAuth: boolean;
  zerodhaLoginUrl: string;
  wsConnected: boolean;
  marketOpen?: boolean;
  marketStatus?: string;
  marketHours?: string;
  onOpenTokenModal: () => void;
  onEmergencyStop: () => void;
  onOpenPaperReport?: () => void;
}

export const Sidebar: React.FC<SidebarProps> = ({
  systemState,
  zerodhaAuth,
  zerodhaLoginUrl,
  wsConnected,
  marketOpen = false,
  marketHours = '09:30 - 15:30 IST',
  onOpenTokenModal,
  onEmergencyStop,
  onOpenPaperReport,
}) => {
  const engineBadge = systemState === 'HALTED' 
    ? 'HALTED' 
    : !marketOpen 
    ? 'IDLE (CLOSED)' 
    : 'LIVE';

  return (
    <aside
      className="sidebar glass-panel"
      style={{ borderRadius: 0, borderTop: 0, borderBottom: 0, borderLeft: 0 }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '16px' }}>
        <Activity color="var(--accent-primary)" size={28} />
        <h1 style={{ margin: 0, fontSize: '22px' }}>OmniTrade</h1>
      </div>

      <div>
        <h3>System Health</h3>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px', marginTop: '16px' }}>
          {/* Market Hours Status */}
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ color: 'var(--text-secondary)' }}>Market Session</span>
            <span
              className={`status-badge ${marketOpen ? 'status-live' : ''}`}
              style={
                !marketOpen
                  ? {
                      background: 'rgba(148, 163, 184, 0.12)',
                      color: '#94a3b8',
                      border: '1px solid rgba(148, 163, 184, 0.25)',
                    }
                  : {}
              }
              title={`NSE Equity Session Hours: ${marketHours}`}
            >
              <div
                className="pulse-dot"
                style={{ background: marketOpen ? '#10b981' : '#64748b' }}
              ></div>
              {marketOpen ? 'OPEN' : 'CLOSED'}
            </span>
          </div>

          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ color: 'var(--text-secondary)' }}>Trading Engine</span>
            <span
              className={`status-badge ${
                systemState === 'HALTED'
                  ? 'status-halted'
                  : marketOpen
                  ? 'status-live'
                  : ''
              }`}
              style={
                !marketOpen && systemState !== 'HALTED'
                  ? {
                      background: 'rgba(234, 179, 8, 0.12)',
                      color: '#facc15',
                      border: '1px solid rgba(234, 179, 8, 0.25)',
                    }
                  : {}
              }
            >
              <div
                className={`pulse-dot ${
                  systemState === 'HALTED' ? 'danger' : ''
                }`}
                style={
                  !marketOpen && systemState !== 'HALTED'
                    ? { background: '#facc15' }
                    : {}
                }
              ></div>
              {engineBadge}
            </span>
          </div>

          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ color: 'var(--text-secondary)' }}>Zerodha Feed</span>
            {zerodhaAuth ? (
              <span
                className="status-badge status-live"
                title="Streaming real-time live market ticks directly from Zerodha Kite Connect"
              >
                <div className="pulse-dot"></div> ZERODHA LIVE
              </span>
            ) : (
              <div style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
                <a
                  href={zerodhaLoginUrl || 'http://localhost:8000/api/v1/auth/login?redirect=true'}
                  target="_blank"
                  rel="noreferrer"
                  className="status-badge status-warning"
                  style={{ textDecoration: 'none', cursor: 'pointer', padding: '3px 8px', fontSize: '11px' }}
                  title="Authenticate with Zerodha Kite"
                >
                  <div className="pulse-dot danger"></div> AUTH REQ ↗
                </a>
                <button
                  onClick={onOpenTokenModal}
                  className="btn btn-secondary"
                  style={{ padding: '3px 8px', fontSize: '11px', borderRadius: '4px' }}
                  title="Paste Daily Access Token"
                >
                  Token
                </button>
              </div>
            )}
          </div>

          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ color: 'var(--text-secondary)' }}>Broker WebSocket</span>
            <span className={`status-badge ${wsConnected ? 'status-live' : 'status-warning'}`}>
              <div className="pulse-dot"></div> {wsConnected ? 'CONNECTED' : 'DISCONNECTED'}
            </span>
          </div>

          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ color: 'var(--text-secondary)' }}>Execution Mode</span>
            <span
              className="status-badge"
              style={
                marketOpen
                  ? {
                      background: 'rgba(16, 185, 129, 0.15)',
                      color: '#10b981',
                      border: '1px solid rgba(16, 185, 129, 0.3)',
                    }
                  : {
                      background: 'rgba(148, 163, 184, 0.12)',
                      color: '#94a3b8',
                      border: '1px solid rgba(148, 163, 184, 0.25)',
                    }
              }
            >
              <div
                className="pulse-dot"
                style={{ background: marketOpen ? '#10b981' : '#64748b' }}
              ></div>{' '}
              {marketOpen ? 'AUTONOMOUS' : 'PAUSED (OFF-HOURS)'}
            </span>
          </div>

          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ color: 'var(--text-secondary)' }}>Exit Monitor</span>
            <span
              className="status-badge"
              style={
                marketOpen
                  ? {
                      background: 'rgba(16, 185, 129, 0.15)',
                      color: '#10b981',
                      border: '1px solid rgba(16, 185, 129, 0.3)',
                    }
                  : {
                      background: 'rgba(148, 163, 184, 0.12)',
                      color: '#94a3b8',
                      border: '1px solid rgba(148, 163, 184, 0.25)',
                    }
              }
            >
              <div
                className="pulse-dot"
                style={{ background: marketOpen ? '#10b981' : '#64748b' }}
              ></div>{' '}
              {marketOpen ? 'ACTIVE (SL/TP)' : 'STANDBY'}
            </span>
          </div>
        </div>
      </div>

      <div style={{ marginTop: 'auto', display: 'flex', flexDirection: 'column', gap: '10px' }}>
        {onOpenPaperReport && (
          <button
            className="btn btn-secondary"
            style={{
              width: '100%',
              padding: '12px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '8px',
              background: 'linear-gradient(135deg, rgba(16, 185, 129, 0.12), rgba(5, 150, 105, 0.2))',
              color: '#34d399',
              border: '1px solid rgba(16, 185, 129, 0.35)',
              fontWeight: 600,
              fontSize: '13px',
              borderRadius: '8px',
              cursor: 'pointer',
            }}
            onClick={onOpenPaperReport}
          >
            <FileText size={16} />
            Paper Report
          </button>
        )}
        <button
          className="btn btn-danger"
          style={{ width: '100%', padding: '16px' }}
          onClick={onEmergencyStop}
          disabled={systemState === 'HALTED'}
        >
          <Power size={18} />
          EMERGENCY STOP
        </button>
      </div>
    </aside>
  );
};
