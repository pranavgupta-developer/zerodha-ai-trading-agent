// Real-time Data for the Dashboard
const mockWatchlist = [];
const mockPositions = [];
const mockHoldings = [];
const prevLtpMap = {};
window.isWebSocketConnected = false;

let currentRealizedPnl = 0.0;
let currentUnrealizedPnl = 0.0;

function formatCurrency(value) {
    if (isNaN(value) || value === null || value === undefined) return '₹0.00';
    return new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR' }).format(value);
}

function updatePnlSummary(realized = null, unrealized = null) {
    if (realized !== null && !isNaN(realized)) currentRealizedPnl = Number(realized);
    if (unrealized !== null && !isNaN(unrealized)) currentUnrealizedPnl = Number(unrealized);

    // Overall Day Profit represents value already gained by Buying and Selling of stocks (Realized)
    const totalDayProfit = currentRealizedPnl;

    const totalDayEl = document.getElementById('total-day-pnl-val');
    if (totalDayEl) {
        totalDayEl.textContent = formatCurrency(totalDayProfit);
        totalDayEl.className = `value ${totalDayProfit >= 0 ? 'positive' : 'negative'}`;
    }

    const realizedEl = document.getElementById('realized-pnl-val');
    if (realizedEl) {
        realizedEl.textContent = formatCurrency(currentRealizedPnl);
        realizedEl.className = `value ${currentRealizedPnl >= 0 ? 'positive' : 'negative'}`;
    }

    const unrealizedEl = document.getElementById('unrealized-pnl-val');
    if (unrealizedEl) {
        unrealizedEl.textContent = formatCurrency(currentUnrealizedPnl);
        unrealizedEl.className = `value ${currentUnrealizedPnl >= 0 ? 'positive' : 'negative'}`;
    }
}

function updateTime() {
    const el = document.getElementById('last-update-time');
    if (el) {
        const now = new Date();
        el.textContent = `Last update: ${now.toLocaleTimeString()}`;
    }
}

function renderWatchlist() {
    const tbody = document.querySelector('#watchlist-table tbody');
    if (!tbody) return;

    if (mockWatchlist.length === 0) {
        tbody.innerHTML = '<tr><td colspan="4" style="text-align: center; color: var(--text-muted);">Waiting for market data...</td></tr>';
        return;
    }

    // Maintain existing rows to avoid DOM destruction and flicker
    const existingRows = new Map();
    tbody.querySelectorAll('tr[data-symbol]').forEach(tr => {
        existingRows.set(tr.getAttribute('data-symbol'), tr);
    });

    // Remove placeholder row if present
    const emptyRow = tbody.querySelector('td[colspan]');
    if (emptyRow) tbody.innerHTML = '';

    mockWatchlist.forEach(item => {
        const sym = item.symbol;
        const prevPrice = prevLtpMap[sym];
        let flashClass = '';
        if (prevPrice !== undefined) {
            if (item.ltp > prevPrice) flashClass = 'flash-up';
            else if (item.ltp < prevPrice) flashClass = 'flash-down';
        }
        prevLtpMap[sym] = item.ltp;

        const changeClass = item.change >= 0 ? 'positive' : 'negative';
        const changePrefix = item.change >= 0 ? '+' : '';
        const signalClass = `signal-${(item.signal || 'hold').toLowerCase()}`;

        // Calculate latencies
        const frontend_ts = Date.now() / 1000;
        const source_latency = window.current_backend_ts && item.source_ts ? (window.current_backend_ts - item.source_ts).toFixed(3) : "0.000";
        const total_latency = item.source_ts ? (frontend_ts - item.source_ts).toFixed(3) : "0.000";

        let tr = existingRows.get(sym);
        if (!tr) {
            tr = document.createElement('tr');
            tr.setAttribute('data-symbol', sym);
            tbody.appendChild(tr);
        }

        tr.className = flashClass;
        tr.innerHTML = `
            <td style="font-weight: 600;">
                ${item.symbol}
                <div style="font-size: 0.65rem; color: var(--text-muted); font-weight: normal; margin-top: 4px;">
                    Latency: src->backend ${source_latency}s | src->ui ${total_latency}s
                </div>
            </td>
            <td style="font-variant-numeric: tabular-nums;">₹${Number(item.ltp).toFixed(2)}</td>
            <td class="${changeClass}" style="font-variant-numeric: tabular-nums;">${changePrefix}${Number(item.change).toFixed(2)}%</td>
            <td><span class="signal-badge ${signalClass}">${item.signal || 'HOLD'}</span></td>
        `;
    });
}

function renderPositions() {
    const tbody = document.querySelector('#positions-table tbody');
    if (!tbody) return;

    if (mockPositions.length === 0) {
        tbody.innerHTML = '<tr><td colspan="6" style="text-align: center; color: var(--text-muted);">No open positions.</td></tr>';
        updatePnlSummary(null, 0.0);
        return;
    }

    let totalUnrealized = 0;
    const currentSymbols = new Set(mockPositions.map(p => p.symbol));
    tbody.querySelectorAll('tr[data-symbol]').forEach(tr => {
        const sym = tr.getAttribute('data-symbol');
        if (!currentSymbols.has(sym)) tr.remove();
    });

    const existingRows = new Map();
    tbody.querySelectorAll('tr[data-symbol]').forEach(tr => {
        existingRows.set(tr.getAttribute('data-symbol'), tr);
    });

    const emptyRow = tbody.querySelector('td[colspan]');
    if (emptyRow) tbody.innerHTML = '';

    mockPositions.forEach(pos => {
        const qty = Math.abs(Number(pos.qty || 0));
        const pnl = pos.pnl !== undefined ? pos.pnl : ((pos.ltp - pos.avg) * qty);
        totalUnrealized += pnl;

        const pnlClass = pnl >= 0 ? 'positive' : 'negative';
        const pnlPrefix = pnl >= 0 ? '+' : '';

        const prevPrice = prevLtpMap['pos_' + pos.symbol];
        let flashClass = '';
        if (prevPrice !== undefined) {
            if (pos.ltp > prevPrice) flashClass = 'flash-up';
            else if (pos.ltp < prevPrice) flashClass = 'flash-down';
        }
        prevLtpMap['pos_' + pos.symbol] = pos.ltp;

        let tr = existingRows.get(pos.symbol);
        if (!tr) {
            tr = document.createElement('tr');
            tr.setAttribute('data-symbol', pos.symbol);
            tbody.appendChild(tr);
        }

        tr.className = flashClass;
        tr.innerHTML = `
            <td style="font-weight: 600;">${pos.symbol}</td>
            <td style="font-variant-numeric: tabular-nums;">${qty}</td>
            <td style="font-variant-numeric: tabular-nums;">₹${Number(pos.avg).toFixed(2)}</td>
            <td style="font-variant-numeric: tabular-nums;">₹${Number(pos.ltp).toFixed(2)}</td>
            <td class="${pnlClass}" style="font-variant-numeric: tabular-nums;">${pnlPrefix}₹${Math.abs(pnl).toFixed(2)}</td>
            <td><button class="btn btn-reject" style="padding: 4px 8px; font-size: 0.8rem;" onclick="closePosition('${pos.symbol}', ${qty})">Close</button></td>
        `;
    });

    // Update summary card with live unrealized P&L and total day profit
    updatePnlSummary(null, totalUnrealized);
}

function renderHoldings() {
    const tbody = document.querySelector('#holdings-table tbody');
    if (!tbody) return;

    if (mockHoldings.length === 0) {
        tbody.innerHTML = '<tr><td colspan="5" style="text-align: center; color: var(--text-muted);">No holdings in portfolio.</td></tr>';
        return;
    }

    const existingRows = new Map();
    tbody.querySelectorAll('tr[data-symbol]').forEach(tr => {
        existingRows.set(tr.getAttribute('data-symbol'), tr);
    });

    const emptyRow = tbody.querySelector('td[colspan]');
    if (emptyRow) tbody.innerHTML = '';

    mockHoldings.forEach(hold => {
        const symbol = hold.tradingsymbol || hold.symbol;
        const qty = hold.quantity || hold.qty;
        const avg = hold.average_price || hold.avg || 0;
        const ltp = hold.last_price || hold.ltp || hold.price || avg;
        const pnl = hold.pnl !== undefined ? hold.pnl : ((ltp - avg) * qty);

        const pnlClass = pnl >= 0 ? 'positive' : 'negative';
        const pnlPrefix = pnl >= 0 ? '+' : '';

        let tr = existingRows.get(symbol);
        if (!tr) {
            tr = document.createElement('tr');
            tr.setAttribute('data-symbol', symbol);
            tbody.appendChild(tr);
        }

        tr.innerHTML = `
            <td style="font-weight: 600;">${symbol}</td>
            <td style="font-variant-numeric: tabular-nums;">${qty}</td>
            <td style="font-variant-numeric: tabular-nums;">₹${Number(avg).toFixed(2)}</td>
            <td style="font-variant-numeric: tabular-nums;">₹${Number(ltp).toFixed(2)}</td>
            <td class="${pnlClass}" style="font-variant-numeric: tabular-nums;">${pnlPrefix}₹${Math.abs(pnl).toFixed(2)}</td>
        `;
    });
}

function handleMarketUpdate(data) {
    if (data.watchlist && data.watchlist.length > 0) {
        mockWatchlist.length = 0;
        mockWatchlist.push(...data.watchlist);
    }
    
    if (data.positions !== undefined) {
        mockPositions.length = 0;
        mockPositions.push(...data.positions);
    }
    
    if (data.holdings !== undefined) {
        mockHoldings.length = 0;
        mockHoldings.push(...data.holdings);
    }
    
    if (data.account_stats) {
        const marginEl = document.getElementById('margin-val');
        if (marginEl) marginEl.textContent = formatCurrency(data.account_stats.margin);
        
        const realized = Number(data.account_stats.realized_pnl || 0);
        const unrealized = Number(data.account_stats.unrealized_pnl || 0);
        updatePnlSummary(realized, unrealized);
    }

    if (data.emergency_stop_active !== undefined) {
        updateEmergencyStopUI(data.emergency_stop_active);
    }

    if (data.reconciliation) {
        const banner = document.getElementById('reconciliation-alert-banner');
        if (banner) {
            if (!data.reconciliation.is_synced && data.reconciliation.discrepancies > 0) {
                banner.style.display = 'block';
                const msgEl = document.getElementById('reconcile-discrepancy-msg');
                if (msgEl) msgEl.textContent = `(${data.reconciliation.discrepancies} mismatches detected)`;
            } else {
                banner.style.display = 'none';
            }
        }
    }

    if (data.ml_metrics) {
        const mlAccEl = document.getElementById('ml-accuracy-val');
        if (mlAccEl) {
            const accPct = (data.ml_metrics.rolling_accuracy_20 * 100).toFixed(1);
            mlAccEl.textContent = data.ml_metrics.total_predictions > 0 ? `${accPct}%` : '--%';
        }
        const driftBadge = document.getElementById('ml-drift-badge');
        if (driftBadge) {
            if (data.ml_metrics.drift_detected) {
                driftBadge.textContent = '⚠️ DRIFT DETECTED';
                driftBadge.style.color = '#ef4444';
            } else {
                driftBadge.textContent = 'Drift: STABLE';
                driftBadge.style.color = '#10b981';
            }
        }
    }

    if (data.paper_validation) {
        const verdictEl = document.getElementById('paper-verdict-val');
        if (verdictEl) {
            verdictEl.textContent = data.paper_validation.verdict || 'IN PROGRESS';
            verdictEl.className = `value ${data.paper_validation.verdict === 'PASSED' ? 'positive' : ''}`;
        }
        const sharpeEl = document.getElementById('paper-sharpe-val');
        if (sharpeEl) {
            sharpeEl.textContent = `Sharpe: ${data.paper_validation.sharpe_ratio} | Day ${data.paper_validation.days_completed}`;
        }
    }
    
    if (data.audit_chain) {
        const badge = document.getElementById('audit-chain-badge');
        if (badge) {
            if (data.audit_chain.is_valid) {
                badge.textContent = `🔒 SHA-256 Chain Verified (${data.audit_chain.last_hash})`;
                badge.style.color = '#10b981';
                badge.style.borderColor = '#10b981';
                badge.style.background = 'rgba(16, 185, 129, 0.2)';
            } else {
                badge.textContent = '⚠️ Chain Tamper Detected';
                badge.style.color = '#ef4444';
                badge.style.borderColor = '#ef4444';
                badge.style.background = 'rgba(239, 68, 68, 0.2)';
            }
        }
    }
    
    if (data.risk_metrics) {
        updateRiskMetricsUI(data.risk_metrics);
    }
    
    if (data.model_status) {
        updateModelRegistryUI(data.model_status);
    }

    if (data.unified_risk) {
        updateUnifiedRiskUI(data.unified_risk);
    }
    
    window.current_backend_ts = data.backend_ts;
    
    if (data.autonomous_trades && Array.isArray(data.autonomous_trades)) {
        data.autonomous_trades.forEach(t => renderAutonomousTrade(t));
    }
    
    renderWatchlist();
    renderPositions();
    renderHoldings();
    updateTime();
}


function appendAuditLog(log) {
    const tbody = document.querySelector('#audit-log-table tbody');
    if (!tbody) return;

    const emptyRow = tbody.querySelector('td[colspan]');
    if (emptyRow) tbody.innerHTML = '';

    const tr = document.createElement('tr');
    tr.className = 'new-row-highlight';
    const date = new Date(log.timestamp.endsWith('Z') ? log.timestamp : log.timestamp + 'Z');

    let eventTypeClass = '';
    if (log.event_type === 'SIGNAL') eventTypeClass = 'style="color: var(--accent-blue);"';
    else if (log.event_type === 'RISK_DECISION') eventTypeClass = 'style="color: var(--warning);"';
    else if (log.event_type === 'ORDER_EVENT') eventTypeClass = 'style="color: var(--positive);"';
    else if (log.event_type === 'USER_DECISION') eventTypeClass = 'style="color: var(--text-main);"';

    const hashStr = log.chain_hash ? `<div style="font-size: 0.65rem; color: #6b7280; font-family: monospace; margin-top: 3px;">🔗 SHA-256: ${log.chain_hash.substring(0, 16)}...</div>` : '';

    tr.innerHTML = `
        <td style="font-size: 0.75rem; color: var(--text-muted);">${date.toLocaleTimeString()}</td>
        <td ${eventTypeClass}>${log.event_type}</td>
        <td style="font-size: 0.75rem;">${log.trade_id || '-'}</td>
        <td style="font-weight: 600;">${log.symbol || '-'}</td>
        <td>${log.action || '-'}</td>
        <td style="font-size: 0.8rem; color: var(--text-muted);">${log.details || '-'}${hashStr}</td>
    `;
    tbody.insertBefore(tr, tbody.firstChild);
}

function renderAutonomousTrade(trade) {
    const tbody = document.querySelector('#candidate-trades-table tbody');
    if (!tbody) return;
    const noCandidatesRow = document.getElementById('no-candidates-row');
    if (noCandidatesRow) {
        noCandidatesRow.remove();
    }
    
    // Avoid duplicate rows
    if (document.getElementById(`trade-${trade.id}`)) return;

    const tr = document.createElement('tr');
    tr.id = `trade-${trade.id}`;
    tr.className = 'new-row-highlight';
    
    const actionClass = trade.action === 'BUY' ? 'signal-buy' : 'signal-sell';
    const qty = trade.qty || 1;
    const capitalStr = trade.allocated_capital ? `₹${Number(trade.allocated_capital).toLocaleString('en-IN')}` : '-';
    
    tr.innerHTML = `
        <td style="font-weight: 600;">${trade.symbol}</td>
        <td><span class="signal-badge ${actionClass}">${trade.action}</span></td>
        <td style="font-variant-numeric: tabular-nums;">₹${Number(trade.price).toFixed(2)}</td>
        <td style="font-variant-numeric: tabular-nums;">${qty} sh (${capitalStr})</td>
        <td class="ai-reasoning">
            ${trade.reasoning || '-'}
            ${trade.sizing_rationale ? `<div style="font-size: 0.7rem; color: var(--accent-blue); margin-top: 2px;">${trade.sizing_rationale}</div>` : ''}
        </td>
        <td>
            <span class="signal-badge signal-buy" style="font-size: 0.7rem; padding: 2px 6px;">⚡ AUTO-EXECUTED</span>
        </td>
    `;
    tbody.insertBefore(tr, tbody.firstChild);
}

function setBrokerStatus(isOnline, text = "Kite API Connected") {
    const dot = document.getElementById('broker-status-dot');
    const textEl = document.getElementById('broker-status-text');
    if (dot) {
        dot.className = `status-dot ${isOnline ? 'online' : 'offline'}`;
    }
    if (textEl) {
        textEl.textContent = text;
    }
}

function setupWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/candidate-trades`;
    const ws = new WebSocket(wsUrl);
    
    let pingInterval = null;

    ws.onopen = () => {
        window.isWebSocketConnected = true;
        setBrokerStatus(true, "Live WebSocket Stream (1s)");
        pingInterval = setInterval(() => {
            if (ws.readyState === WebSocket.OPEN) {
                ws.send("ping");
            }
        }, 10000);
    };

    ws.onmessage = (event) => {
        try {
            const data = JSON.parse(event.data);
            if (data.type === 'market_update') {
                handleMarketUpdate(data);
            } else if (data.type === 'autonomous_trade') {
                renderAutonomousTrade(data.trade);
            } else if (data.type === 'candidate_trade') {
                renderAutonomousTrade(data.candidate);
            } else if (data.type === 'audit_log') {
                appendAuditLog(data.log);
            }
        } catch (e) {
            console.error("Failed to parse websocket message", e);
        }
    };
    
    ws.onclose = () => {
        window.isWebSocketConnected = false;
        setBrokerStatus(false, "Reconnecting...");
        if (pingInterval) clearInterval(pingInterval);
        setTimeout(setupWebSocket, 1500);
    };

    ws.onerror = () => {
        window.isWebSocketConnected = false;
    };
}

async function fetchPortfolio() {
    try {
        const response = await fetch('/api/v1/portfolio');
        if (response.ok) {
            const data = await response.json();
            handleMarketUpdate(data);
        }
    } catch (e) {
        // Fallback quiet
    }
}

async function handleTradeAction(tradeId, action) {
    try {
        const response = await fetch('/api/v1/trades/action', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ trade_id: tradeId, action: action })
        });
        
        if (response.ok) {
            const tr = document.getElementById(`trade-${tradeId}`);
            if (tr) {
                const td = tr.querySelector('td:last-child');
                td.innerHTML = `<span class="badge ${action === 'APPROVE' ? 'mode-dry' : ''}" style="${action === 'APPROVE' ? 'background-color: var(--positive);' : 'background-color: var(--negative); color: white;'}">${action}D</span>`;
            }
            // Instantly sync portfolio state
            fetchPortfolio();
        } else {
            const errData = await response.json();
            alert(`Trade action failed: ${errData.detail || 'Unknown error'}`);
        }
    } catch (error) {
        console.error("Error submitting trade action:", error);
    }
}

async function closePosition(symbol, qty) {
    if (!confirm(`Are you sure you want to close position for ${symbol}?`)) return;
    
    try {
        const response = await fetch('/api/v1/trades/close', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ symbol: symbol, quantity: qty })
        });
        
        const data = await response.json();
        if (response.ok) {
            alert(`Position closing order submitted! Order ID: ${data.broker_order_id}`);
            // Instantly sync portfolio state
            fetchPortfolio();
        } else {
            alert(`Failed to close position: ${data.detail || 'Unknown error'}`);
        }
    } catch (error) {
        console.error("Error closing position:", error);
        alert("An error occurred while trying to close the position.");
    }
}

async function toggleEmergencyStop() {
    try {
        const response = await fetch('/api/v1/system/emergency-stop', { method: 'POST' });
        const data = await response.json();
        updateEmergencyStopUI(data.emergency_stop_active);
    } catch (e) {
        console.error(e);
    }
}

async function triggerManualReconciliation() {
    const btn = document.getElementById('btn-reconcile');
    if (btn) btn.textContent = '🔄 Reconciling...';
    try {
        const response = await fetch('/api/v1/system/reconcile', { method: 'POST' });
        const data = await response.json();
        const banner = document.getElementById('reconciliation-alert-banner');
        if (data.report && !data.report.is_synced && data.report.total_discrepancies > 0) {
            if (banner) {
                banner.style.display = 'block';
                const msgEl = document.getElementById('reconcile-discrepancy-msg');
                if (msgEl) msgEl.textContent = `(${data.report.total_discrepancies} mismatches detected - auto-synced: ${data.report.auto_resolved})`;
            }
        } else {
            if (banner) banner.style.display = 'none';
        }
        if (btn) btn.textContent = '✅ Synced';
        setTimeout(() => { if (btn) btn.textContent = '🔄 Reconcile Now'; }, 2000);
    } catch (e) {
        console.error('Failed to trigger reconciliation:', e);
        if (btn) btn.textContent = '❌ Failed';
        setTimeout(() => { if (btn) btn.textContent = '🔄 Reconcile Now'; }, 2000);
    }
}

function updateEmergencyStopUI(isActive) {
    const btn = document.getElementById('btn-emergency-stop');
    if (!btn) return;
    if (isActive) {
        btn.innerHTML = '🛑 SYSTEM HALTED (RESUME)';
        btn.style.backgroundColor = '#000';
        btn.style.color = 'var(--negative)';
        btn.style.border = '1px solid var(--negative)';
    } else {
        btn.innerHTML = '🚨 EMERGENCY STOP';
        btn.style.backgroundColor = 'var(--negative)';
        btn.style.color = '#fff';
    }
}

async function showPaperReportModal() {
    const modal = document.getElementById('paper-report-modal');
    const content = document.getElementById('paper-report-content');
    if (modal) modal.style.display = 'flex';
    if (content) content.textContent = 'Generating validation report...';
    
    try {
        const res = await fetch('/api/v1/system/paper-report/markdown');
        const data = await res.json();
        if (content) content.textContent = data.markdown || 'No report available.';
    } catch (e) {
        if (content) content.textContent = 'Failed to load report: ' + e;
    }
}

function closePaperReportModal() {
    const modal = document.getElementById('paper-report-modal');
    if (modal) modal.style.display = 'none';
}

async function verifyAuditChain() {
    const badge = document.getElementById('audit-chain-badge');
    if (badge) badge.textContent = '🔄 Verifying...';
    try {
        const res = await fetch('/api/v1/system/audit/verify');
        const data = await res.json();
        if (data.is_valid) {
            if (badge) {
                badge.textContent = `🔒 Verified (${data.total_events} blocks)`;
                badge.style.color = '#10b981';
                badge.style.borderColor = '#10b981';
                badge.style.background = 'rgba(16, 185, 129, 0.2)';
            }
            alert(`AUDIT CHAIN INTEGRITY: 100% Cryptographically Verified.\nTotal Immutable Blocks: ${data.total_events}\nLatest Block Hash: ${data.last_hash}`);
        } else {
            if (badge) {
                badge.textContent = `⚠️ Tamper Detected (L${data.tampered_at_line})`;
                badge.style.color = '#ef4444';
                badge.style.borderColor = '#ef4444';
                badge.style.background = 'rgba(239, 68, 68, 0.2)';
            }
            alert(`CRITICAL AUDIT TAMPERING DETECTED!\n${data.message}`);
        }
    } catch (e) {
        if (badge) badge.textContent = '⚠️ Verify Error';
        console.error(e);
    }
}

async function fetchSystemStatus() {
    try {
        const response = await fetch('/api/v1/system/status');
        const data = await response.json();
        updateEmergencyStopUI(data.emergency_stop_active);
        
        const badge = document.querySelector('.logo .badge');
        if (badge && data.trading_mode) {
            badge.textContent = data.trading_mode;
            if (data.trading_mode === 'LIVE') {
                badge.className = 'badge mode-live';
            } else {
                badge.className = 'badge mode-dry';
            }
        }
    } catch (e) {
        console.error(e);
    }
}

async function fetchAuditLogs() {
    try {
        const response = await fetch('/api/v1/audit-logs');
        const data = await response.json();
        const tbody = document.querySelector('#audit-log-table tbody');
        if (!tbody) return;
        
        if (data.logs.length === 0) {
            tbody.innerHTML = '<tr><td colspan="6" style="text-align: center; color: var(--text-muted);">No audit logs found.</td></tr>';
            return;
        }
        
        tbody.innerHTML = '';
        data.logs.forEach(log => {
            const tr = document.createElement('tr');
            const date = new Date(log.timestamp.endsWith('Z') ? log.timestamp : log.timestamp + 'Z');
            
            let eventTypeClass = '';
            if (log.event_type === 'SIGNAL') eventTypeClass = 'style="color: var(--accent-blue);"';
            else if (log.event_type === 'RISK_DECISION') eventTypeClass = 'style="color: var(--warning);"';
            else if (log.event_type === 'ORDER_EVENT') eventTypeClass = 'style="color: var(--positive);"';
            else if (log.event_type === 'USER_DECISION') eventTypeClass = 'style="color: var(--text-main);"';

            tr.innerHTML = `
                <td style="font-size: 0.75rem; color: var(--text-muted);">${date.toLocaleTimeString()}</td>
                <td ${eventTypeClass}>${log.event_type}</td>
                <td style="font-size: 0.75rem;">${log.trade_id || '-'}</td>
                <td style="font-weight: 600;">${log.symbol || '-'}</td>
                <td>${log.action || '-'}</td>
                <td style="font-size: 0.8rem; color: var(--text-muted);">${log.details || '-'}</td>
            `;
            tbody.appendChild(tr);
        });
    } catch (e) {
        console.error("Failed to fetch audit logs:", e);
    }
}

// ==========================================
// Institutional Risk & Sector UI
// ==========================================

function updateRiskMetricsUI(riskMetrics) {
    if (!riskMetrics) return;
    
    const container = document.getElementById('sector-bars-container');
    const compStatus = document.getElementById('sector-compliance-status');
    const sectorBadge = document.getElementById('sector-risk-badge');
    
    if (riskMetrics.sectors && riskMetrics.sectors.sectors) {
        const sectors = riskMetrics.sectors.sectors;
        const keys = Object.keys(sectors);
        const maxCapPct = (riskMetrics.max_sector_pct || 0.35) * 100;
        
        if (sectorBadge) {
            sectorBadge.textContent = `Sector Cap: ${maxCapPct.toFixed(0)}% Max`;
        }
        
        if (keys.length === 0) {
            if (container) container.innerHTML = '<div style="font-size: 0.8rem; color: var(--text-muted);">No open positions. Capital fully diversified.</div>';
            if (compStatus) {
                compStatus.textContent = 'COMPLIANT';
                compStatus.style.color = '#10b981';
            }
        } else {
            let hasBreach = false;
            let html = '';
            keys.forEach(sec => {
                const info = sectors[sec];
                const pct = (info.pct * 100);
                const isBreached = info.breached || pct > maxCapPct;
                if (isBreached) hasBreach = true;
                
                const barColor = isBreached ? '#ef4444' : (pct > maxCapPct * 0.75 ? '#f59e0b' : '#10b981');
                const barWidth = Math.min(100, Math.max(5, (pct / maxCapPct) * 100));
                
                html += `
                    <div style="font-size: 0.8rem;">
                        <div style="display: flex; justify-content: space-between; margin-bottom: 2px;">
                            <span><strong style="color: white;">${sec}</strong> (${info.symbols.join(', ')})</span>
                            <span style="color: ${barColor}; font-weight: 600;">${pct.toFixed(1)}% / ${maxCapPct.toFixed(0)}%</span>
                        </div>
                        <div style="background: rgba(255,255,255,0.1); height: 6px; border-radius: 3px; overflow: hidden;">
                            <div style="background: ${barColor}; width: ${barWidth}%; height: 100%; border-radius: 3px; transition: width 0.3s ease;"></div>
                        </div>
                    </div>
                `;
            });
            if (container) container.innerHTML = html;
            if (compStatus) {
                if (hasBreach) {
                    compStatus.textContent = 'CAP BREACHED';
                    compStatus.style.color = '#ef4444';
                } else {
                    compStatus.textContent = 'COMPLIANT';
                    compStatus.style.color = '#10b981';
                }
            }
        }
    }
}

async function fetchRiskVarMetrics() {
    try {
        const resp = await fetch('/api/v1/system/risk/var?confidence=0.95');
        if (resp.ok) {
            const data = await resp.json();
            const paramVarEl = document.getElementById('param-var-val');
            const paramCvarEl = document.getElementById('param-cvar-val');
            const histVarEl = document.getElementById('hist-var-val');
            const histCvarEl = document.getElementById('hist-cvar-val');
            const badge = document.getElementById('var-risk-badge');
            
            if (paramVarEl && data.parametric) {
                paramVarEl.textContent = `${(data.parametric.var_pct * 100).toFixed(2)}%`;
            }
            if (paramCvarEl && data.parametric) {
                paramCvarEl.textContent = `${(data.parametric.cvar_pct * 100).toFixed(2)}%`;
            }
            if (histVarEl && data.historical) {
                histVarEl.textContent = `${(data.historical.var_pct * 100).toFixed(2)}%`;
            }
            if (histCvarEl && data.historical) {
                histCvarEl.textContent = `${(data.historical.cvar_pct * 100).toFixed(2)}%`;
            }
            if (badge) {
                if (data.is_safe) {
                    badge.textContent = `🛡️ 1-Day 95% VaR: Safe (< ${(data.max_var_pct * 100).toFixed(0)}%)`;
                    badge.style.color = '#10b981';
                    badge.style.borderColor = '#10b981';
                    badge.style.background = 'rgba(16, 185, 129, 0.2)';
                } else {
                    badge.textContent = '⚠️ 1-Day VaR Limit Warning';
                    badge.style.color = '#ef4444';
                    badge.style.borderColor = '#ef4444';
                    badge.style.background = 'rgba(239, 68, 68, 0.2)';
                }
            }
        }
    } catch (e) {
        // silent fallback
    }
}

async function fetchUnifiedRiskStatus() {
    try {
        const resp = await fetch('/api/v1/system/risk-center/status');
        if (resp.ok) {
            const json = await resp.json();
            if (json.data) updateUnifiedRiskUI(json.data);
        }
    } catch (e) {}
}

async function fetchModelsStatus() {
    try {
        const resp = await fetch('/api/v1/system/models/status');
        if (resp.ok) {
            const json = await resp.json();
            if (json.data) updateModelRegistryUI(json.data);
        }
    } catch (e) {}
}

function updateUnifiedRiskUI(riskData) {
    if (!riskData) return;
    const state = riskData.overall_state || 'SAFE';
    
    // Top Banner
    const banner = document.getElementById('unified-risk-banner');
    const badge = document.getElementById('risk-center-status-badge');
    const summary = document.getElementById('risk-center-summary-text');
    const resumeBtn = document.getElementById('btn-resume-system');
    const statePill = document.getElementById('control-center-state-pill');

    if (banner && badge && summary) {
        summary.textContent = riskData.summary || '';
        if (state === 'SAFE') {
            banner.style.background = 'rgba(16, 185, 129, 0.12)';
            banner.style.borderColor = '#10b981';
            badge.style.background = '#10b981';
            badge.style.color = '#111827';
            badge.textContent = '🟢 SYSTEM SAFE';
            if (resumeBtn) resumeBtn.style.display = 'none';
        } else if (state === 'WARNING') {
            banner.style.background = 'rgba(245, 158, 11, 0.15)';
            banner.style.borderColor = '#f59e0b';
            badge.style.background = '#f59e0b';
            badge.style.color = '#111827';
            badge.textContent = '🟡 SYSTEM WARNING';
            if (resumeBtn) resumeBtn.style.display = 'none';
        } else if (state === 'HALTED') {
            banner.style.background = 'rgba(220, 38, 38, 0.25)';
            banner.style.borderColor = '#dc2626';
            badge.style.background = '#dc2626';
            badge.style.color = '#ffffff';
            badge.textContent = '🔴 SYSTEM HALTED';
            if (resumeBtn) resumeBtn.style.display = 'inline-block';
        }
    }

    if (statePill) {
        statePill.textContent = `STATUS: ${state}`;
        if (state === 'SAFE') {
            statePill.style.color = '#10b981';
            statePill.style.borderColor = '#10b981';
            statePill.style.background = 'rgba(16, 185, 129, 0.2)';
        } else if (state === 'WARNING') {
            statePill.style.color = '#f59e0b';
            statePill.style.borderColor = '#f59e0b';
            statePill.style.background = 'rgba(245, 158, 11, 0.2)';
        } else {
            statePill.style.color = '#ef4444';
            statePill.style.borderColor = '#ef4444';
            statePill.style.background = 'rgba(239, 68, 68, 0.2)';
        }
    }

    // Subsystems
    const sub = riskData.subsystems || {};
    
    // 1. Audit Chain
    if (sub.audit_chain) {
        const auditStatusEl = document.getElementById('cc-audit-status');
        const auditRecordsEl = document.getElementById('cc-audit-records');
        if (auditStatusEl) {
            auditStatusEl.textContent = sub.audit_chain.status;
            auditStatusEl.style.color = sub.audit_chain.is_valid ? '#10b981' : '#ef4444';
        }
        if (auditRecordsEl) {
            auditRecordsEl.textContent = `${sub.audit_chain.total_events || 0} events`;
        }
    }

    // 2. Broker Sync
    if (sub.reconciliation) {
        const recStatusEl = document.getElementById('cc-reconcile-status');
        const recDetailsEl = document.getElementById('cc-reconcile-details');
        const quarEl = document.getElementById('cc-quarantine-count');
        if (recStatusEl) {
            recStatusEl.textContent = sub.reconciliation.status;
            recStatusEl.style.color = sub.reconciliation.status === 'SYNCHRONIZED' ? '#10b981' : '#f59e0b';
        }
        if (recDetailsEl) {
            recDetailsEl.textContent = `${sub.reconciliation.discrepancies || 0} Mismatches`;
        }
        if (quarEl) quarEl.textContent = sub.reconciliation.quarantined || 0;
    }

    // 3. Anomaly Sentinel
    if (sub.anomaly_sentinel) {
        const anomStatusEl = document.getElementById('cc-anomaly-status');
        const anomDetailsEl = document.getElementById('cc-anomaly-details');
        if (anomStatusEl) {
            anomStatusEl.textContent = sub.anomaly_sentinel.status;
            anomStatusEl.style.color = sub.anomaly_sentinel.is_halted ? '#ef4444' : (sub.anomaly_sentinel.warning_count > 0 ? '#f59e0b' : '#10b981');
        }
        if (anomDetailsEl) {
            anomDetailsEl.textContent = `${sub.anomaly_sentinel.critical_count || 0} Critical`;
        }
    }

    // 4. Portfolio Risk
    if (sub.portfolio_risk) {
        const portStatusEl = document.getElementById('cc-portfolio-status');
        const portMaxSecEl = document.getElementById('cc-portfolio-max-sec');
        if (portStatusEl) {
            portStatusEl.textContent = sub.portfolio_risk.status;
            portStatusEl.style.color = sub.portfolio_risk.status === 'COMPLIANT' ? '#10b981' : '#f59e0b';
        }
        if (portMaxSecEl) {
            portMaxSecEl.textContent = `Max Sec: ${sub.portfolio_risk.max_sector_pct || 0}%`;
        }
    }

    // 5. Model Registry
    if (sub.model_registry) {
        const modStatusEl = document.getElementById('cc-model-status');
        const champAccEl = document.getElementById('cc-champ-acc');
        const shadowLeadEl = document.getElementById('cc-shadow-delta');
        if (modStatusEl) {
            modStatusEl.textContent = sub.model_registry.status;
            modStatusEl.style.color = sub.model_registry.status === 'ACTIVE' ? '#10b981' : '#f59e0b';
        }
        if (champAccEl) {
            champAccEl.textContent = `Acc: ${(sub.model_registry.champion_accuracy || 0).toFixed(1)}%`;
        }
        if (shadowLeadEl) {
            const delta = sub.model_registry.win_delta || 0;
            shadowLeadEl.textContent = `${delta >= 0 ? '+' : ''}${delta.toFixed(1)}%`;
            shadowLeadEl.style.color = delta >= 5.0 ? '#10b981' : 'var(--text-muted)';
        }
    }

    // 6. Kill Switch
    if (sub.kill_switch) {
        const killStatusEl = document.getElementById('cc-killswitch-status');
        const killStateEl = document.getElementById('cc-killswitch-state');
        if (killStatusEl) {
            killStatusEl.textContent = sub.kill_switch.is_active ? 'ENGAGED' : 'ARMED';
            killStatusEl.style.color = sub.kill_switch.is_active ? '#ef4444' : '#10b981';
        }
        if (killStateEl) {
            killStateEl.textContent = sub.kill_switch.is_active ? 'HALTED' : 'STANDBY';
            killStateEl.style.color = sub.kill_switch.is_active ? '#ef4444' : '#10b981';
        }
    }

    // Reasons list
    const reasonsContainer = document.getElementById('cc-reasons-container');
    const reasonsList = document.getElementById('cc-reasons-list');
    if (reasonsContainer && reasonsList) {
        if (riskData.reasons && riskData.reasons.length > 0) {
            reasonsContainer.style.display = 'block';
            reasonsList.innerHTML = riskData.reasons.map(r => `<li>${r}</li>`).join('');
        } else {
            reasonsContainer.style.display = 'none';
            reasonsList.innerHTML = '';
        }
    }
}

function updateModelRegistryUI(modelData) {
    if (!modelData) return;
    const champ = modelData.champion;
    const chall = modelData.challenger;
    const badge = document.getElementById('model-registry-badge');

    if (champ) {
        const nameEl = document.getElementById('champ-model-name');
        const verEl = document.getElementById('champ-version-badge');
        const accEl = document.getElementById('champ-acc-val');
        const evalsEl = document.getElementById('champ-evals-val');
        if (nameEl) nameEl.textContent = champ.name || champ.model_id;
        if (verEl) verEl.textContent = champ.version || 'v1.0';
        if (accEl) {
            const acc = (champ.rolling_accuracy || 0).toFixed(1);
            accEl.textContent = `${acc}%`;
            accEl.style.color = champ.rolling_accuracy >= 55.0 ? '#10b981' : (champ.rolling_accuracy >= 45.0 ? '#f59e0b' : '#ef4444');
        }
        if (evalsEl) evalsEl.textContent = champ.total_evaluations || 0;
    }

    if (chall) {
        const nameEl = document.getElementById('chall-model-name');
        const verEl = document.getElementById('chall-version-badge');
        const accEl = document.getElementById('chall-acc-val');
        const deltaEl = document.getElementById('chall-delta-val');
        const promoBtn = document.getElementById('btn-promote-challenger');
        if (nameEl) nameEl.textContent = chall.name || chall.model_id;
        if (verEl) verEl.textContent = chall.version || 'v2.0';
        if (accEl) {
            const acc = (chall.rolling_accuracy || 0).toFixed(1);
            accEl.textContent = `${acc}%`;
        }
        if (deltaEl) {
            const delta = chall.shadow_win_delta || 0;
            deltaEl.textContent = `${delta >= 0 ? '+' : ''}${delta.toFixed(1)}%`;
            deltaEl.style.color = delta >= 5.0 ? '#10b981' : (delta > 0 ? '#f59e0b' : 'white');
        }
        if (promoBtn) {
            if (modelData.auto_promote_eligible) {
                promoBtn.style.background = '#10b981';
                promoBtn.textContent = '⚡ Promote (+5% Lead)';
            } else {
                promoBtn.style.background = '#2563eb';
                promoBtn.textContent = '⚡ Promote Now';
            }
        }
    }

    if (badge) {
        if (modelData.auto_rollback_eligible) {
            badge.textContent = '⚠️ Rollback Recommended';
            badge.style.color = '#ef4444';
            badge.style.borderColor = '#ef4444';
            badge.style.background = 'rgba(239, 68, 68, 0.2)';
        } else if (modelData.auto_promote_eligible) {
            badge.textContent = '🚀 Challenger Outperforming';
            badge.style.color = '#10b981';
            badge.style.borderColor = '#10b981';
            badge.style.background = 'rgba(16, 185, 129, 0.2)';
        } else {
            badge.textContent = '🏆 Champion Active';
            badge.style.color = '#10b981';
            badge.style.borderColor = '#10b981';
            badge.style.background = 'rgba(16, 185, 129, 0.2)';
        }
    }
}

async function triggerEmergencyHaltRiskCenter() {
    const reason = prompt("Enter emergency halt reason (e.g. Market Dislocation / Operational Anomaly):", "Manual operator halt triggered from dashboard");
    if (!reason) return;
    try {
        const resp = await fetch('/api/v1/system/risk-center/halt', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ reason: reason, triggered_by: 'DASHBOARD_OPERATOR' })
        });
        const data = await resp.json();
        alert(`🚨 EMERGENCY HALT ENGAGED: ${data.reason}`);
        fetchPortfolio();
        fetchUnifiedRiskStatus();
    } catch (e) {
        alert(`Failed to trigger halt: ${e}`);
    }
}

async function resumeRiskCenter() {
    const confirmStr = prompt("To clear emergency halt and resume execution, type 'CONFIRM_RESUME':");
    if (!confirmStr) return;
    try {
        const resp = await fetch('/api/v1/system/risk-center/resume', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ confirmation: confirmStr, authorized_by: 'RISK_DIRECTOR' })
        });
        if (resp.ok) {
            alert("✅ System Emergency Halt Cleared. Normal execution resumed.");
            fetchPortfolio();
            fetchUnifiedRiskStatus();
        } else {
            const err = await resp.json();
            alert(`Resume rejected: ${err.detail || 'Invalid confirmation'}`);
        }
    } catch (e) {
        alert(`Failed to resume: ${e}`);
    }
}

async function promoteChallenger() {
    if (!confirm("Are you sure you want to promote the Challenger model to active Champion?")) return;
    try {
        const resp = await fetch('/api/v1/system/models/promote', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ reason: "Manual promotion from dashboard" })
        });
        const data = await resp.json();
        if (resp.ok) {
            alert(`🏆 Model Promoted! New Champion: ${data.new_champion} (${data.new_version})`);
            fetchPortfolio();
            fetchModelsStatus();
            fetchUnifiedRiskStatus();
        } else {
            alert(`Promotion failed: ${data.detail || data.message}`);
        }
    } catch (e) {
        alert(`Promotion error: ${e}`);
    }
}

async function rollbackChampion() {
    if (!confirm("Are you sure you want to rollback the active Champion model to safe Fallback?")) return;
    try {
        const resp = await fetch('/api/v1/system/models/rollback', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ reason: "Manual rollback from dashboard" })
        });
        const data = await resp.json();
        if (resp.ok) {
            alert(`🔄 Model Rollback Completed! Active Model: ${data.active_model} (${data.active_version})`);
            fetchPortfolio();
            fetchModelsStatus();
            fetchUnifiedRiskStatus();
        } else {
            alert(`Rollback failed: ${data.detail || data.message}`);
        }
    } catch (e) {
        alert(`Rollback error: ${e}`);
    }
}

// Initial render & lifecycle
document.addEventListener('DOMContentLoaded', () => {
    updateTime();
    setInterval(updateTime, 1000); // Dynamic clock every 1 second
    
    // Fetch initial portfolio snapshot immediately
    fetchPortfolio();
    
    // Connect live WebSocket stream
    setupWebSocket();
    
    // System status, logs & risk metrics
    fetchSystemStatus();
    fetchAuditLogs();
    fetchRiskVarMetrics();
    fetchUnifiedRiskStatus();
    fetchModelsStatus();
    
    // Fallback polling: if WebSocket disconnects, poll portfolio every second
    setInterval(() => {
        if (!window.isWebSocketConnected) {
            fetchPortfolio();
        }
    }, 1500);

    // Poll audit logs and risk metrics regularly
    setInterval(fetchAuditLogs, 2500);
    setInterval(fetchRiskVarMetrics, 5000);
    setInterval(fetchUnifiedRiskStatus, 4000);
    setInterval(fetchModelsStatus, 5000);
});


