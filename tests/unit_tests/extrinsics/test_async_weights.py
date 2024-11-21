import pytest
from bittensor.core import async_subtensor
from bittensor_wallet import Wallet
from bittensor.core.extrinsics import async_weights


@pytest.fixture(autouse=True)
def subtensor(mocker):
    fake_async_substrate = mocker.AsyncMock(
        autospec=async_subtensor.AsyncSubstrateInterface
    )
    mocker.patch.object(
        async_subtensor, "AsyncSubstrateInterface", return_value=fake_async_substrate
    )
    return async_subtensor.AsyncSubtensor()


@pytest.mark.asyncio
async def test_do_commit_weights_success(subtensor, mocker):
    """Tests _do_commit_weights when the commit is successful."""
    # Preps
    fake_wallet = mocker.Mock(autospec=Wallet)
    fake_netuid = 1
    fake_commit_hash = "test_hash"

    fake_call = mocker.AsyncMock()
    fake_extrinsic = mocker.AsyncMock()
    fake_response = mocker.Mock()

    async def fake_is_success():
        return True

    fake_response.is_success = fake_is_success()
    fake_response.process_events = mocker.AsyncMock()

    mocker.patch.object(subtensor.substrate, "compose_call", return_value=fake_call)
    mocker.patch.object(
        subtensor.substrate, "create_signed_extrinsic", return_value=fake_extrinsic
    )
    mocker.patch.object(
        subtensor.substrate, "submit_extrinsic", return_value=fake_response
    )

    # Call
    result, message = await async_weights._do_commit_weights(
        subtensor=subtensor,
        wallet=fake_wallet,
        netuid=fake_netuid,
        commit_hash=fake_commit_hash,
        wait_for_inclusion=True,
        wait_for_finalization=True,
    )

    # Asserts
    assert result is True
    assert message is None


@pytest.mark.asyncio
async def test_do_commit_weights_failure(subtensor, mocker):
    """Tests _do_commit_weights when the commit fails."""
    # Preps
    fake_wallet = mocker.Mock(autospec=Wallet)
    fake_netuid = 1
    fake_commit_hash = "test_hash"

    fake_call = mocker.AsyncMock()
    fake_extrinsic = mocker.AsyncMock()

    async def fake_is_success():
        return False

    fake_response = mocker.Mock()
    fake_response.is_success = fake_is_success()
    fake_response.process_events = mocker.AsyncMock()
    fake_response.error_message = "Error occurred"

    mocked_format_error_message = mocker.Mock(return_value="Formatted error")
    mocker.patch.object(
        async_weights, "format_error_message", mocked_format_error_message
    )

    mocker.patch.object(subtensor.substrate, "compose_call", return_value=fake_call)
    mocker.patch.object(
        subtensor.substrate, "create_signed_extrinsic", return_value=fake_extrinsic
    )
    mocker.patch.object(
        subtensor.substrate, "submit_extrinsic", return_value=fake_response
    )

    # Call
    result, message = await async_weights._do_commit_weights(
        subtensor=subtensor,
        wallet=fake_wallet,
        netuid=fake_netuid,
        commit_hash=fake_commit_hash,
        wait_for_inclusion=True,
        wait_for_finalization=True,
    )

    # Asserts
    assert result is False
    mocked_format_error_message.assert_called_once_with(
        fake_response.error_message, substrate=subtensor.substrate
    )
    assert message == "Formatted error"


@pytest.mark.asyncio
async def test_do_commit_weights_no_waiting(subtensor, mocker):
    """Tests _do_commit_weights when not waiting for inclusion or finalization."""
    # Preps
    fake_wallet = mocker.Mock(autospec=Wallet)
    fake_netuid = 1
    fake_commit_hash = "test_hash"

    fake_call = mocker.AsyncMock()
    fake_extrinsic = mocker.AsyncMock()
    fake_response = mocker.Mock()

    mocker.patch.object(subtensor.substrate, "compose_call", return_value=fake_call)
    mocker.patch.object(
        subtensor.substrate, "create_signed_extrinsic", return_value=fake_extrinsic
    )
    mocker.patch.object(
        subtensor.substrate, "submit_extrinsic", return_value=fake_response
    )

    # Call
    result, message = await async_weights._do_commit_weights(
        subtensor=subtensor,
        wallet=fake_wallet,
        netuid=fake_netuid,
        commit_hash=fake_commit_hash,
        wait_for_inclusion=False,
        wait_for_finalization=False,
    )

    # Asserts
    assert result is True
    assert message is None


@pytest.mark.asyncio
async def test_do_commit_weights_exception(subtensor, mocker):
    """Tests _do_commit_weights when an exception is raised."""
    # Preps
    fake_wallet = mocker.Mock(autospec=Wallet)
    fake_netuid = 1
    fake_commit_hash = "test_hash"

    mocker.patch.object(
        subtensor.substrate,
        "compose_call",
        side_effect=Exception("Unexpected exception"),
    )

    # Call
    with pytest.raises(Exception, match="Unexpected exception"):
        await async_weights._do_commit_weights(
            subtensor=subtensor,
            wallet=fake_wallet,
            netuid=fake_netuid,
            commit_hash=fake_commit_hash,
            wait_for_inclusion=True,
            wait_for_finalization=True,
        )


@pytest.mark.asyncio
async def test_commit_weights_extrinsic_success(subtensor, mocker):
    """Tests commit_weights_extrinsic when the commit is successful."""
    # Preps
    fake_wallet = mocker.Mock(autospec=Wallet)
    fake_netuid = 1
    fake_commit_hash = "test_hash"

    mocked_do_commit_weights = mocker.patch.object(
        async_weights, "_do_commit_weights", return_value=(True, None)
    )

    # Call
    result, message = await async_weights.commit_weights_extrinsic(
        subtensor=subtensor,
        wallet=fake_wallet,
        netuid=fake_netuid,
        commit_hash=fake_commit_hash,
        wait_for_inclusion=True,
        wait_for_finalization=True,
    )

    # Asserts
    mocked_do_commit_weights.assert_called_once_with(
        subtensor=subtensor,
        wallet=fake_wallet,
        netuid=fake_netuid,
        commit_hash=fake_commit_hash,
        wait_for_inclusion=True,
        wait_for_finalization=True,
    )
    assert result is True
    assert message == "Successfully committed weights."


@pytest.mark.asyncio
async def test_commit_weights_extrinsic_failure(subtensor, mocker):
    """Tests commit_weights_extrinsic when the commit fails."""
    # Preps
    fake_wallet = mocker.Mock(autospec=Wallet)
    fake_netuid = 1
    fake_commit_hash = "test_hash"

    mocked_do_commit_weights = mocker.patch.object(
        async_weights, "_do_commit_weights", return_value=(False, "Commit failed.")
    )

    # Call
    result, message = await async_weights.commit_weights_extrinsic(
        subtensor=subtensor,
        wallet=fake_wallet,
        netuid=fake_netuid,
        commit_hash=fake_commit_hash,
        wait_for_inclusion=True,
        wait_for_finalization=True,
    )

    # Asserts
    mocked_do_commit_weights.assert_called_once_with(
        subtensor=subtensor,
        wallet=fake_wallet,
        netuid=fake_netuid,
        commit_hash=fake_commit_hash,
        wait_for_inclusion=True,
        wait_for_finalization=True,
    )
    assert result is False
    assert message == "Commit failed."
