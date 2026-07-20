// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import {Test} from "forge-std/Test.sol";
import {TWAPOracle} from "../src/TWAPOracle.sol";

contract TWAPOracleTest is Test {
    TWAPOracle internal oracle;
    address internal reporter = address(0xBEEF);
    address internal stranger = address(0xC0FFEE);

    function setUp() public {
        oracle = new TWAPOracle(reporter, 8, 0);
    }

    // ---------------------------------------------------------------------
    // Construction
    // ---------------------------------------------------------------------

    function test_RevertWhen_ConstructedWithZeroReporter() public {
        vm.expectRevert(abi.encodeWithSelector(TWAPOracle.Unauthorized.selector, address(0)));
        new TWAPOracle(address(0), 8, 0);
    }

    function test_RevertWhen_ConstructedWithZeroCardinality() public {
        vm.expectRevert(TWAPOracle.InvalidCardinality.selector);
        new TWAPOracle(reporter, 0, 0);
    }

    // ---------------------------------------------------------------------
    // Access control
    // ---------------------------------------------------------------------

    function test_RevertWhen_StrangerRecords() public {
        vm.prank(stranger);
        vm.expectRevert(abi.encodeWithSelector(TWAPOracle.Unauthorized.selector, stranger));
        oracle.record(100);
    }

    function test_RevertWhen_StrangerSetsReporter() public {
        vm.prank(stranger);
        vm.expectRevert(abi.encodeWithSelector(TWAPOracle.Unauthorized.selector, stranger));
        oracle.setReporter(stranger);
    }

    function test_SetReporter_TransfersRightsAndEmitsEvent() public {
        vm.prank(reporter);
        vm.expectEmit(true, true, false, false);
        emit TWAPOracle.ReporterUpdated(reporter, stranger);
        oracle.setReporter(stranger);

        assertEq(oracle.reporter(), stranger);

        // Old reporter can no longer record; new one can.
        vm.prank(reporter);
        vm.expectRevert(abi.encodeWithSelector(TWAPOracle.Unauthorized.selector, reporter));
        oracle.record(100);

        vm.prank(stranger);
        oracle.record(100);
    }

    // ---------------------------------------------------------------------
    // record() input validation
    // ---------------------------------------------------------------------

    function test_RevertWhen_RecordingZeroPrice() public {
        vm.prank(reporter);
        vm.expectRevert(TWAPOracle.InvalidPrice.selector);
        oracle.record(0);
    }

    function test_RevertWhen_RecordingTooSoon() public {
        TWAPOracle rateLimited = new TWAPOracle(reporter, 8, 60);

        vm.warp(1000);
        vm.prank(reporter);
        rateLimited.record(100);

        vm.warp(1030); // only 30s later, minInterval is 60s
        vm.prank(reporter);
        vm.expectRevert(abi.encodeWithSelector(TWAPOracle.TooSoon.selector, 60, 30));
        rateLimited.record(200);
    }

    function test_FirstRecord_SeedsBufferWithZeroCumulative() public {
        vm.warp(1000);
        vm.prank(reporter);
        oracle.record(100);

        assertEq(oracle.priceCumulative(), 0);
        assertEq(oracle.observationsCount(), 1);
        assertEq(oracle.availableWindow(), 0); // still <2 observations
    }

    // ---------------------------------------------------------------------
    // Ring buffer wraparound
    // ---------------------------------------------------------------------

    function test_RingBuffer_OverwritesOldestWhenFull() public {
        TWAPOracle small = new TWAPOracle(reporter, 3, 0);

        vm.startPrank(reporter);
        for (uint256 i = 0; i < 5; i++) {
            vm.warp(1000 + i * 100);
            small.record(100 * (i + 1));
        }
        vm.stopPrank();

        // Buffer capped at cardinality even though 5 reports were made.
        assertEq(small.observationsCount(), 3);

        // Oldest surviving checkpoint is from the 3rd report (t=1200), so the
        // longest available window is now (1400 - 1200) = 200s, not 400s.
        assertEq(small.availableWindow(), 200);

        vm.expectRevert(abi.encodeWithSelector(TWAPOracle.InsufficientHistory.selector, 400, 200));
        small.consult(400);
    }

    // ---------------------------------------------------------------------
    // consult()
    // ---------------------------------------------------------------------

    function test_RevertWhen_ConsultingWithFewerThanTwoObservations() public {
        vm.prank(reporter);
        oracle.record(100);

        vm.expectRevert(abi.encodeWithSelector(TWAPOracle.InsufficientHistory.selector, 10, 0));
        oracle.consult(10);
    }

    function test_RevertWhen_ConsultingZeroWindow() public {
        vm.startPrank(reporter);
        oracle.record(100);
        vm.warp(block.timestamp + 100);
        oracle.record(200);
        vm.stopPrank();

        vm.expectRevert(abi.encodeWithSelector(TWAPOracle.InsufficientHistory.selector, 0, 0));
        oracle.consult(0);
    }

    function test_RevertWhen_WindowExceedsAvailableHistory() public {
        vm.startPrank(reporter);
        vm.warp(1000);
        oracle.record(100);
        vm.warp(1100);
        oracle.record(200);
        vm.stopPrank();

        vm.expectRevert(abi.encodeWithSelector(TWAPOracle.InsufficientHistory.selector, 500, 100));
        oracle.consult(500);
    }

    function test_Consult_AveragesWeightedByTimeElapsed() public {
        vm.startPrank(reporter);
        vm.warp(1000);
        oracle.record(100);
        vm.warp(1100);
        oracle.record(200);
        vm.warp(1200);
        oracle.record(300);
        vm.stopPrank();

        assertEq(oracle.consult(200), 150);
        assertEq(oracle.availableWindow(), 200);
    }

    function test_Consult_UsesClosestCheckpointAtOrBeforeTarget() public {
        vm.startPrank(reporter);
        vm.warp(1000);
        oracle.record(100); // checkpoint A: t=1000, cum=0
        vm.warp(1100);
        oracle.record(200); // checkpoint B: t=1100, cum=10000
        vm.warp(1300);
        oracle.record(300); // checkpoint C: t=1300, cum=10000+200*200=50000
        vm.stopPrank();

        // Window of 150 targets t=1150, which falls between checkpoints B (1100)
        // and C (1300). The realized window anchors at B, not an interpolated point.
        uint256 twap = oracle.consult(150);
        assertEq(twap, (50000 - 10000) / (1300 - 1100));
    }

    // ---------------------------------------------------------------------
    // Fuzz: the core accumulator formula holds for arbitrary valid inputs
    // ---------------------------------------------------------------------

    function testFuzz_ConsultMatchesWeightedAverageOfTwoIntervals(
        uint96 priceA,
        uint96 priceB,
        uint32 gapA,
        uint32 gapB
    ) public {
        priceA = uint96(bound(priceA, 1, 1e18));
        priceB = uint96(bound(priceB, 1, 1e18));
        gapA = uint32(bound(gapA, 1, 30 days));
        gapB = uint32(bound(gapB, 1, 30 days));

        uint256 start = 1_700_000_000;
        vm.startPrank(reporter);
        vm.warp(start);
        oracle.record(priceA);
        vm.warp(start + gapA);
        oracle.record(priceB);
        vm.warp(start + gapA + gapB);
        oracle.record(1); // third report just to create a checkpoint boundary
        vm.stopPrank();

        uint256 expected = (uint256(priceA) * gapA + uint256(priceB) * gapB) / (gapA + gapB);
        assertEq(oracle.consult(gapA + gapB), expected);
    }
}
