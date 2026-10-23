import { useState } from 'react';
import { Search } from 'lucide-react';
import type { WatchlistItem } from '../types';

interface WatchlistMLProps {
  watchlist: WatchlistItem[];
}

export const WatchlistML: React.FC<WatchlistMLProps> = ({ watchlist }) => {
  const [searchTerm, setSearchTerm] = useState('');

  const filteredWatchlist = watchlist.filter((item) =>
    item.symbol.toLowerCase().includes(searchTerm.toLowerCase())
  );

  return (
    <div
      className="col-span-4 glass-panel animate-enter delay-2"
      style={{ padding: '24px', display: 'flex', flexDirection: 'column' }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
        <h2 style={{ margin: 0, fontSize: '18px' }}>Watchlist & ML Predictions</h2>
        <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>{watchlist.length} Tickers</span>
      </div>

      {/* Quick Search */}
      <div style={{ position: 'relative', marginBottom: '16px' }}>
        <Search
          size={14}
          color="var(--text-secondary)"
          style={{ position: 'absolute', left: '10px', top: '10px' }}
        />
        <input
          type="text"
          placeholder="Filter ticker (e.g. RELIANCE, TCS)..."
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
          style={{
            width: '100%',
            padding: '8px 12px 8px 32px',
            borderRadius: '6px',
            background: 'rgba(255,255,255,0.04)',
            border: '1px solid var(--border)',
            color: '#fff',
            fontSize: '12px',
            boxSizing: 'border-box',
          }}
        />
      </div>

      <div style={{ overflowY: 'auto', flex: 1, paddingRight: '4px', maxHeight: '420px' }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
          {filteredWatchlist.length === 0 && (
            <div style={{ color: 'var(--text-muted)', textAlign: 'center', padding: '20px' }}>
              {watchlist.length === 0 ? 'Loading watchlist...' : 'No matching symbols found.'}
            </div>
          )}
          {filteredWatchlist.map((item, idx) => (
            <div
              key={idx}
              style={{
                padding: '16px',
                background: 'rgba(255,255,255,0.02)',
                borderRadius: '8px',
                border: '1px solid var(--border)',
                borderLeft:
                  item.signal === 'BUY'
                    ? '3px solid var(--success)'
                    : item.signal === 'SELL'
                    ? '3px solid var(--danger)'
                    : '',
              }}
            >
              <div
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  marginBottom: '8px',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <span style={{ fontWeight: 600 }}>{item.symbol}</span>
                  {item.status === 'ZERODHA_LIVE' ? (
                    <span
                      style={{
                        fontSize: '10px',
                        background: 'rgba(16, 185, 129, 0.15)',
                        color: '#10b981',
                        padding: '1px 5px',
                        borderRadius: '4px',
                        fontWeight: 600,
                      }}
                    >
                      LIVE
                    </span>
                  ) : item.status === 'MARKET_CLOSED' || item.status === 'CLOSED' ? (
                    <span
                      style={{
                        fontSize: '10px',
                        background: 'rgba(148, 163, 184, 0.15)',
                        color: '#94a3b8',
                        padding: '1px 6px',
                        borderRadius: '4px',
                        fontWeight: 600,
                      }}
                      title="Market is closed (trading session: 09:30 - 15:30 IST)"
                    >
                      CLOSED
                    </span>
                  ) : (
                    <span
                      style={{
                        fontSize: '10px',
                        background: 'rgba(234, 179, 8, 0.15)',
                        color: '#eab308',
                        padding: '1px 5px',
                        borderRadius: '4px',
                      }}
                    >
                      AUTH REQ
                    </span>
                  )}
                </div>
                <span
                  style={{
                    fontFamily: 'JetBrains Mono',
                    color: (item.change || 0) >= 0 ? 'var(--success)' : 'var(--danger)',
                  }}
                >
                  {item.ltp > 0
                    ? `₹${item.ltp?.toLocaleString('en-IN', {
                        minimumFractionDigits: 2,
                        maximumFractionDigits: 2,
                      })}`
                    : '—'}
                </span>
              </div>
              <div
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  fontSize: '12px',
                  marginBottom: '4px',
                }}
              >
                <span style={{ color: 'var(--text-secondary)' }}>
                  ML Predict:{' '}
                  <span
                    style={{
                      color:
                        item.ml_predict && item.ml_predict.includes('BULLISH')
                          ? 'var(--success)'
                          : item.ml_predict && item.ml_predict.includes('BEARISH')
                          ? 'var(--danger)'
                          : 'var(--warning)',
                    }}
                  >
                    {item.ml_predict || item.signal}
                  </span>
                </span>
                <span style={{ color: 'var(--text-secondary)' }}>
                  Change:{' '}
                  {item.ltp > 0
                    ? `${(item.change || 0) >= 0 ? '+' : ''}${(item.change || 0).toFixed(2)}%`
                    : '—'}
                </span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px' }}>
                <span style={{ color: 'var(--text-secondary)' }}>
                  RSI: {item.rsi ? item.rsi.toFixed(1) : '—'}
                </span>
                <span style={{ color: 'var(--text-secondary)' }}>Signal: {item.signal}</span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};
