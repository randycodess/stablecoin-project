"""
router/lifi.py

Fetches live bridge quotes from the Across Protocol API.
https://docs.across.to/reference/suggested-fees-endpoint

Across is a fast, low-fee bridge focused on USDC transfers across
major EVM chains. No API key required.

Supported chains: Ethereum, Arbitrum, Base, Optimism, Polygon.

If the API is unavailable or a route isn't supported, functions here
return None and the engine falls back to mock data automatically.
"""

import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

ACROSS_API_BASE = "https://app.across.to/api"

# Chain name → chain ID + USDC address
CHAIN_MAP = {
    "ethereum": {
        "chainId": 1,
        "usdc":    "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
    },
    "arbitrum": {
        "chainId": 42161,
        "usdc":    "0xaf88d065e77c8cC2239327C5EDb3A432268e5831",
    },
    "base": {
        "chainId": 8453,
        "usdc":    "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
    },
    "optimism": {
        "chainId": 10,
        "usdc":    "0x0b2C639c533813f4Aa9D7837CAf62653d097Ff85",
    },
    "polygon": {
        "chainId": 137,
        "usdc":    "0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359",
    },
}


def get_live_quote(from_chain: str, to_chain: str, token: str, amount_usd: float) -> dict | None:
    """
    Fetches a live quote from Across Protocol for a single hop (from_chain → to_chain).

    Args:
        from_chain:  Source chain name (e.g. "ethereum")
        to_chain:    Destination chain name (e.g. "arbitrum")
        token:       Stablecoin symbol — must be "USDC"
        amount_usd:  Amount in USD

    Returns:
        A dict with fee_usd, latency_sec, bridge_name, and source, or None if unavailable.
    """
    from_info = CHAIN_MAP.get(from_chain)
    to_info   = CHAIN_MAP.get(to_chain)

    if not from_info or not to_info:
        return None  # Chain not supported by Across

    if token != "USDC":
        return None  # Across only supports USDC via this integration

    # USDC uses 6 decimals
    amount_raw = int(amount_usd * 1_000_000)

    params = {
        "inputToken":          from_info["usdc"],
        "outputToken":         to_info["usdc"],
        "originChainId":       str(from_info["chainId"]),
        "destinationChainId":  str(to_info["chainId"]),
        "amount":              str(amount_raw),
    }

    try:
        response = requests.get(
            f"{ACROSS_API_BASE}/suggested-fees",
            params=params,
            timeout=8,
        )

        if response.status_code != 200:
            print(f"  [across] Quote failed for {from_chain}->{to_chain}: HTTP {response.status_code}")
            return None

        data = response.json()

        if data.get("isAmountTooLow"):
            print(f"  [across] Amount too low for {from_chain}->{to_chain}")
            return None

        fee_usd     = float(data["relayFeeTotal"]) / 1e6
        latency_sec = data.get("estimatedFillTimeSec")

        print(f"  [across] [OK] Live quote {from_chain}->{to_chain}: "
              f"${fee_usd:.4f} fee, {latency_sec}s via Across")

        return {
            "fee_usd":     round(fee_usd, 4),
            "latency_sec": latency_sec,
            "bridge_name": "Across",
            "source":      "across_live",
        }

    except requests.exceptions.Timeout:
        print(f"  [across] Timeout fetching quote for {from_chain}->{to_chain}")
        return None
    except Exception as e:
        print(f"  [across] Error fetching quote for {from_chain}->{to_chain}: {e}")
        return None


def get_quotes_parallel(hops: list, token: str, amount_usd: float) -> dict:
    """
    Fetches Across quotes for multiple hops simultaneously (in parallel).

    Args:
        hops:        List of (from_chain, to_chain) tuples
        token:       Stablecoin symbol (must be "USDC")
        amount_usd:  Amount in USD

    Returns:
        Dict mapping (from_chain, to_chain) → quote result (or None if failed)
    """
    results = {}

    def fetch(hop):
        from_chain, to_chain = hop
        return hop, get_live_quote(from_chain, to_chain, token, amount_usd)

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {executor.submit(fetch, hop): hop for hop in hops}
        for future in as_completed(futures):
            hop, result = future.result()
            results[hop] = result

    return results
