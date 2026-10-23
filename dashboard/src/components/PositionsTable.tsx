import { Power } from 'lucide-react';
import type { PositionItem } from '../types';

interface PositionsTableProps {
  positions: PositionItem[];
  actionLoading: string | null;
  onSquareOff: (symbol: string, quantity: number) => void;
  onSquareOffAll: () => void;
}

export const PositionsTable: React.FC<PositionsTableProps> = ({
  positions,
  actionLoading,
  onSquareOff,
  onSquareOffAll,
}) => {
  return (
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
            onClick={onSquareOffAll}
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
                No active positions. Auto-executed trades will appear here with active SL/TP monitors.
              </td>
            </tr>
          )}
          {positions.map((pos, idx) => (
            <tr key={idx}>
              <td style={{ fontWeight: 600 }}>{pos.symbol}</td>
              <td className="font-mono">{pos.qty}</td>
              <td className="font-mono">
                ₹{pos.avg?.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
              </td>
              <td className="font-mono">
                ₹{pos.ltp?.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
              </td>
              <td className="font-mono">
                <span style={{ color: (pos.pnl || 0) >= 0 ? 'var(--success)' : 'var(--danger)', fontWeight: 600 }}>
                  {(pos.pnl || 0) >= 0 ? '+' : ''}₹
                  {(pos.pnl || 0).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                  <span style={{ fontSize: '11px', marginLeft: '6px', opacity: 0.85 }}>
                    ({(pos.pnl_pct || 0) >= 0 ? '+' : ''}
                    {(pos.pnl_pct || 0).toFixed(2)}%)
                  </span>
                </span>
              </td>
              <td className="font-mono">
                <span
                  style={{
                    color: 'var(--danger)',
                    background: 'var(--danger-bg)',
                    padding: '3px 8px',
                    borderRadius: '4px',
                    fontSize: '12px',
                  }}
                >
                  ₹
                  {(pos.stop_loss || pos.avg * 0.98)?.toLocaleString('en-IN', {
                    minimumFractionDigits: 2,
                    maximumFractionDigits: 2,
                  })}
                </span>
              </td>
              <td className="font-mono">
                <span
                  style={{
                    color: 'var(--success)',
                    background: 'var(--success-bg)',
                    padding: '3px 8px',
                    borderRadius: '4px',
                    fontSize: '12px',
                  }}
                >
                  ₹
                  {(pos.take_target || pos.avg * 1.05)?.toLocaleString('en-IN', {
                    minimumFractionDigits: 2,
                    maximumFractionDigits: 2,
                  })}
                </span>
              </td>
              <td style={{ textAlign: 'right' }}>
                <button
                  onClick={() => onSquareOff(pos.symbol, pos.qty)}
                  className="btn btn-outline"
                  style={{
                    padding: '6px 14px',
                    fontSize: '12px',
                    color: 'var(--danger)',
                    borderColor: 'rgba(239, 68, 68, 0.4)',
                  }}
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
  );
};
