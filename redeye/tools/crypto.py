"""Cryptocurrency address intelligence from public chain data."""
from __future__ import annotations

import re

from ..config import Config
from .base import ToolRegistry, ToolResult
from . import httpkit


def register(registry: ToolRegistry, cfg: Config) -> None:

    @registry.tool(
        name="crypto_address_intel",
        description=(
            "Inspect a public cryptocurrency address (BTC or ETH): balance, transaction "
            "count, recent counterparties. Uses public blockchain explorers — read-only."
        ),
        parameters={
            "type": "object",
            "properties": {
                "address": {"type": "string", "description": "BTC or ETH address"},
                "chain": {
                    "type": "string",
                    "enum": ["auto", "btc", "eth"],
                    "description": "Chain; 'auto' detects from address format",
                },
            },
            "required": ["address"],
        },
    )
    def crypto_address_intel(address: str, chain: str = "auto") -> ToolResult:
        address = address.strip()
        if chain == "auto":
            if re.fullmatch(r"0x[0-9a-fA-F]{40}", address):
                chain = "eth"
            elif re.fullmatch(r"(bc1[a-z0-9]{25,60}|[13][a-km-zA-HJ-NP-Z1-9]{25,34})", address):
                chain = "btc"
            else:
                return ToolResult.error(
                    f"Cannot detect chain for {address!r} (expected BTC base58/bech32 or ETH 0x)."
                )
        if chain == "btc":
            return _btc(address)
        return _eth(address, cfg)


def _btc(address: str) -> ToolResult:
    status, data = httpkit.get_json(
        f"https://blockchain.info/rawaddr/{address}", params={"limit": 10}, timeout=25
    )
    if status != 200 or not isinstance(data, dict):
        return ToolResult.error(f"blockchain.info returned HTTP {status} for {address}")
    bal = data.get("final_balance", 0) / 1e8
    recv = data.get("total_received", 0) / 1e8
    sent = data.get("total_sent", 0) / 1e8
    lines = [
        f"BTC address {address}:",
        f"  balance: {bal:.8f} BTC | received: {recv:.8f} | sent: {sent:.8f}",
        f"  transactions: {data.get('n_tx', 0)}",
    ]
    txs = data.get("txs", []) or []
    if txs:
        lines.append("  recent transactions:")
        for tx in txs[:10]:
            outs = [o.get("addr", "?") for o in tx.get("out", []) if o.get("addr")]
            lines.append(
                f"    - {tx.get('time', '?')} hash={tx.get('hash', '?')[:20]}… -> {', '.join(outs[:4])}"
            )
    return ToolResult(ok=True, content="\n".join(lines))


def _eth(address: str, cfg: Config) -> ToolResult:
    key = cfg.etherscan_api_key or ""
    status, data = httpkit.get_json(
        "https://api.etherscan.io/api",
        params={
            "module": "account",
            "action": "balance",
            "address": address,
            "tag": "latest",
            "apikey": key,
        },
        timeout=25,
    )
    if status != 200 or not isinstance(data, dict):
        return ToolResult.error(f"etherscan returned HTTP {status}")
    if data.get("status") != "1" and data.get("message") not in ("OK",):
        msg = data.get("result") or data.get("message") or "unknown error"
        if "rate limit" in str(msg).lower() or "api key" in str(msg).lower():
            return ToolResult.error(f"etherscan: {msg}. Set ETHERSCAN_API_KEY for reliable access.")
    balance_eth = int(data.get("result", "0") or 0) / 1e18
    lines = [f"ETH address {address}:", f"  balance: {balance_eth:.6f} ETH"]

    tstatus, tdata = httpkit.get_json(
        "https://api.etherscan.io/api",
        params={
            "module": "account",
            "action": "txlist",
            "address": address,
            "startblock": 0,
            "endblock": 99999999,
            "page": 1,
            "offset": 10,
            "sort": "desc",
            "apikey": key,
        },
        timeout=25,
    )
    if tstatus == 200 and isinstance(tdata, dict) and isinstance(tdata.get("result"), list):
        txs = tdata["result"]
        lines.append(f"  recent transactions ({len(txs)} shown):")
        for tx in txs[:10]:
            val = int(tx.get("value", "0") or 0) / 1e18
            lines.append(
                f"    - {tx.get('timeStamp', '?')} {tx.get('from', '?')[:12]}… -> "
                f"{tx.get('to', '?')[:12]}… {val:.5f} ETH"
            )
    return ToolResult(ok=True, content="\n".join(lines))
