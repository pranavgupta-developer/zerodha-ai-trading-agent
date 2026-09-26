// Mock Data for the Dashboard Skeleton

const mockWatchlist = [
    { symbol: 'RELIANCE', ltp: 2984.50, change: 1.2, signal: 'BUY' },
    { symbol: 'TCS', ltp: 4120.00, change: -0.5, signal: 'HOLD' },
    { symbol: 'HDFCBANK', ltp: 1650.25, change: 0.8, signal: 'BUY' },
    { symbol: 'INFY', ltp: 1540.10, change: -1.2, signal: 'SELL' },
    { symbol: 'ICICIBANK', ltp: 1080.40, change: 0.3, signal: 'HOLD' }
];

const mockPositions = [
    { symbol: 'RELIANCE', qty: 50, avg: 2950.00, ltp: 2984.50 },
    { symbol: 'TCS', qty: -20, avg: 4150.00, ltp: 4120.00 },
];

function formatCurrency(value) {
    return new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR' }).format(value);
}

function renderWatchlist() {
    const tbody = document.querySelector('#watchlist-table tbody');
    tbody.innerHTML = '';
    
    mockWatchlist.forEach(item => {
        const tr = document.createElement('tr');
        
        const changeClass = item.change >= 0 ? 'positive' : 'negative';
        const changePrefix = item.change >= 0 ? '+' : '';
        const signalClass = `signal-${item.signal.toLowerCase()}`;
        
        tr.innerHTML = `
            <td style="font-weight: 600;">${item.symbol}</td>
            <td>₹${item.ltp.toFixed(2)}</td>
            <td class="${changeClass}">${changePrefix}${item.change.toFixed(2)}%</td>
            <td><span class="signal-badge ${signalClass}">${item.signal}</span></td>
        `;
        tbody.appendChild(tr);
    });
}

function renderPositions() {
    const tbody = document.querySelector('#positions-table tbody');
    tbody.innerHTML = '';
    
    let totalUnrealized = 0;
    
    mockPositions.forEach(pos => {
        const pnl = (pos.ltp - pos.avg) * pos.qty;
        totalUnrealized += pnl;
        
        const pnlClass = pnl >= 0 ? 'positive' : 'negative';
        const pnlPrefix = pnl >= 0 ? '+' : '';
        
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td style="font-weight: 600;">${pos.symbol}</td>
            <td>${pos.qty}</td>
            <td>₹${pos.avg.toFixed(2)}</td>
            <td>₹${pos.ltp.toFixed(2)}</td>
            <td class="${pnlClass}">${pnlPrefix}₹${Math.abs(pnl).toFixed(2)}</td>
            <td><button class="btn btn-reject" style="padding: 4px 8px; font-size: 0.8rem;" onclick="closePosition('${pos.symbol}', ${pos.qty})">Close</button></td>
        `;
        tbody.appendChild(tr);
    });
    
    // Update summary cards
    document.getElementById('margin-val').textContent = formatCurrency(450000);
    document.getElementById('realized-pnl-val').textContent = formatCurrency(2500);
    
    const unrealizedEl = document.getElementById('unrealized-pnl-val');
    unrealizedEl.textContent = formatCurrency(totalUnrealized);
    unrealizedEl.className = `value ${totalUnrealized >= 0 ? 'positive' : 'negative'}`;
}

function updateTime() {
    const now = new Date();
    document.getElementById('last-update-time').textContent = `Last update: ${now.toLocaleTimeString()}`;
}

function setupWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/candidate-trades`;
    const ws = new WebSocket(wsUrl);
    
    ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        if (data.type === 'market_update') {
            // Update watchlist
            mockWatchlist.length = 0;
            mockWatchlist.push(...data.watchlist);
            
            // Sync positions from broker (via backend)
            if (data.positions) {
                mockPositions.length = 0;
                mockPositions.push(...data.positions);
            }
            
            renderWatchlist();
            renderPositions();
            updateTime();
        } else if (data.type === 'candidate_trade') {
            renderCandidate(data.candidate);
        } else {
            // legacy fallback
            renderCandidate(data);
        }
    };
    
    ws.onclose = () => {
        console.log("WebSocket connection closed. Reconnecting...");
        setTimeout(setupWebSocket, 3000);
    };
}

function renderCandidate(candidate) {
    const tbody = document.querySelector('#candidate-trades-table tbody');
    const noCandidatesRow = document.getElementById('no-candidates-row');
    if (noCandidatesRow) {
        noCandidatesRow.remove();
    }
    
    const tr = document.createElement('tr');
    tr.id = `trade-${candidate.id}`;
    
    const actionClass = candidate.action === 'BUY' ? 'signal-buy' : 'signal-sell';
    
    tr.innerHTML = `
        <td style="font-weight: 600;">${candidate.symbol}</td>
        <td><span class="signal-badge ${actionClass}">${candidate.action}</span></td>
        <td>₹${candidate.price.toFixed(2)}</td>
        <td class="ai-reasoning">${candidate.reasoning}</td>
        <td>
            <button class="btn btn-approve" onclick="handleTradeAction('${candidate.id}', 'APPROVE')">Approve</button>
            <button class="btn btn-reject" onclick="handleTradeAction('${candidate.id}', 'REJECT')">Reject</button>
        </td>
    `;
    // Insert at the top
    tbody.insertBefore(tr, tbody.firstChild);
}

async function handleTradeAction(tradeId, action) {
    try {
        const response = await fetch('/api/v1/trades/action', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ trade_id: tradeId, action: action })
        });
        
        if (response.ok) {
            const tr = document.getElementById(`trade-${tradeId}`);
            if (tr) {
                const td = tr.querySelector('td:last-child');
                td.innerHTML = `<span class="badge ${action === 'APPROVE' ? 'mode-dry' : ''}" style="${action === 'APPROVE' ? 'background-color: var(--positive);' : 'background-color: var(--negative); color: white;'}">${action}D</span>`;
                
                // Add to positions if approved (mock behavior)
                if (action === 'APPROVE') {
                    const symbolEl = tr.querySelector('td:first-child').innerText;
                    const priceEl = parseFloat(tr.querySelectorAll('td')[2].innerText.replace('₹', ''));
                    const isBuy = tr.querySelector('.signal-badge').innerText === 'BUY';
                    const qty = isBuy ? 10 : -10;
                    
                    mockPositions.push({
                        symbol: symbolEl,
                        qty: qty,
                        avg: priceEl,
                        ltp: priceEl
                    });
                    renderPositions();
                }
            }
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
            // Optimistically remove from mockPositions for fast UI update
            const idx = mockPositions.findIndex(p => p.symbol === symbol);
            if (idx > -1) mockPositions.splice(idx, 1);
            renderPositions();
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
        
        // Update Trading Mode Badge
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
        tbody.innerHTML = '';
        
        if (data.logs.length === 0) {
            tbody.innerHTML = '<tr><td colspan="6" style="text-align: center; color: var(--text-muted);">No audit logs found.</td></tr>';
            return;
        }
        
        data.logs.forEach(log => {
            const tr = document.createElement('tr');
            const date = new Date(log.timestamp + 'Z'); // parse as UTC
            
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

// Initial render
document.addEventListener('DOMContentLoaded', () => {
    renderWatchlist();
    renderPositions();
    updateTime();
    setupWebSocket();
    fetchSystemStatus();
    fetchAuditLogs();
    
    // Poll audit logs
    setInterval(fetchAuditLogs, 5000);
});
