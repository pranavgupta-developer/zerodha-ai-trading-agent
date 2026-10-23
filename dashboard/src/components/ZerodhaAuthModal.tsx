import React from 'react';
import { Activity } from 'lucide-react';

interface ZerodhaAuthModalProps {
  show: boolean;
  loginUrl: string;
  tokenInput: string;
  submittingToken: boolean;
  onTokenChange: (val: string) => void;
  onClose: () => void;
  onSubmit: () => void;
}

export const ZerodhaAuthModal: React.FC<ZerodhaAuthModalProps> = ({
  show,
  loginUrl,
  tokenInput,
  submittingToken,
  onTokenChange,
  onClose,
  onSubmit,
}) => {
  if (!show) return null;

  return (
    <div
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        background: 'rgba(0,0,0,0.7)',
        backdropFilter: 'blur(6px)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 9999,
      }}
    >
      <div
        className="glass-panel"
        style={{
          width: '440px',
          padding: '24px',
          borderRadius: '12px',
          border: '1px solid var(--border)',
        }}
      >
        <h3 style={{ margin: '0 0 12px 0', display: 'flex', alignItems: 'center', gap: '8px' }}>
          <Activity size={20} color="var(--accent-primary)" />
          Connect Zerodha Kite Live Feed
        </h3>
        <p
          style={{
            fontSize: '13px',
            color: 'var(--text-secondary)',
            marginBottom: '16px',
            lineHeight: 1.5,
          }}
        >
          To stream genuine live market ticks and execute trades on Zerodha without simulation,
          authenticate your daily Kite session.
        </p>
        <div style={{ marginBottom: '16px' }}>
          <a
            href={loginUrl || 'http://localhost:8000/api/v1/auth/login?redirect=true'}
            target="_blank"
            rel="noreferrer"
            className="btn btn-primary"
            style={{
              display: 'block',
              textAlign: 'center',
              padding: '10px 16px',
              textDecoration: 'none',
              marginBottom: '12px',
            }}
          >
            1-Click Login via Zerodha Kite ↗
          </a>
          <div style={{ textAlign: 'center', fontSize: '11px', color: 'var(--text-muted)', margin: '8px 0' }}>
            — OR PASTE DAILY ACCESS TOKEN —
          </div>
          <input
            type="text"
            placeholder="Paste Access Token / Request Token..."
            value={tokenInput}
            onChange={(e) => onTokenChange(e.target.value)}
            style={{
              width: '100%',
              padding: '10px 12px',
              borderRadius: '6px',
              background: 'rgba(255,255,255,0.05)',
              border: '1px solid var(--border)',
              color: '#fff',
              fontFamily: 'JetBrains Mono, monospace',
              fontSize: '12px',
              boxSizing: 'border-box',
            }}
          />
        </div>
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px' }}>
          <button
            onClick={onClose}
            className="btn btn-outline"
            style={{ padding: '8px 16px', fontSize: '12px' }}
          >
            Cancel
          </button>
          <button
            onClick={onSubmit}
            disabled={!tokenInput.trim() || submittingToken}
            className="btn btn-primary"
            style={{ padding: '8px 16px', fontSize: '12px' }}
          >
            {submittingToken ? 'Verifying...' : 'Submit Token'}
          </button>
        </div>
      </div>
    </div>
  );
};
