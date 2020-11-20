from bittensor.subtensor import SubstrateWSInterface, Keypair
import netaddr

class WSClient:
    def __init__(self, socket : str, keypair: Keypair):
        host, port = socket.split(":")

        self.substrate = SubstrateWSInterface(
            host=host,
            port=int(port),
            address_type = 42,
            type_registry_preset = 'substrate-node-template'
        )

        self.keypair = keypair

    '''
    PRIVATE METHODS
    '''

    def __int_to_ip(self, int_val):
        return str(netaddr.IPAddress(int_val))

    def __ip_to_int(self, str_val):
        return int(netaddr.IPAddress(str_val))


    '''
    PUBLIC METHODS
    '''


    def connect(self):
        self.substrate.connect()

    def is_connected(self):
        return self.substrate.is_connected()

    async def subscribe(self, ip: str, port: int):
        params = {'ip': self.__ip_to_int(ip),
                  'port': port, 'ip_type': 4}

        call = await self.substrate.compose_call(
            call_module='SubtensorModule',
            call_function='subscribe',
            call_params=params
        )

        extrinsic = await self.substrate.create_signed_extrinsic(call=call, keypair=keypair)
        await self.substrate.submit_extrinsic(extrinsic, wait_for_inclusion=False)  # Waiting for inclusion and other does not work

    async def unsubscribe(self, keypair=None):
        if not keypair:
            keypair = self.keypair

        call = await self.substrate.compose_call(
            call_module='SubtensorModule',
            call_function='unsubscribe'
        )

        extrinsic = await self.substrate.create_signed_extrinsic(call=call, keypair=keypair)
        await self.substrate.submit_extrinsic(extrinsic, wait_for_inclusion=False)

    async def get_peers(self):
        peers = await self.substrate.iterate_map(
            module='SubtensorModule',
            storage_function='Peers')

        return peers

    async def get_balance(self, address):
        result  = await self.substrate.get_runtime_state(
            module='System',
            storage_function='Account',
            params=[address],
            block_hash=None
        )

        balance_info = result.get('result')

        return balance_info['data']['free']

    async def add_stake(self, amount, keypair):
        call = await self.substrate.compose_call(
            call_module='SubtensorModule',
            call_function='add_stake',
            call_params={'stake_amount': amount}
        )

        extrinsic = await self.substrate.create_signed_extrinsic(call=call, keypair=keypair)
        await self.substrate.submit_extrinsic(extrinsic, wait_for_inclusion=False)

    async def get_stake(self):
        result = await self.substrate.iterate_map(
            module='SubtensorModule',
            storage_function='Stake')
        return result

    async def set_weights(self, destinations, values, keypair):
        call = await self.substrate.compose_call(
            call_module = 'SubtensorModule',
            call_function = 'set_weights',
            call_params = {'dests': destinations, 'values': values}
        )

        extrinsic = await self.substrate.create_signed_extrinsic(call=call, keypair=keypair)
        await self.substrate.submit_extrinsic(extrinsic, wait_for_inclusion=False)


    async def weight_keys(self):
        result = await self.substrate.iterate_map(
            module='SubtensorModule',
            storage_function='Weight_keys',
        )

        return result

    async def weight_vals(self):
        result = await self.substrate.iterate_map(
            module='SubtensorModule',
            storage_function='Weight_vals',
        )

        return result

    async def emit(self, keypair):
        call = await self.substrate.compose_call(
            call_module='SubtensorModule',
            call_function='emit'
        )
        extrinsic = await self. substrate.create_signed_extrinsic(call=call, keypair=keypair)
        await self.substrate.submit_extrinsic(extrinsic, wait_for_inclusion=False)






