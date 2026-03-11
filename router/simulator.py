"""
router/simulator.py

Simulates the cost and time of sending money along a specific route.

A "route" is just a list of chains to hop through, like:
  ["ethereum", "polygon", "solana"]

For each hop, we calculate:
  - The fee in USD (base fee + % of the amount)
  - The latency in seconds (with some random noise, because real life is messy)

This is all made-up math — but it's based on roughly realistic ballparks
for what cross-chain bridges actually charge. Could tune these later
with real API data.
"""

import numpy as np
import networkx as nx
from typing import List
from router.lifi import get_live_quote


def simulate_route(
    G: nx.DiGraph,
    route: List[str],
    amount_usd: float,
    noise_factor: float = 0.15,
    stablecoin: str = "USDC",
    quote_cache: dict = None,
) -> dict:
    """
    Given a route (list of chain IDs), calculate the total cost and time
    of sending `amount_usd` along that path.

    Uses pre-fetched quotes from `quote_cache` if available (much faster).
    Falls back to a fresh Swing.xyz call, then mock data if all else fails.
    """

    total_fee_usd = 0.0
    total_latency_sec = 0.0
    hops = []

    for i in range(len(route) - 1):
        src = route[i]
        dst = route[i + 1]

        edge = G.get_edge_data(src, dst)

        if edge is None:
            print(f"  [simulator] WARNING: No bridge found {src} -> {dst}")
            continue

        # Use cached quote if available, otherwise fetch live
        if quote_cache and (src, dst) in quote_cache:
            live = quote_cache[(src, dst)]
        else:
            live = get_live_quote(src, dst, stablecoin, amount_usd)

        if live:
            hop_fee = live["fee_usd"]
            hop_latency = live["latency_sec"] or edge["avg_latency_sec"]
            bridge_name = live["bridge_name"]
            data_source = "live"
        else:
            # Fall back to mock data with noise
            base_fee = edge["base_fee_usd"]
            pct_fee = edge["fee_pct"] * amount_usd
            noise = np.random.normal(1.0, noise_factor)
            hop_fee = max(0, (base_fee + pct_fee) * noise)

            latency_noise = np.random.normal(1.0, noise_factor)
            hop_latency = max(1, edge["avg_latency_sec"] * latency_noise)
            bridge_name = edge["bridge_name"]
            data_source = "mock"

        total_fee_usd += hop_fee
        total_latency_sec += hop_latency

        hops.append({
            "from":        src,
            "to":          dst,
            "bridge":      bridge_name,
            "fee_usd":     round(hop_fee, 4),
            "latency_sec": round(hop_latency, 2),
            "reliability": edge["reliability"],
            "data_source": data_source,
        })

    return {
        "route":              route,
        "amount_usd":         amount_usd,
        "total_fee_usd":      round(total_fee_usd, 4),
        "total_latency_sec":  round(total_latency_sec, 2),
        "hops":               hops,
        "num_hops":           len(hops),
    }


def score_route(simulation_result: dict, fee_weight: float = 0.6) -> float:
    """
    Combines fee, latency, and reliability into a single score for comparing routes.
    Lower score = better route.

    We weight fee more heavily by default (60/40) because for B2B
    cross-border payments, cost usually matters more than a few extra seconds.

    Reliability penalty: a route through unreliable bridges is penalised even if
    it looks cheap on paper. Each hop's reliability multiplies together — three
    hops at 94% reliability gives a combined probability of only ~83%.
    """

    latency_weight = 1.0 - fee_weight

    fee_score = simulation_result["total_fee_usd"] * fee_weight
    latency_score = (simulation_result["total_latency_sec"] / 60) * latency_weight

    # Small penalty for more hops — each hop adds smart contract risk
    hop_penalty = simulation_result["num_hops"] * 0.05

    # Reliability penalty: combined route reliability (product of all hops).
    # A perfectly reliable route scores 0 extra; a 50% reliable route adds ~0.69.
    import math
    hops = simulation_result.get("hops", [])
    if hops:
        combined_reliability = 1.0
        for hop in hops:
            combined_reliability *= hop.get("reliability", 1.0)
        # -log(reliability) is 0 at 100%, grows as reliability drops
        reliability_penalty = -math.log(combined_reliability) * 0.5
    else:
        reliability_penalty = 0.0

    return round(fee_score + latency_score + hop_penalty + reliability_penalty, 4)
