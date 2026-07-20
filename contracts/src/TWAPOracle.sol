// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

/// @title TWAPOracle
/// @author ChainScope
/// @notice A push-based, manipulation-resistant time-weighted average price oracle.
/// @dev Mechanically this is Uniswap V2's cumulative-price oracle pattern (accumulate
///      price * timeElapsed on every update, derive an average by diffing two
///      checkpoints) generalized to an arbitrary look-back window: instead of one
///      "since-last-update" average, a fixed-size ring buffer of checkpoints lets
///      `consult` answer "what was the TWAP over the last N seconds?" for any N up to
///      the buffer's current history depth.
///
///      Two things are deliberately out of scope, and that's a scope decision, not an
///      oversight:
///      - This oracle does not source prices itself; an authorized `reporter` pushes
///        them via `record`. A real DEX-embedded oracle (Uniswap V2/V3) accumulates on
///        every swap, permissionlessly and continuously - that requires the oracle to
///        BE the AMM. Decoupling data-sourcing from TWAP math keeps this contract
///        focused on the oracle mechanism, at the cost of introducing a trust
///        assumption in the reporter (see docs/architecture.md for how this is used).
///      - Like Uniswap V2's oracle, timestamps are truncated to uint32 and arithmetic
///        is not wraparound-safe past block.timestamp == 2^32 (the year 2106). Uniswap
///        V2 has shipped with this same accepted limitation since 2020.
contract TWAPOracle {
    struct Observation {
        uint32 timestamp;
        uint256 priceCumulative;
    }

    /// @notice Reverts when a non-reporter calls a reporter-only function.
    error Unauthorized(address caller);
    /// @notice Reverts when `record` is called with a zero price.
    error InvalidPrice();
    /// @notice Reverts when `record` is called before `minInterval` has elapsed.
    error TooSoon(uint32 minInterval, uint32 elapsed);
    /// @notice Reverts when `consult` is asked for a window the buffer can't yet cover.
    /// @param requestedSecondsAgo The window that was asked for.
    /// @param availableSecondsAgo The longest window currently available (0 if <2 observations).
    error InsufficientHistory(uint32 requestedSecondsAgo, uint32 availableSecondsAgo);

    /// @notice Emitted every time a new price observation is recorded.
    event Reported(uint16 indexed index, uint256 price, uint256 priceCumulative, uint32 timestamp);
    /// @notice Emitted when the authorized reporter address changes.
    event ReporterUpdated(address indexed previousReporter, address indexed newReporter);

    /// @notice The only address allowed to call `record`.
    address public reporter;
    /// @notice Ring buffer capacity - the maximum number of observations retained.
    uint16 public immutable cardinality;
    /// @notice Minimum seconds required between two `record` calls.
    uint32 public immutable minInterval;

    Observation[] private observations;
    uint16 private latestIndex;

    /// @notice Cumulative price as of `lastTimestamp` (price * seconds, summed since deployment).
    uint256 public priceCumulative;
    /// @notice Timestamp of the most recent recorded observation.
    uint32 public lastTimestamp;
    /// @notice The price supplied in the most recent `record` call.
    uint256 private lastPrice;

    modifier onlyReporter() {
        if (msg.sender != reporter) revert Unauthorized(msg.sender);
        _;
    }

    /// @param _reporter Address authorized to call `record`.
    /// @param _cardinality Ring buffer size; caps the maximum queryable window's resolution.
    /// @param _minInterval Minimum seconds between reports (rate-limits the reporter).
    constructor(address _reporter, uint16 _cardinality, uint32 _minInterval) {
        if (_reporter == address(0)) revert Unauthorized(address(0));
        reporter = _reporter;
        cardinality = _cardinality;
        minInterval = _minInterval;
    }

    /// @notice Transfers reporting rights to a new address.
    /// @param newReporter The address that will be authorized to call `record` next.
    function setReporter(address newReporter) external onlyReporter {
        emit ReporterUpdated(reporter, newReporter);
        reporter = newReporter;
    }

    /// @notice Records a new price observation, accumulating price * timeElapsed since
    ///         the previous call.
    /// @dev The first call seeds the buffer (priceCumulative stays 0, nothing to average
    ///      against yet); every call after that extends the accumulator.
    /// @param price The current price, reporter-supplied and not validated on-chain.
    function record(uint256 price) external onlyReporter {
        if (price == 0) revert InvalidPrice();

        uint32 nowTs = uint32(block.timestamp % 2 ** 32);

        if (lastTimestamp != 0) {
            uint32 elapsed = nowTs - lastTimestamp;
            if (elapsed < minInterval) revert TooSoon(minInterval, elapsed);
            // The PREVIOUS price was in effect for the interval that just elapsed.
            priceCumulative += lastPrice * elapsed;
        }

        lastTimestamp = nowTs;
        lastPrice = price;

        uint16 count = uint16(observations.length);
        if (count < cardinality) {
            observations.push(Observation(nowTs, priceCumulative));
            latestIndex = count;
        } else {
            latestIndex = (latestIndex + 1) % cardinality;
            observations[latestIndex] = Observation(nowTs, priceCumulative);
        }

        emit Reported(latestIndex, price, priceCumulative, nowTs);
    }

    /// @notice Computes the time-weighted average price over the trailing `secondsAgo`
    ///         window, ending at `lastTimestamp`.
    /// @dev Finds the latest stored checkpoint at or before (lastTimestamp - secondsAgo)
    ///      and averages between it and the newest checkpoint. Because checkpoints are
    ///      discrete, the realized window is `lastTimestamp - checkpoint.timestamp`,
    ///      which is >= secondsAgo but not necessarily exact - the same granularity
    ///      tradeoff as Uniswap V2's periodic oracle, without V3's binary-search
    ///      interpolation between arbitrary points.
    /// @param secondsAgo How far back the window should reach.
    /// @return twap The average price over the realized window.
    function consult(uint32 secondsAgo) external view returns (uint256 twap) {
        uint16 count = uint16(observations.length);
        if (count < 2 || secondsAgo == 0) revert InsufficientHistory(secondsAgo, 0);
        if (secondsAgo > lastTimestamp) revert InsufficientHistory(secondsAgo, lastTimestamp);

        uint32 targetTimestamp = lastTimestamp - secondsAgo;
        uint16 oldestIndex = count < cardinality ? 0 : (latestIndex + 1) % cardinality;
        Observation memory checkpoint = observations[oldestIndex];

        if (targetTimestamp < checkpoint.timestamp) {
            revert InsufficientHistory(secondsAgo, lastTimestamp - checkpoint.timestamp);
        }

        for (uint16 i = 1; i < count; i++) {
            Observation memory obs = observations[(oldestIndex + i) % cardinality];
            if (obs.timestamp > targetTimestamp) break;
            checkpoint = obs;
        }

        uint32 elapsed = lastTimestamp - checkpoint.timestamp;
        if (elapsed == 0) revert InsufficientHistory(secondsAgo, 0);

        twap = (priceCumulative - checkpoint.priceCumulative) / elapsed;
    }

    /// @notice The longest window currently answerable by `consult`.
    /// @return secondsAgo 0 if fewer than 2 observations exist yet.
    function availableWindow() external view returns (uint32 secondsAgo) {
        uint16 count = uint16(observations.length);
        if (count < 2) return 0;
        uint16 oldestIndex = count < cardinality ? 0 : (latestIndex + 1) % cardinality;
        secondsAgo = lastTimestamp - observations[oldestIndex].timestamp;
    }

    /// @notice The number of observations currently stored (<= cardinality).
    function observationsCount() external view returns (uint16) {
        return uint16(observations.length);
    }

    /// @notice The most recently recorded observation.
    function latestObservation() external view returns (Observation memory) {
        return observations[latestIndex];
    }
}
