// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import {Test} from "forge-std/Test.sol";
import {TWAPOracle} from "../src/TWAPOracle.sol";

/// @dev Single smoke test proving the contract wires together correctly. The full
///      edge-case/fuzz/error suite is built in Phase 5.
contract TWAPOracleTest is Test {
    TWAPOracle internal oracle;
    address internal reporter = address(0xBEEF);

    function setUp() public {
        oracle = new TWAPOracle(reporter, 8, 0);
    }

    function test_ConsultAveragesWeightedByTimeElapsed() public {
        vm.warp(1000);
        vm.prank(reporter);
        oracle.record(100);

        vm.warp(1100);
        vm.prank(reporter);
        oracle.record(200);

        vm.warp(1200);
        vm.prank(reporter);
        oracle.record(300);

        assertEq(oracle.consult(200), 150);
        assertEq(oracle.availableWindow(), 200);
    }
}
