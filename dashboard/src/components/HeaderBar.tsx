import React from 'react';
import { FileText } from 'lucide-react';

interface HeaderBarProps {
  pnl: number;
  margin: number;
  onOpenPaperReport?: () => void;
}

export const HeaderBar: React.FC<HeaderBarProps> = ({ pnl, margin, onOpenPaperReport }) => {
  return (
    <header className="header-bar animate-enter">
      <div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <h1 style={{ fontSize: '28px', color: '#fff', margin: 0 }}>Autonomous Trading Terminal</h1>
          <span
            className="status-badge"
            style={{
              background: 'rgba(16, 185, 129, 0.2)',
              color: '#34d399',
              border: '1px solid rgba(16, 185, 129, 0.4)',
            }}
          >
            ⚡ ZERO-CLICK AUTO-EXECUTION
          </span>
        </div>
        <p style={{ color: 'var(--text-secondary)', marginTop: '4px' }}>
          Multi-regime algorithmic signals, dynamic Kelly sizing, and institutional risk-validated broker execution
        </p>
      </div>
      <div style={{ display: 'flex', gap: '16px', alignItems: 'center' }}>
        {onOpenPaperReport && (
          <button
            onClick={onOpenPaperReport}
            className="btn btn-secondary"
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              padding: '9px 16px',
              borderRadius: '8px',
              background: 'linear-gradient(135deg, rgba(16, 185, 129, 0.15), rgba(5, 150, 105, 0.25))',
              color: '#34d399',
              border: '1px solid rgba(16, 185, 129, 0.35)',
              cursor: 'pointer',
              fontWeight: 600,
              fontSize: '13px',
              boxShadow: '0 2px 8px rgba(0,0,0,0.2)',
            }}
            title="View 3-7 Day Paper-Trading Forward Validation Report"
          >
            <FileText size={16} /> Paper Report
          </button>
        )}
        <div
          style={{
            textAlign: 'right',
            background: pnl >= 0 ? 'rgba(16, 185, 129, 0.08)' : 'rgba(239, 68, 68, 0.08)',
            padding: '8px 16px',
            borderRadius: '10px',
            border: pnl >= 0 ? '1px solid rgba(16, 185, 129, 0.25)' : '1px solid rgba(239, 68, 68, 0.25)',
          }}
        >
          <div
            style={{
              fontSize: '11px',
              color: 'var(--text-secondary)',
              textTransform: 'uppercase',
              letterSpacing: '0.5px',
              fontWeight: 600,
            }}
          >
            Overall Profit (Today)
          </div>
          <div
            style={{
              fontSize: '22px',
              fontWeight: 'bold',
              color: pnl >= 0 ? '#10b981' : '#ef4444',
              fontFamily: 'JetBrains Mono',
            }}
          >
            {pnl >= 0 ? '+' : ''}₹
            {pnl.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </div>
        </div>
        <div style={{ textAlign: 'right' }}>
          <div style={{ fontSize: '12px', color: 'var(--text-secondary)', textTransform: 'uppercase' }}>
            Available Margin
          </div>
          <div style={{ fontSize: '24px', fontWeight: 'bold', color: '#fff', fontFamily: 'JetBrains Mono' }}>
            ₹{margin.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </div>
        </div>
      </div>
    </header>
  );
};
