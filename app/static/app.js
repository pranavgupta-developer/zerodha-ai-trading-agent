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

    const totalDayProfit = currentRealizedPnl + currentUnrealizedPnl;

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

    tr.innerHTML = `
        <td style="font-size: 0.75rem; color: var(--text-muted);">${date.toLocaleTimeString()}</td>
        <td ${eventTypeClass}>${log.event_type}</td>
        <td style="font-size: 0.75rem;">${log.trade_id || '-'}</td>
        <td style="font-weight: 600;">${log.symbol || '-'}</td>
        <td>${log.action || '-'}</td>
        <td style="font-size: 0.8rem; color: var(--text-muted);">${log.details || '-'}</td>
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
        btn.style.border = 'none';
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

// Initial render & lifecycle
document.addEventListener('DOMContentLoaded', () => {
    updateTime();
    setInterval(updateTime, 1000); // Dynamic clock every 1 second
    
    // Fetch initial portfolio snapshot immediately
    fetchPortfolio();
    
    // Connect live WebSocket stream
    setupWebSocket();
    
    // System status & logs
    fetchSystemStatus();
    fetchAuditLogs();
    
    // Fallback polling: if WebSocket disconnects, poll portfolio every second
    setInterval(() => {
        if (!window.isWebSocketConnected) {
            fetchPortfolio();
        }
    }, 1500);

    // Poll audit logs regularly
    setInterval(fetchAuditLogs, 2500);
});
