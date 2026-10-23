import type { AuditLogItem } from '../types';

interface AuditLogStreamProps {
  logs: AuditLogItem[];
  onRefresh: () => void;
}

export const AuditLogStream: React.FC<AuditLogStreamProps> = ({ logs, onRefresh }) => {
  return (
    <div className="col-span-12 glass-panel animate-enter delay-3" style={{ padding: '24px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
        <div>
          <h2>Live Audit Log Stream</h2>
          <p style={{ fontSize: '13px', color: 'var(--text-secondary)', marginTop: '2px' }}>
            Complete audit trail of signals, risk decisions, automated SL/TP exits, and order executions.
          </p>
        </div>
        <button onClick={onRefresh} className="btn btn-outline" style={{ fontSize: '12px', padding: '6px 12px' }}>
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
          {logs.length === 0 && (
            <tr>
              <td colSpan={5} style={{ textAlign: 'center', color: 'var(--text-muted)' }}>
                No audit events logged yet.
              </td>
            </tr>
          )}
          {logs.map((log, idx) => (
            <tr key={idx}>
              <td className="font-mono" style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
                {new Date(log.timestamp).toLocaleTimeString()}
              </td>
              <td>
                <span
                  className="status-badge"
                  style={{
                    background:
                      log.event_type === 'POSITION_EXIT'
                        ? 'var(--danger-bg)'
                        : log.event_type === 'ORDER_EVENT'
                        ? 'var(--success-bg)'
                        : 'rgba(255,255,255,0.05)',
                    color:
                      log.event_type === 'POSITION_EXIT'
                        ? 'var(--danger)'
                        : log.event_type === 'ORDER_EVENT'
                        ? 'var(--success)'
                        : 'var(--text-primary)',
                  }}
                >
                  {log.event_type}
                </span>
              </td>
              <td style={{ fontWeight: 600 }}>{log.symbol || '-'}</td>
              <td>
                <span
                  style={{
                    color:
                      log.action === 'APPROVE' || log.action === 'SUBMITTED'
                        ? 'var(--success)'
                        : log.action === 'REJECT' || log.action === 'STOP_LOSS'
                        ? 'var(--danger)'
                        : log.action === 'TAKE_PROFIT'
                        ? 'var(--success)'
                        : 'inherit',
                    fontWeight: 500,
                  }}
                >
                  {log.action}
                </span>
              </td>
              <td style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>{log.details}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};
