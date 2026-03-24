# Stablecoin Settlement Router (Prototype)

A routing engine for stablecoin-based cross-border B2B payments.
Built to explore the idea of smart settlement routing
across blockchain networks.

---

## The Idea

When a business in Dubai pays a supplier in Singapore using USDC,
the payment might travel across multiple blockchain "hops."
Each hop has a different fee and speed.

This prototype asks: **how can we find the cheapest + fastest route automatically?**

---
## Two Modes

Getting reliable, real-time quote data from bridge APIs is harder than it sounds - rate limits, authentication requirements, and inconsistent responses make live data difficult to work with in a prototype context. Because of this, **the Simulator tab is the better demonstration of the actual routing logic.**

### Simulator (start here)
Uses realistic mock data modelled on real bridge fee structures (Stargate, Across, Wormhole, cBridge etc.). Covers 9 chains and both USDC and USDT. No API calls, no rate limits — instant results. This is where the routing engine actually gets to show its work: multi-hop paths, fee sensitivity curves, and route comparisons all function cleanly.

### Live
Fetches real bridge quotes from the Across Protocol API. Limited to 5 EVM chains and USDC only, as Across is one of the few bridges with a clean, no-auth quote endpoint. Less interesting as a routing demo.

---

## Web Dashboard

A browser-based interface where you configure a transfer and instantly see:

- The optimal route across chains, with fee and latency for each bridge hop
- Route insights, including estimated savings vs a traditional SWIFT wire
- Alternative routes ranked by score
- A fee sensitivity chart showing how costs scale with transfer size
- Stablecoin selection (USDC, USDT); routes filtered by which bridges support your chosen coin

**To run the dashboard:**

```bash
pip install -r requirements.txt
python app.py
```

Then open your browser at **http://localhost:5000**

No API key needed for the Simulator. For the Live tab, Across Protocol's public API is used directly with no authentication required.

---

## Project Structure

```
stablecoin-project/
├── app.py                # Flask server + all API endpoints
├── templates/
│   └── index.html        # Dashboard UI (Live + Simulator tabs)
├── router/
│   ├── network.py        # Builds the chain/bridge graph (live and sim)
│   ├── across.py           # Across Protocol API integration (live quotes)
│   ├── simulator.py      # Route cost calculation (live or mock)
│   └── engine.py         # Routing engine — finds and scores all paths
├── data/
│   └── mock_chains.py    # Chain and bridge data (used by both tabs)
├── examples/
│   └── run_routing.py    # Command-line demo using the simulator
├── tests/
│   └── test_router.py    # Test suite covering core routing logic
├── requirements.txt
└── README.md
```

---

## How the Router Works

1. **Network**: chains (Ethereum, Polygon, Base etc.) are modelled as nodes in a graph. Bridges between them are edges with fee, latency, and reliability data.
2. **Pathfinding**: finds all possible paths between source and destination up to a configurable hop limit.
3. **Scoring**: combines fee, latency, and reliability into a single score. You control the weighting (e.g. 70% fee, 30% speed). Less reliable bridges are penalised even if they look cheaper on paper.
4. **Live mode**: replaces mock fees with real Across Protocol quotes for supported pairs. Only routes where every hop returns a valid quote are shown.

---

## API Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `GET /api/chains` | GET | Chains available in the live tab |
| `GET /api/sim/chains` | GET | Chains available in the simulator |
| `POST /api/route/stream` | POST | Live route — streams progress as quotes come in |
| `POST /api/route/sensitivity` | POST | Live fee sensitivity data across 9 transfer amounts |
| `POST /api/sim/route` | POST | Simulator route — instant, no API calls |
| `POST /api/sim/sensitivity` | POST | Simulator fee sensitivity — instant |
| `POST /api/swift_estimate` | POST | SWIFT wire cost breakdown for comparison |


---

## Running Tests

```bash
python -m pytest tests/ -v
```

---

## Tech Used

- `flask` - web server and API
- `networkx` - for modeling chains/bridges as a graph
- `numpy` - for fee/latency calculations
- `requests` - Across Protocol API calls (live tab)
- Python 3.10+
