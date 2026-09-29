from app.broker.kite_adapter import BrokerAdapter
b = BrokerAdapter()
b._ensure_authenticated()
print(b.get_quote(["NSE:RELIANCE"]))
