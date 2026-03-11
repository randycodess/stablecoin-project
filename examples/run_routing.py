"""
examples/run_routing.py

Command-line demo of the simulator routing engine.
Uses the 9-chain simulator network (mock data, no API calls).

Run from the project root:
    python examples/run_routing.py
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from router.network import build_sim_network
from router.engine import find_best_route


def print_route(result, label=""):
    print("\n" + "=" * 60)
    if label:
        print(f"  {label}")
    print("=" * 60)

    if result["best"] is None:
        print("  No route found.")
        return

    best = result["best"]
    print(f"  Best route:  {' -> '.join(best['route'])}")
    print(f"  Fee:         ${best['total_fee_usd']:.4f} USD")
    print(f"  Latency:     {best['total_latency_sec']:.0f}s")
    print(f"  Hops:        {best['num_hops']}")
    for hop in best["hops"]:
        print(f"    {hop['from']:12s} -> {hop['to']:12s} | {hop['bridge']:35s} | "
              f"${hop['fee_usd']:.4f} | {hop['latency_sec']:.0f}s")


def main():
    print("\nStablecoin Settlement Router — Simulator Demo")
    G = build_sim_network()

    scenarios = [
        ("ethereum",  "solana",    5000,  0.7, "ETH -> Solana    | $5,000  USDC | fee-sensitive"),
        ("polygon",   "avalanche", 50000, 0.5, "Polygon -> Avax  | $50,000 USDC | balanced"),
        ("base",      "bnb",       1000,  0.3, "Base -> BNB      | $1,000  USDC | speed-sensitive"),
        ("arbitrum",  "solana",    200,   0.8, "Arbitrum -> Sol  | $200    USDC | micropayment"),
    ]

    for src, dst, amt, fw, label in scenarios:
        result = find_best_route(G, src, dst, amt, fee_weight=fw, use_live=False)
        print_route(result, label)

    print("\nDemo complete.\n")


if __name__ == "__main__":
    main()
