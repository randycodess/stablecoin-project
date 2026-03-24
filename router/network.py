"""
router/network.py
Builds graph networks for the Live and Simulator tabs.
"""

import networkx as nx
from data.mock_chains import LIVE_CHAINS, CHAINS, LIVE_BRIDGES, BRIDGES


def _build(chains, bridges):
    G = nx.DiGraph()
    for chain in chains:
        G.add_node(chain["id"], name=chain["name"], native_token=chain["native_token"],
                   avg_block_time_sec=chain["avg_block_time_sec"])
    for b in bridges:
        G.add_edge(b["from_chain"], b["to_chain"],
                   bridge_name=b["name"], base_fee_usd=b["base_fee_usd"],
                   fee_rate=b["fee_rate"], avg_latency_sec=b["avg_latency_sec"],
                   reliability=b["reliability"],
                   supported_stablecoins=b.get("supported_stablecoins", ["USDC"]))
    return G


def build_network():
    """Live tab: 5 chains, Across bridges only."""
    G = _build(LIVE_CHAINS, LIVE_BRIDGES)
    print(f"  [live network] {G.number_of_nodes()} chains, {G.number_of_edges()} bridges")
    return G


def build_sim_network():
    """Simulator tab: 9 chains, all mock bridges."""
    G = _build(CHAINS, BRIDGES)
    print(f"  [sim network]  {G.number_of_nodes()} chains, {G.number_of_edges()} bridges")
    return G
