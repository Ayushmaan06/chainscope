// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import {Script, console2} from "forge-std/Script.sol";
import {TWAPOracle} from "../src/TWAPOracle.sol";

/// @notice Deploys TWAPOracle to whatever chain `--rpc-url` points at.
/// @dev Per docs/architecture.md, Sepolia has no organic price activity to accumulate,
///      so the deployer is set as its own `reporter` — observations are seeded manually
///      afterwards (a separate interaction step), not sourced from a live DEX. Cardinality
///      and min interval are overridable via env so the same script works for a fast local
///      demo (small interval) and a more realistic Sepolia deployment, without editing code.
contract DeployTWAPOracle is Script {
    function run() external returns (TWAPOracle oracle) {
        uint256 deployerKey = vm.envUint("SEPOLIA_DEPLOYER_PRIVATE_KEY");
        address deployer = vm.addr(deployerKey);

        uint16 cardinality = uint16(vm.envOr("TWAP_CARDINALITY", uint256(24)));
        uint32 minInterval = uint32(vm.envOr("TWAP_MIN_INTERVAL", uint256(60)));

        vm.startBroadcast(deployerKey);
        oracle = new TWAPOracle(deployer, cardinality, minInterval);
        vm.stopBroadcast();

        console2.log("TWAPOracle deployed at:", address(oracle));
        console2.log("Reporter (deployer):", deployer);
        console2.log("Cardinality:", cardinality);
        console2.log("Min interval (s):", minInterval);
    }
}
