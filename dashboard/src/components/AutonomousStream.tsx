import { Zap, AlertTriangle } from 'lucide-react';
import type { AutonomousTrade } from '../types';

interface AutonomousStreamProps {
  systemState: string;
  trades: AutonomousTrade[];
}

export const AutonomousStream: React.FC<AutonomousStreamProps> = ({ systemState, trades }) => {
  return (
    <div className="col-span-8 glass-panel animate-enter delay-2" style={{ padding: '24px', minHeight: '380px' }}>
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: '20px',
          flexWrap: 'wrap',
          gap: '12px',
        }}
      >
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <Zap size={22} color="#10b981" />
            <h2 style={{ margin: 0 }}>Autonomous Execution Stream</h2>
          </div>
          <p style={{ fontSize: '13px', color: 'var(--text-secondary)', marginTop: '4px' }}>
            Quant & ML signals executed directly into live dry-run broker with zero manual approval.
          </p>
        </div>
        <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
          <span
            className="status-badge"
            style={{
              background: 'rgba(16, 185, 129, 0.15)',
              color: '#10b981',
              border: '1px solid rgba(16, 185, 129, 0.3)',
            }}
          >
            <div className="pulse-dot" style={{ background: '#10b981' }}></div>
            AUTONOMOUS ON
          </span>
          <span
            className="status-badge"
            style={{
              background: 'rgba(56, 189, 248, 0.15)',
              color: '#38bdf8',
              border: '1px solid rgba(56, 189, 248, 0.3)',
            }}
          >
            {trades.length} EXECUTED
          </span>
        </div>
      </div>

      {systemState === 'HALTED' ? (
        <div style={{ padding: '32px', textAlign: 'center', color: 'var(--danger)' }}>
          <AlertTriangle size={32} style={{ margin: '0 auto 12px' }} />
          <h3>TRADING HALTED</h3>
          <p style={{ marginTop: '8px', color: 'var(--text-muted)' }}>
            Autonomous execution is suspended while the system is halted.
          </p>
        </div>
      ) : trades.length === 0 ? (
        <div
          style={{
            padding: '40px',
            textAlign: 'center',
            color: 'var(--text-muted)',
            background: 'rgba(0,0,0,0.2)',
            borderRadius: '12px',
            border: '1px dashed var(--border)',
          }}
        >
          <Zap size={32} style={{ margin: '0 auto 12px', color: '#10b981', opacity: 0.6 }} />
          <h3 style={{ color: '#fff', fontSize: '16px' }}>Autonomous Engine Active & Scanning Market Data</h3>
          <p style={{ marginTop: '8px', fontSize: '13px', maxWidth: '480px', margin: '8px auto 0' }}>
            As ML and Quant strategies detect signals, trades are automatically sized, risk-validated, and executed
            without manual approval.
          </p>
        </div>
      ) : (
        <div
          style={{
            display: 'flex',
            flexDirection: 'column',
            gap: '16px',
            maxHeight: '440px',
            overflowY: 'auto',
            paddingRight: '4px',
          }}
        >
          {trades.map((trade) => (
            <div
              key={trade.id}
              style={{
                background: 'rgba(0,0,0,0.25)',
                borderRadius: '12px',
                padding: '20px',
                border: '1px solid rgba(16, 185, 129, 0.25)',
              }}
            >
              <div
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  borderBottom: '1px solid var(--border)',
                  paddingBottom: '16px',
                  marginBottom: '16px',
                  flexWrap: 'wrap',
                  gap: '12px',
                }}
              >
                <div>
                  <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
                    <h3 style={{ fontSize: '20px', color: '#fff', margin: 0 }}>{trade.symbol}</h3>
                    <span className={`status-badge ${trade.action === 'BUY' ? 'status-live' : 'status-warning'}`}>
                      {trade.action}
                    </span>
                    <span
                      className="status-badge"
                      style={{
                        background: 'rgba(16, 185, 129, 0.2)',
                        color: '#34d399',
                        border: '1px solid rgba(16, 185, 129, 0.4)',
                        fontWeight: 600,
                      }}
                    >
                      ⚡ AUTO-EXECUTED
                    </span>
                  </div>
                  <div
                    style={{
                      display: 'flex',
                      gap: '16px',
                      marginTop: '12px',
                      fontFamily: 'JetBrains Mono',
                      fontSize: '13px',
                      flexWrap: 'wrap',
                      alignItems: 'center',
                    }}
                  >
                    <div>
                      <span style={{ color: 'var(--text-secondary)' }}>Entry:</span> ₹
                      {Number(trade.price).toLocaleString('en-IN', {
                        minimumFractionDigits: 2,
                        maximumFractionDigits: 2,
                      })}
                    </div>
                    <div>
                      <span style={{ color: 'var(--danger)' }}>Stop-Loss:</span> ₹
                      {Number(trade.stop_loss || trade.price * 0.98).toLocaleString('en-IN', {
                        minimumFractionDigits: 2,
                        maximumFractionDigits: 2,
                      })}
                    </div>
                    <div>
                      <span style={{ color: 'var(--success)' }}>Target:</span> ₹
                      {Number(trade.take_target || trade.price * 1.05).toLocaleString('en-IN', {
                        minimumFractionDigits: 2,
                        maximumFractionDigits: 2,
                      })}
                    </div>
                    <div
                      style={{
                        background: 'rgba(56, 189, 248, 0.1)',
                        padding: '2px 8px',
                        borderRadius: '4px',
                        border: '1px solid rgba(56, 189, 248, 0.2)',
                      }}
                    >
                      <span style={{ color: '#38bdf8', fontWeight: 600 }}>Qty:</span> {trade.qty || 1} shares
                    </div>
                    {trade.allocated_capital && (
                      <div
                        style={{
                          background: 'rgba(168, 85, 247, 0.1)',
                          padding: '2px 8px',
                          borderRadius: '4px',
                          border: '1px solid rgba(168, 85, 247, 0.2)',
                        }}
                      >
                        <span style={{ color: '#c084fc', fontWeight: 600 }}>Capital:</span> ₹
                        {Number(trade.allocated_capital).toLocaleString('en-IN')}
                      </div>
                    )}
                    {trade.risk_budget && (
                      <div
                        style={{
                          background: 'rgba(239, 68, 68, 0.1)',
                          padding: '2px 8px',
                          borderRadius: '4px',
                          border: '1px solid rgba(239, 68, 68, 0.2)',
                        }}
                      >
                        <span style={{ color: '#f87171', fontWeight: 600 }}>Risk Budget:</span> ₹
                        {Number(trade.risk_budget).toLocaleString('en-IN')} ({trade.risk_pct}%)
                      </div>
                    )}
                  </div>
                </div>
                <div style={{ textAlign: 'right' }}>
                  <div style={{ fontSize: '12px', color: 'var(--text-secondary)', fontFamily: 'JetBrains Mono' }}>
                    {trade.timestamp ? `Time: ${trade.timestamp}` : ''}
                  </div>
                  <div style={{ fontSize: '12px', color: '#38bdf8', fontFamily: 'JetBrains Mono', marginTop: '4px' }}>
                    Order: #{trade.broker_order_id ? String(trade.broker_order_id).slice(-8) : String(trade.id).slice(-8)}
                  </div>
                  <div style={{ fontSize: '11px', color: '#10b981', marginTop: '4px', fontWeight: 600 }}>
                    ✓ PLACED WITH BROKER
                  </div>
                </div>
              </div>

              <div style={{ marginBottom: '12px' }}>
                <div
                  style={{
                    fontSize: '12px',
                    textTransform: 'uppercase',
                    color: 'var(--text-secondary)',
                    marginBottom: '4px',
                  }}
                >
                  AI Reasoning
                </div>
                <p style={{ fontSize: '14px', color: 'var(--text-muted)', margin: 0 }}>{trade.reasoning}</p>
              </div>

              {trade.sizing_rationale && (
                <div
                  style={{
                    background: 'rgba(255,255,255,0.03)',
                    padding: '8px 12px',
                    borderRadius: '6px',
                    fontSize: '12px',
                    fontFamily: 'JetBrains Mono',
                    color: 'var(--text-secondary)',
                  }}
                >
                  <span style={{ color: 'var(--accent-primary)', fontWeight: 600 }}>Dynamic Sizer:</span>{' '}
                  {trade.sizing_rationale}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
