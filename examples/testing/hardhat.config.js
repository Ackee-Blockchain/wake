/** @type import('hardhat/config').HardhatUserConfig */
module.exports = {
    solidity: "0.8.17",
    networks: {
        hardhat: {
            initialBaseFeePerGas: 0,
            gasPrice: 0,
        }
    }
};
