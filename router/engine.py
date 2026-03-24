"""
router/engine.py
Routing engine — shared by both Live and Simulator tabs.
use_live=False skips Across API calls (simulator mode).
"""

import networkx as nx
from router.simulator import simulate_route, score_route


def find_best_route(G, source, target, amount_usd, max_hops=4,
                    fee_weight=0.6, top_n=3, stablecoin="USDC", use_live=True):

    print(f"\n[engine] {source} -> {target} | ${amount_usd:,.2f} {stablecoin} | live={use_live}")

    filtered = [(u, v) for u, v, d in G.edges(data=True)
                if stablecoin in d.get("supported_stablecoins", [stablecoin])]
    Gf = G.edge_subgraph(filtered).copy()

    try:
        all_paths = list(nx.all_simple_paths(Gf, source=source, target=target, cutoff=max_hops))
    except (nx.NetworkXNoPath, nx.NodeNotFound):
        return {"best": None, "all_routes": [], "error": "No path found."}

    if not all_paths:
        return {"best": None, "all_routes": [], "error": f"No {stablecoin} routes between {source} and {target}."}

    # Pre-fetch quotes (live mode only)
    quote_cache = {}
    if use_live:
        from router.across import get_quotes_parallel
        unique_hops = {(p[i], p[i+1]) for p in all_paths for i in range(len(p)-1)}
        quote_cache = get_quotes_parallel(list(unique_hops), stablecoin, amount_usd)

    scored = []
    for path in all_paths:
        sim = simulate_route(Gf, path, amount_usd, stablecoin=stablecoin,
                             quote_cache=quote_cache if use_live else None)
        sim["score"] = score_route(sim, fee_weight=fee_weight)
        scored.append(sim)

    scored.sort(key=lambda r: r["score"])

    if use_live:
        routes = [r for r in scored if r.get("hops") and
                  all(h.get("data_source") == "live" for h in r["hops"])]
        if not routes:
            return {"best": None, "all_routes": [],
                    "error": "No live routes found. Try a different pair."}
    else:
        routes = scored  # simulator: all routes are valid

    return {"best": routes[0], "all_routes": routes[:top_n]}
