import React from 'react';
import { TrendingUp, Activity, Zap, ShieldAlert } from 'lucide-react';

interface MetricsGridProps {
  pnl: number;
  dayRealizedPnl: number;
  dayUnrealizedPnl: number;
  positionsCount: number;
  autonomousTradesCount: number;
  securityEventsCount: number;
}

export const MetricsGrid: React.FC<MetricsGridProps> = ({
  pnl,
  dayRealizedPnl,
  dayUnrealizedPnl,
  positionsCount,
  autonomousTradesCount,
  securityEventsCount,
}) => {
  const netTotal = dayRealizedPnl + dayUnrealizedPnl;

  return (
    <div className="col-span-12 dashboard-grid animate-enter delay-1">
      <div
        className="col-span-3 glass-panel card"
        style={{ borderLeft: pnl >= 0 ? '4px solid #10b981' : '4px solid #ef4444' }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: 'var(--text-secondary)' }}>
          <TrendingUp size={16} color={pnl >= 0 ? '#10b981' : '#ef4444'} />
          <span style={{ fontSize: '13px', fontWeight: 600, textTransform: 'uppercase' }}>
            Overall Profit of the Day
          </span>
        </div>
        <div
          className={`metric-value ${pnl >= 0 ? 'text-success' : 'text-danger'}`}
          style={{ background: 'none', WebkitTextFillColor: 'initial' }}
        >
          {pnl >= 0 ? '+' : ''}₹
          {pnl.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
        </div>
        <div style={{ fontSize: '12px', color: 'var(--text-secondary)', marginTop: '4px' }}>
          Unrealized P&L:{' '}
          <span style={{ color: dayUnrealizedPnl >= 0 ? 'var(--success)' : 'var(--danger)', fontWeight: 600 }}>
            {dayUnrealizedPnl >= 0 ? '+' : ''}₹{dayUnrealizedPnl.toFixed(2)}
          </span>{' '}
          | Net Total:{' '}
          <span style={{ color: netTotal >= 0 ? 'var(--success)' : 'var(--danger)', fontWeight: 600 }}>
            {netTotal >= 0 ? '+' : ''}₹{netTotal.toFixed(2)}
          </span>
        </div>
      </div>

      <div className="col-span-3 glass-panel card">
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: 'var(--text-secondary)' }}>
          <Activity size={16} />{' '}
          <span style={{ fontSize: '13px', fontWeight: 600, textTransform: 'uppercase' }}>Active Positions</span>
        </div>
        <div className="metric-value">{positionsCount}</div>
      </div>

      <div className="col-span-3 glass-panel card" style={{ borderLeft: '4px solid #10b981' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: 'var(--text-secondary)' }}>
          <Zap size={16} color="#10b981" />{' '}
          <span style={{ fontSize: '13px', fontWeight: 600, textTransform: 'uppercase' }}>Auto-Executed Trades</span>
        </div>
        <div className="metric-value" style={{ color: '#10b981' }}>
          {autonomousTradesCount}
        </div>
        <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>100% Autonomous (Zero manual click)</div>
      </div>

      <div className="col-span-3 glass-panel card" style={{ borderLeft: '4px solid var(--warning)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: 'var(--text-secondary)' }}>
          <ShieldAlert size={16} color="var(--warning)" />{' '}
          <span style={{ fontSize: '13px', fontWeight: 600, textTransform: 'uppercase' }}>Security Events</span>
        </div>
        <div className="metric-value">{securityEventsCount}</div>
      </div>
    </div>
  );
};
