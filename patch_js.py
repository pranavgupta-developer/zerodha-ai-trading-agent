import re

with open("app/static/app.js", "r") as f:
    content = f.read()

old_render = """        tr.innerHTML = `
            <td style="font-weight: 600;">${item.symbol}</td>
            <td>₹${item.ltp.toFixed(2)}</td>
            <td class="${changeClass}">${changePrefix}${item.change.toFixed(2)}%</td>
            <td><span class="signal-badge ${signalClass}">${item.signal}</span></td>
        `;"""

new_render = """        // Calculate latencies
        const frontend_ts = Date.now() / 1000; // in seconds
        const source_latency = window.current_backend_ts ? (window.current_backend_ts - item.source_ts).toFixed(3) : "0.000";
        const total_latency = (frontend_ts - item.source_ts).toFixed(3);
        
        tr.innerHTML = `
            <td style="font-weight: 600;">
                ${item.symbol}
                <div style="font-size: 0.65rem; color: var(--text-muted); font-weight: normal; margin-top: 4px;">
                    Latency: src->backend ${source_latency}s | src->ui ${total_latency}s
                </div>
            </td>
            <td>₹${item.ltp.toFixed(2)}</td>
            <td class="${changeClass}">${changePrefix}${item.change.toFixed(2)}%</td>
            <td><span class="signal-badge ${signalClass}">${item.signal}</span></td>
        `;"""

content = content.replace(old_render, new_render)

old_ws = """            if (data.account_stats) {
                document.getElementById('margin-val').textContent = formatCurrency(data.account_stats.margin);
                document.getElementById('realized-pnl-val').textContent = formatCurrency(data.account_stats.realized_pnl);
            }
            
            renderWatchlist();"""

new_ws = """            if (data.account_stats) {
                document.getElementById('margin-val').textContent = formatCurrency(data.account_stats.margin);
                document.getElementById('realized-pnl-val').textContent = formatCurrency(data.account_stats.realized_pnl);
            }
            
            window.current_backend_ts = data.backend_ts;
            
            renderWatchlist();"""

content = content.replace(old_ws, new_ws)

with open("app/static/app.js", "w") as f:
    f.write(content)
