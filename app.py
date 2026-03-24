"""
app.py - Stablecoin Settlement Router
Live tab: Across Protocol, USDC, 5 chains
Simulator tab: mock data, USDC + USDT, 9 chains
"""

from flask import Flask, render_template, request, jsonify, Response, stream_with_context
import sys, os, json, queue, threading
from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from router.network import build_network, build_sim_network
from router.engine import find_best_route
from router.simulator import simulate_route, score_route

app = Flask(__name__)

print("Building networks...")
G_live = build_network()
G_sim  = build_sim_network()
print("Ready.\n")


def _swift_cost(amount):
    fx = amount * 0.025
    return {
        "sending_fee_usd": 35.0, "fx_spread_pct": 2.5,
        "fx_cost_usd": round(fx, 2), "intermediary_fee_usd": 20.0,
        "total_cost_usd": round(55 + fx, 2),
        "total_cost_pct": round(((55 + fx) / amount) * 100, 3),
        "settlement_days_min": 2, "settlement_days_max": 5,
    }


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/chains")
def get_chains():
    from data.mock_chains import LIVE_CHAINS
    return jsonify(LIVE_CHAINS)


@app.route("/api/sim/chains")
def get_sim_chains():
    from data.mock_chains import CHAINS
    return jsonify(CHAINS)


@app.route("/api/swift_estimate", methods=["POST"])
def swift_estimate():
    data = request.get_json()
    if not data:
        return jsonify({"error": "Invalid request"}), 400
    try:
        amount = float(data.get("amount", 5000))
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid amount"}), 400
    if amount <= 0:
        return jsonify({"error": "Amount must be > 0"}), 400
    return jsonify(_swift_cost(amount))


# ── Live streaming route ──────────────────────────────────────────────────────

@app.route("/api/route/stream", methods=["POST"])
def get_route_stream():
    data = request.get_json()
    if not data:
        return jsonify({"error": "Invalid request."}), 400

    source     = data.get("source", "ethereum")
    target     = data.get("target", "arbitrum")
    stablecoin = data.get("stablecoin", "USDC").upper()

    if stablecoin != "USDC":
        return jsonify({"error": "Live tab only supports USDC via Across Protocol."}), 400

    try:
        amount     = max(0.01, min(float(data.get("amount", 5000)), 10_000_000))
        fee_weight = max(0.0,  min(float(data.get("fee_weight", 0.6)), 1.0))
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid parameters."}), 400

    pq = queue.Queue()

    def run():
        from router.across import get_live_quote, CHAIN_MAP
        from concurrent.futures import ThreadPoolExecutor, as_completed
        import networkx as nx

        try:
            pq.put({"type": "status", "message": "Building route graph..."})

            filtered = [(u, v) for u, v, d in G_live.edges(data=True)
                        if stablecoin in d.get("supported_stablecoins", [stablecoin])]
            Gf = G_live.edge_subgraph(filtered).copy()

            if source not in Gf or target not in Gf:
                pq.put({"type": "error", "message": f"No {stablecoin} bridges available for selected chains."}); return

            all_paths = list(nx.all_simple_paths(Gf, source=source, target=target, cutoff=4))
            if not all_paths:
                pq.put({"type": "error", "message": "No routes found."}); return

            pq.put({"type": "status", "message": f"Found {len(all_paths)} route(s). Fetching live quotes..."})

            unique_hops = {(p[i], p[i+1]) for p in all_paths for i in range(len(p)-1)}
            supported   = [(f, t) for f, t in unique_hops if CHAIN_MAP.get(f) and CHAIN_MAP.get(t)]

            pq.put({"type": "status", "message": f"Querying Across Protocol for {len(supported)} hop(s)..."})

            quote_cache = {}

            def fetch(hop):
                f, t = hop
                r = get_live_quote(f, t, stablecoin, amount)
                label = f"${r['fee_usd']}" if r else "(no quote)"
                pq.put({"type": "hop", "message": f"⚡ {f} → {t}  {label}"})
                return hop, r

            with ThreadPoolExecutor(max_workers=8) as ex:
                futures = {ex.submit(fetch, h): h for h in supported}
                for future in as_completed(futures):
                    try:
                        hop, result = future.result()
                        quote_cache[hop] = result
                    except Exception as exc:
                        hop = futures[future]
                        print(f"  [stream] Future error for {hop}: {exc}")
                        quote_cache[hop] = None

            for hop in unique_hops - set(supported):
                quote_cache[hop] = None

            pq.put({"type": "status", "message": "Scoring routes..."})

            scored = []
            for path in all_paths:
                sim = simulate_route(Gf, path, amount, stablecoin=stablecoin, quote_cache=quote_cache)
                sim["score"] = score_route(sim, fee_weight=fee_weight)
                scored.append(sim)
            scored.sort(key=lambda r: r["score"])

            live_routes = [r for r in scored if r.get("hops") and
                           all(h.get("data_source") == "live" for h in r["hops"])]

            if not live_routes:
                pq.put({"type": "error", "message": "No live routes found for this pair. Try a different combination."}); return

            pq.put({"type": "result", "data": {
                "best": live_routes[0], "all_routes": live_routes[:3], "stablecoin": stablecoin
            }})

        except Exception as e:
            pq.put({"type": "error", "message": str(e)})

    threading.Thread(target=run).start()

    def generate():
        while True:
            try:
                msg = pq.get(timeout=30)
                yield f"data: {json.dumps(msg)}\n\n"
                if msg["type"] in ("result", "error"):
                    break
            except queue.Empty:
                yield f"data: {json.dumps({'type':'error','message':'Request timed out.'})}\n\n"
                break

    return Response(stream_with_context(generate()), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ── Live fee sensitivity (real Across quotes, opt-in) ────────────────────────

@app.route("/api/route/sensitivity", methods=["POST"])
def route_sensitivity():
    data = request.get_json()
    if not data:
        return jsonify({"error": "Invalid request"}), 400

    route      = data.get("route", [])
    stablecoin = data.get("stablecoin", "USDC").upper()

    if len(route) < 2:
        return jsonify({"error": "Route must have at least 2 chains"}), 400

    AMOUNTS = [100, 500, 1_000, 5_000, 10_000, 50_000, 100_000, 500_000, 1_000_000]
    hops = [(route[i], route[i+1]) for i in range(len(route)-1)]

    from router.across import get_live_quote
    from concurrent.futures import ThreadPoolExecutor, as_completed

    def fetch_for_amount(amt):
        total = 0.0
        for f, t in hops:
            q = get_live_quote(f, t, stablecoin, amt)
            if q is None:
                return None
            total += q["fee_usd"]
        swift = _swift_cost(amt)["total_cost_usd"]
        return {"amount": amt, "fee_usd": round(total, 4),
                "fee_pct": round((total / amt) * 100, 4),
                "swift_usd": swift}

    results = []
    with ThreadPoolExecutor(max_workers=8) as ex:
        futures = {ex.submit(fetch_for_amount, a): a for a in AMOUNTS}
        for future in as_completed(futures):
            try:
                r = future.result()
                if r:
                    results.append(r)
            except Exception as exc:
                print(f"  [sensitivity] Future error for amount {futures[future]}: {exc}")

    results.sort(key=lambda x: x["amount"])
    return jsonify({"points": results, "stablecoin": stablecoin})


# ── Simulator route (instant, no API calls) ───────────────────────────────────

@app.route("/api/sim/route", methods=["POST"])
def sim_route():
    data = request.get_json()
    if not data:
        return jsonify({"error": "Invalid request"}), 400

    source     = data.get("source", "ethereum")
    target     = data.get("target", "solana")
    stablecoin = data.get("stablecoin", "USDC").upper()

    try:
        amount     = max(0.01, min(float(data.get("amount", 5000)), 10_000_000))
        fee_weight = max(0.0,  min(float(data.get("fee_weight", 0.6)), 1.0))
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid parameters"}), 400

    if source == target:
        return jsonify({"error": "Source and destination must differ"}), 400

    result = find_best_route(G_sim, source=source, target=target, amount_usd=amount,
                             fee_weight=fee_weight, stablecoin=stablecoin, use_live=False)

    if result["best"] is None:
        return jsonify({"error": result.get("error", "No route found.")}), 404

    result["stablecoin"] = stablecoin
    return jsonify(result)


# ── Simulator fee sensitivity (instant) ──────────────────────────────────────

@app.route("/api/sim/sensitivity", methods=["POST"])
def sim_sensitivity():
    data = request.get_json()
    if not data:
        return jsonify({"error": "Invalid request"}), 400

    route      = data.get("route", [])
    stablecoin = data.get("stablecoin", "USDC").upper()

    if len(route) < 2:
        return jsonify({"error": "Route must have at least 2 chains"}), 400

    AMOUNTS = [100, 500, 1_000, 5_000, 10_000, 50_000, 100_000, 500_000, 1_000_000]
    points = []
    for amt in AMOUNTS:
        sim = simulate_route(G_sim, route, amt, stablecoin=stablecoin, noise_factor=0.0)
        swift = _swift_cost(amt)["total_cost_usd"]
        points.append({"amount": amt, "fee_usd": sim["total_fee_usd"],
                       "fee_pct": round((sim["total_fee_usd"] / amt) * 100, 4),
                       "swift_usd": swift})

    return jsonify({"points": points, "stablecoin": stablecoin})


if __name__ == "__main__":
    app.run(debug=True, port=5000)
