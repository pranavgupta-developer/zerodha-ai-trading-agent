export interface WatchlistItem {
  symbol: string;
  ltp: number;
  prev_close?: number;
  change?: number;
  signal: string;
  status: string;
  source_ts?: number | string;
  rsi?: number;
  ml_predict?: string;
}

export interface PositionItem {
  symbol: string;
  qty: number;
  avg: number;
  ltp: number;
  pnl: number;
  pnl_pct?: number;
  stop_loss?: number;
  take_target?: number;
}

export interface AutonomousTrade {
  id: string;
  symbol: string;
  action: 'BUY' | 'SELL';
  qty: number;
  price: number;
  stop_loss?: number;
  take_target?: number;
  confidence_score?: number;
  reasoning: string;
  timestamp?: string;
  broker_order_id?: string | number;
  allocated_capital?: number;
  risk_budget?: number;
  risk_pct?: number;
  sizing_rationale?: string;
}

export interface AuditLogItem {
  timestamp: string;
  event_type: string;
  symbol?: string;
  action: string;
  details: string;
}

export interface FeedbackMessage {
  text: string;
  type: 'success' | 'danger';
}
