"""
tests/test_router.py

Run with:
    python -m pytest tests/ -v
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from router.network import build_network, build_sim_network
from router.simulator import simulate_route, score_route
from router.engine import find_best_route


@pytest.fixture(scope="module")
def live_network():
    return build_network()

@pytest.fixture(scope="module")
def sim_network():
    return build_sim_network()


class TestNetwork:

    def test_live_network_has_chains(self, live_network):
        assert live_network.number_of_nodes() >= 5

    def test_live_network_has_bridges(self, live_network):
        assert live_network.number_of_edges() >= 10

    def test_live_known_chains_exist(self, live_network):
        for chain in ["ethereum", "polygon", "arbitrum", "base", "optimism"]:
            assert chain in live_network.nodes

    def test_sim_network_has_more_chains(self, live_network, sim_network):
        assert sim_network.number_of_nodes() > live_network.number_of_nodes()

    def test_sim_includes_solana(self, sim_network):
        assert "solana" in sim_network.nodes


class TestSimulator:

    def test_simulate_direct_route(self, live_network):
        result = simulate_route(live_network, ["ethereum", "polygon"], amount_usd=1000)
        assert result["total_fee_usd"] > 0
        assert result["total_latency_sec"] > 0
        assert result["num_hops"] == 1

    def test_simulate_multi_hop(self, sim_network):
        result = simulate_route(sim_network, ["ethereum", "polygon", "solana"], amount_usd=5000)
        assert result["num_hops"] == 2
        assert result["total_fee_usd"] > 0

    def test_fee_scales_with_amount(self, live_network):
        small = simulate_route(live_network, ["ethereum", "polygon"], amount_usd=100)
        large = simulate_route(live_network, ["ethereum", "polygon"], amount_usd=100000)
        assert large["total_fee_usd"] > small["total_fee_usd"]

    def test_score_lower_is_better(self, live_network):
        cheap = {"total_fee_usd": 1.0, "total_latency_sec": 30, "num_hops": 1}
        expensive = {"total_fee_usd": 10.0, "total_latency_sec": 600, "num_hops": 3}
        assert score_route(cheap) < score_route(expensive)


class TestEngine:

    def test_finds_route_sim(self, sim_network):
        result = find_best_route(sim_network, "ethereum", "solana", amount_usd=1000, use_live=False)
        assert result["best"] is not None
        assert result["best"]["route"][0] == "ethereum"
        assert result["best"]["route"][-1] == "solana"

    def test_best_route_lowest_score(self, sim_network):
        result = find_best_route(sim_network, "ethereum", "solana", amount_usd=5000, use_live=False)
        if result["best"] is None or len(result["all_routes"]) < 2:
            pytest.skip("Not enough routes to compare")
        best_score = result["best"]["score"]
        for route in result["all_routes"]:
            assert route["score"] >= best_score

    def test_invalid_chain_returns_gracefully(self, sim_network):
        result = find_best_route(sim_network, "narnia", "solana", amount_usd=100, use_live=False)
        assert result["best"] is None

    def test_route_respects_max_hops(self, sim_network):
        result = find_best_route(sim_network, "ethereum", "solana", amount_usd=1000,
                                 max_hops=2, use_live=False)
        if result["best"] is not None:
            assert result["best"]["num_hops"] <= 2
