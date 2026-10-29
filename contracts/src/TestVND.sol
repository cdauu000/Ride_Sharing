// SPDX-License-Identifier: MIT
pragma solidity ^0.8.30;

import {ERC20} from "@openzeppelin/contracts/token/ERC20/ERC20.sol";
import {Ownable} from "@openzeppelin/contracts/access/Ownable.sol";

/// @notice Research credits only: one indivisible base unit represents 1 VND.
/// @dev No redemption or fiat backing. Only the test operator can issue credits.
contract TestVND is ERC20, Ownable {
    constructor(address operator) ERC20("Research VND Credit", "tVND") Ownable(operator) {}

    function decimals() public pure override returns (uint8) { return 0; }

    function mint(address to, uint256 amountVnd) external onlyOwner {
        _mint(to, amountVnd);
    }
}
