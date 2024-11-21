"""This module provides functionality for setting weights on the Bittensor network."""

from typing import TYPE_CHECKING, Optional


from bittensor.utils import format_error_message
from bittensor.utils.btlogging import logging

if TYPE_CHECKING:
    from bittensor_wallet import Wallet
    from bittensor.core.async_subtensor import AsyncSubtensor


async def _do_commit_weights(
    subtensor: "AsyncSubtensor",
    wallet: "Wallet",
    netuid: int,
    commit_hash: str,
    wait_for_inclusion: bool = False,
    wait_for_finalization: bool = False,
) -> tuple[bool, Optional[str]]:
    """
    Internal method to send a transaction to the Bittensor blockchain, committing the hash of a neuron's weights.
    This method constructs and submits the transaction, handling retries and blockchain communication.

    Args:
        subtensor (bittensor.core.subtensor.Subtensor): The subtensor instance used for blockchain interaction.
        wallet (bittensor_wallet.Wallet): The wallet associated with the neuron committing the weights.
        netuid (int): The unique identifier of the subnet.
        commit_hash (str): The hash of the neuron's weights to be committed.
        wait_for_inclusion (bool): Waits for the transaction to be included in a block.
        wait_for_finalization (bool): Waits for the transaction to be finalized on the blockchain.

    Returns:
        tuple[bool, Optional[str]]: A tuple containing a success flag and an optional error message.

    This method ensures that the weight commitment is securely recorded on the Bittensor blockchain, providing a verifiable record of the neuron's weight distribution at a specific point in time.
    """
    call = await subtensor.substrate.compose_call(
        call_module="SubtensorModule",
        call_function="commit_weights",
        call_params={
            "netuid": netuid,
            "commit_hash": commit_hash,
        },
    )
    extrinsic = await subtensor.substrate.create_signed_extrinsic(
        call=call,
        keypair=wallet.hotkey,
    )
    response = await subtensor.substrate.submit_extrinsic(
        substrate=subtensor.substrate,
        extrinsic=extrinsic,
        wait_for_inclusion=wait_for_inclusion,
        wait_for_finalization=wait_for_finalization,
    )

    if not wait_for_finalization and not wait_for_inclusion:
        return True, None

    await response.process_events()
    if await response.is_success:
        return True, None
    else:
        return False, format_error_message(
            response.error_message, substrate=subtensor.substrate
        )


async def commit_weights_extrinsic(
    subtensor: "AsyncSubtensor",
    wallet: "Wallet",
    netuid: int,
    commit_hash: str,
    wait_for_inclusion: bool = False,
    wait_for_finalization: bool = False,
) -> tuple[bool, str]:
    """
    Commits a hash of the neuron's weights to the Bittensor blockchain using the provided wallet.
    This function is a wrapper around the `do_commit_weights` method.

    Args:
        subtensor (bittensor.core.subtensor.Subtensor): The subtensor instance used for blockchain interaction.
        wallet (bittensor_wallet.Wallet): The wallet associated with the neuron committing the weights.
        netuid (int): The unique identifier of the subnet.
        commit_hash (str): The hash of the neuron's weights to be committed.
        wait_for_inclusion (bool): Waits for the transaction to be included in a block.
        wait_for_finalization (bool): Waits for the transaction to be finalized on the blockchain.

    Returns:
        tuple[bool, str]: ``True`` if the weight commitment is successful, False otherwise. And `msg`, a string
        value describing the success or potential error.

    This function provides a user-friendly interface for committing weights to the Bittensor blockchain, ensuring proper error handling and user interaction when required.
    """

    success, error_message = await _do_commit_weights(
        subtensor=subtensor,
        wallet=wallet,
        netuid=netuid,
        commit_hash=commit_hash,
        wait_for_inclusion=wait_for_inclusion,
        wait_for_finalization=wait_for_finalization,
    )

    if success:
        success_message = "Successfully committed weights."
        logging.info(success_message)
        return True, success_message
    else:
        logging.error(f"Failed to commit weights: {error_message}")
        return False, error_message
