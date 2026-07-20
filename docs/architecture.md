# ChainScope — Architecture (Phase 1)

## What this project is

A two-part portfolio piece for a Wintermute DeFi Algorithmic Trading Internship application:
a Solidity contract on Sepolia, and a Python research toolkit that pulls real Uniswap V3 /
Aave data from mainnet (read-only, free RPC). Both halves are connected by one concept —
**TWAP** — rather than being two unrelated demos glued into one repo.

## Key decisions

### 1. Contract: TWAP Oracle (not a vault/AMM/token)

Chosen over the other options (liquidity vault, simple AMM, vault share token, position
tracker) because it's the one piece of infra a market maker actually touches: manipulation-
resistant pricing via cumulative price accumulation, checkpointed and read back over a
window. It's small enough to reason about fully (a hiring engineer can read the whole
contract in an interview) and it directly motivates the research experiment below — the
contract and the analytics aren't just co-located, they're about the same problem.

Mechanics: a cumulative-price accumulator (`price * timeElapsed`, Uniswap-V2-oracle style)
updated on each observation, with a `consult(window)` view that derives the average price
over an arbitrary look-back from two checkpoints. Custom errors for stale/insufficient
history, an `Observation` event, NatSpec throughout.

**Honest caveat, stated up front so it doesn't read as a gap later:** Sepolia has no real
volume, so this contract will be fed synthetic observations via the deployment/interaction
script, not live-arbitraged prices. It demonstrates the primitive correctly; it is not
"Sepolia's real price." The Python side gets its TWAP data from real mainnet Uniswap V3
pools instead (see below) — the link between the two is conceptual (both compute TWAP,
both care about the same manipulation/staleness tradeoffs), not a live data pipe. This
gets called out explicitly in the README so it reads as a deliberate scope decision, not
an oversight.

### 2. Research experiment: TWAP deviation monitor

Runs against real mainnet Uniswap V3 pools (e.g. USDC/WETH 0.05%) via `slot0` + the
pool's `observe()` oracle. Computes the pool's built-in TWAP over a window, computes an
independent TWAP from raw swap events via pandas, and reports the deviation between them
plus how it moves with pool liquidity/volume. This is the same question a TWAP execution
algo has to answer — "how much does the price I'd get differ from the oracle price, and
why" — which is the connective tissue back to the contract.

### 3. Protocols: Uniswap V3 + Aave v3 (mainnet reads only)

No transactions, no keys needed for this half — `eth_call` against public free-tier RPCs.
Uniswap V3: pool state (`slot0`, `liquidity`, `observe`), swap events for volume/fees.
Aave v3: `PoolDataProvider` reads for reserve data, utilization, rates.

### 4. Package layout (top-level `src/`, per CLAUDE.md's repo structure — not nested under
a `research/` wrapper)

```
src/
  protocols/     thin typed wrappers over web3.py Contract objects (UniswapV3Pool, AaveV3Reserve)
                 + ABI json. No business logic — just "give me clean data for this address."
  data/          collectors, one per source (uniswap_v3.py, aave.py, coingecko.py, gas.py).
                 Each collector takes a `RetryPolicy`/`ResponseCache` as a constructor arg
                 (composition, per CLAUDE.md's Architecture Principles) rather than
                 subclassing a shared base — same retry/caching behavior everywhere, but a
                 collector can be tested by injecting a fake client instead of a fake
                 subclass, and a mock client swaps in cleanly for "every network dependency
                 is replaceable with mocks."
  analysis/      metrics.py (rolling returns/vol, Sharpe, max drawdown, correlation),
                 twap.py, liquidity.py (utilization, price-impact approximation).
                 Takes DataFrames in, DataFrames/scalars out — never touches web3.py or
                 requests directly, so it stays testable with plain fixture data and has
                 zero knowledge that a network ever existed.
  visualization/ one function per chart type + a shared style module, so every figure
                 looks like it came from the same hand
  utils/         config (dataclass + python-dotenv — no pydantic-settings; nothing here
                 needs schema validation beyond "is this env var set"), plus the
                 RetryPolicy/ResponseCache helpers collectors compose in
tests/
```

Why composition over inheritance for collectors: four data sources means four places a
network call can fail, but a shared abstract base class would mean every collector *is a*
retrying-cacher (inheritance), which makes it awkward to test a collector's parsing logic
without also exercising the retry machinery. Instead each collector *has a* retry policy
and *has a* cache, injected — the behavior is still written once and reused everywhere, but
swapping in a no-op or fake policy for a unit test is a constructor argument, not a mock of
a parent class.

### 5. Data flow

```mermaid
flowchart LR
    subgraph Mainnet [Ethereum Mainnet - reads only]
        RPC[Free RPC]
        Etherscan[Etherscan v2 API]
        CoinGecko[CoinGecko free tier]
    end
    subgraph Research [Python toolkit - src/]
        Collectors[data/ collectors] --> Cache[(data/ cache)]
        Cache --> Analysis[analysis/]
        Analysis --> Viz[visualization/]
        Viz --> Figures[[figures/]]
        Notebooks[[notebooks/ - exploration]] -.reads.-> Cache
    end
    RPC --> Collectors
    Etherscan --> Collectors
    CoinGecko --> Collectors

    subgraph Sepolia [Sepolia - contract half]
        TWAPOracle[TWAPOracle.sol] --> ForgeTests[forge test]
        TWAPOracle --> Deploy[deploy + verify script]
    end
```

The two subgraphs are deliberately not wired together at the data layer — see the caveat
in decision 1.

### 6. Config & secrets

A single `Config` dataclass in `src/utils/config.py`, populated from `.env` via
`python-dotenv`. No `pydantic-settings` — nothing here needs schema validation beyond
"is this env var present," so a stdlib-adjacent dataclass is the whole solution.

### 7. Testing / CI

`forge test` for `contracts/`, `pytest` for `src/`, one GitHub Actions workflow with two
jobs (`python`, `contracts`) so either half can fail independently — done incrementally:
the `python` job landed in Phase 2, the `contracts` job in Phase 3, once there was
something in each half worth running.

## Deliberately deferred to later phases

- ABI files / contract wrapper implementations (Phase 4/7)
- The actual TWAP oracle contract and its tests (Phase 4/5)
- OpenZeppelin/forge-std are vendored as git submodules (`contracts/lib/`), not committed
  source — CI checks out with `submodules: recursive`
