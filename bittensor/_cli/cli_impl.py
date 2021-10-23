# The MIT License (MIT)
# Copyright © 2021 Yuma Rao

# Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated 
# documentation files (the “Software”), to deal in the Software without restriction, including without limitation 
# the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, 
# and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in all copies or substantial portions of 
# the Software.

# THE SOFTWARE IS PROVIDED “AS IS”, WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO
# THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL 
# THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION 
# OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER 
# DEALINGS IN THE SOFTWARE.

import bittensor

import sys
import time
import torch
from bittensor._dendrite import dendrite
import bittensor.utils.codes as code_utils
from tqdm import tqdm
from rich.align import Align
from rich.console import Console
from rich.table import Table
from rich.console import Console
from rich.prompt import Confirm

class CLI:
    """
    Implementation of the CLI class, which handles the coldkey, hotkey and money transfer 
    """
    def __init__(self, config: 'bittensor.Config' ):
        r""" Initialized a bittensor.CLI object.
            Args:
                config (:obj:`bittensor.Config`, `required`): 
                    bittensor.cli.config()
        """
        self.config = config

    def run ( self ):
        """ Execute the command from config 
        """
        if self.config.command == "transfer":
            self.transfer ()
        elif self.config.command == "unstake":
            self.unstake()
        elif self.config.command == "stake":
            self.stake()
        elif self.config.command == "overview":
            self.overview()
        elif self.config.command == "new_coldkey":
            self.create_new_coldkey()
        elif self.config.command == "new_hotkey":
            self.create_new_hotkey()
        elif self.config.command == "regen_coldkey":
            self.regen_coldkey()
        elif self.config.command == "regen_hotkey":
            self.regen_hotkey()

    def create_new_coldkey ( self ):
        r""" Creates a new coldkey under this wallet.
        """
        wallet = bittensor.wallet(config = self.config)
        wallet.create_new_coldkey( n_words = self.config.n_words, use_password = self.config.use_password, overwrite = False)   

    def create_new_hotkey ( self ):
        r""" Creates a new hotke under this wallet.
        """
        wallet = bittensor.wallet(config = self.config)
        wallet.create_new_hotkey( n_words = self.config.n_words, use_password = self.config.use_password, overwrite = False)   

    def regen_coldkey ( self ):
        r""" Creates a new coldkey under this wallet.
        """
        wallet = bittensor.wallet(config = self.config)
        wallet.regenerate_coldkey( mnemonic = self.config.mnemonic, use_password = self.config.use_password, overwrite = False )

    def regen_hotkey ( self ):
        r""" Creates a new coldkey under this wallet.
        """
        wallet = bittensor.wallet(config = self.config)
        wallet.regenerate_hotkey( mnemonic = self.config.mnemonic, use_password = self.config.use_password, overwrite = False)

    def transfer( self ):
        r""" Transfers token of amount to destination.
        """
        console = Console()
        wallet = bittensor.wallet( config = self.config )
        subtensor = bittensor.subtensor( config = self.config )

        # Unlock wallet coldkey.
        wallet.coldkey

        # Check that we have enough balance.
        transfer_balance = bittensor.Balance.from_float( self.config.amount )
        with console.status(":satellite: Checking Balance..."):
            account_balance = subtensor.get_balance( wallet.coldkey.ss58_address )
        if account_balance < transfer_balance:
            console.print(":cross_mark:[red]Not enough balance[/red]:[green]{}[/green] to transfer:[blue]{}[/blue]".format( account_balance, transfer_balance ))
            sys.exit()

        # Ask before moving on.
        do_transfer = Confirm.ask("Do you want to transfer:[green]{}[/green] from:[blue]{}:{}[/blue] to:[green]{}[/green]?".format( transfer_balance, self.config.wallet.name, wallet.coldkey.ss58_address, self.config.dest ) )
        if not do_transfer:
            sys.exit()

        with console.status(":satellite: Transferring..."):
            with subtensor.substrate as substrate:
                call = substrate.compose_call(
                    call_module='Balances',
                    call_function='transfer',
                    call_params={
                        'dest': self.config.dest, 
                        'value': transfer_balance.rao
                    }
                )
                extrinsic = substrate.create_signed_extrinsic( call = call, keypair = wallet.coldkey )
                response = substrate.submit_extrinsic( extrinsic, wait_for_inclusion = False, wait_for_finalization = True )
                response.process_events()
                if response.is_success:
                    console.print(":white_heavy_check_mark:[green]Finalized[/green]")
                else:
                    console.print(":cross_mark:[red]Failed[/red]: error:{}".format(response.error_message))

        if response.is_success:
            with console.status(":satellite: Checking Balance..."):
                new_balance = subtensor.get_balance( wallet.coldkey.ss58_address )
                console.print("Balance:[blue]{}[/blue] :arrow_right: [green]{}[/green]".format(account_balance, new_balance))

    def unstake( self ):
        r""" Unstaked token of amount from uid.
        """
        console = Console()
        wallet = bittensor.wallet( config = self.config )
        subtensor = bittensor.subtensor( config = self.config )

        wallet.coldkey
        wallet.hotkey

        with console.status(":satellite: Syncing with chain: [white]{}[/white] ...".format(self.config.subtensor.network)):
            old_balance = subtensor.get_balance( wallet.coldkey.ss58_address )
            neuron = subtensor.neuron_for_uid( uid = self.config.uid, ss58_hotkey = wallet.hotkey.ss58_address)
        if neuron.is_null:
            console.print(":cross_mark:[red]Uid does not exist or is not associated with hotkey:{}[/red]".format(wallet.hotkey.ss58_address))
            sys.exit()

        if self.config.unstake_all:
            unstaking_balance = bittensor.Balance.from_rao( neuron.stake )
        else:
            unstaking_balance = bittensor.Balance.from_float( self.config.amount )
        stake_on_uid = bittensor.Balance.from_rao( neuron.stake )
        if unstaking_balance > stake_on_uid:
            console.print(":cross_mark:[red]Not enough stake[/red]:[green]{}[/green] to unstake:[blue]{}[/blue] from uid:[/white]{}[/white]".format(stake_on_uid, unstaking_balance, self.config.uid))
        
        # Ask before moving on.
        do_unstake = Confirm.ask("Do you want to unstake:[green ]{}[/green ] from uid:[blue ]{}[/blue ]?".format( unstaking_balance, self.config.uid) )
        if not do_unstake:
            sys.exit()

        with console.status(":satellite: Unstaking from chain: [white]{}[/white] ...".format(self.config.subtensor.network)):
            with subtensor.substrate as substrate:
                call = substrate.compose_call(
                    call_module='SubtensorModule', 
                    call_function='remove_stake',
                    call_params={
                        'hotkey': wallet.hotkey.ss58_address,
                        'ammount_unstaked': unstaking_balance.rao
                    }
                )
                extrinsic = substrate.create_signed_extrinsic( call = call, keypair = wallet.coldkey )
                response = substrate.submit_extrinsic( extrinsic, wait_for_inclusion = False, wait_for_finalization = True )
                if response.is_success:
                    console.print(":white_heavy_check_mark:[green]Finalized[/green]")
                else:
                    console.print(":cross_mark:[red]Failed[/red]: error:{}".format(response.error_message))

        if response.is_success:
            with console.status(":satellite: Checking Balance on: ([white]{}[/white] ...".format(self.config.subtensor.network)):
                new_balance = subtensor.get_balance( wallet.coldkey.ss58_address )
                new_stake = bittensor.Balance.from_rao( subtensor.neuron_for_uid( uid = self.config.uid, ss58_hotkey = wallet.hotkey.ss58_address).stake)
                console.print("Balance:[blue]{}[/blue] :arrow_right: [green]{}[/green]".format( old_balance, new_balance ))
                console.print("Stake:[blue]{}[/blue] :arrow_right: [green]{}[/green]".format( stake_on_uid, new_stake ))


    def stake( self ):
        r""" Staked token of amount to uid.
        """
        console = Console()
        wallet = bittensor.wallet( config = self.config )
        subtensor = bittensor.subtensor( config = self.config )

        wallet.coldkey
        wallet.hotkey

        with console.status(":satellite: Syncing with chain: [white]{}[/white] ...".format(self.config.subtensor.network)):
            old_balance = subtensor.get_balance( wallet.coldkey.ss58_address )
            old_neuron = subtensor.neuron_for_uid( uid = self.config.uid, ss58_hotkey = wallet.hotkey.ss58_address)
        if old_neuron.is_null:
            console.print(":cross_mark:[red]Uid does not exist or is not associated with hotkey:{}[/red]".format(wallet.hotkey.ss58_address))
            sys.exit()

        if self.config.stake_all:
            # TODO(const): once fixed for the staking mechanism.
            staking_balance = bittensor.Balance.from_float(old_balance.tao - 0.5) # must pay transfer fee too.
        else:
            staking_balance = bittensor.Balance.from_float( self.config.amount )
        if staking_balance > old_balance:
            console.print(":cross_mark:[red]Not enough stake[/red]:[green]{}[/green] to stake:[blue]{}[/blue] from account:[/white]{}[/white]".format(old_balance, staking_balance, wallet.coldkey.ss58_address))
        
        # Ask before moving on.
        do_stake = Confirm.ask("Do you want to stake:[green ]{}[/green ] to uid:[blue ]{}[/blue ]?".format( staking_balance, self.config.uid) )
        if not do_stake:
            sys.exit()

        with console.status(":satellite: Staking to: [white]{}[/white] ...".format(self.config.subtensor.network)):
            with subtensor.substrate as substrate:
                call = substrate.compose_call(
                    call_module='SubtensorModule', 
                    call_function='add_stake',
                    call_params={
                        'hotkey': wallet.hotkey.ss58_address,
                        'ammount_staked': staking_balance.rao
                    }
                )
                extrinsic = substrate.create_signed_extrinsic( call = call, keypair = wallet.coldkey )
                response = substrate.submit_extrinsic( extrinsic, wait_for_inclusion = False, wait_for_finalization = True )
                if response.is_success:
                    console.print(":white_heavy_check_mark:[green]Finalized[/green]")
                else:
                    console.print(":cross_mark:[red]Failed[/red]: error:{}".format(response.error_message))

        if response.is_success:
            with console.status(":satellite: Checking Balance on: [white]{}[/white] ...".format(self.config.subtensor.network)):
                new_balance = subtensor.get_balance( wallet.coldkey.ss58_address )
                old_stake = bittensor.Balance.from_rao( old_neuron.stake )
                new_stake = bittensor.Balance.from_rao( subtensor.neuron_for_uid( uid = self.config.uid, ss58_hotkey = wallet.hotkey.ss58_address).stake)
                console.print("Balance:[blue]{}[/blue] :arrow_right: [green]{}[/green]".format( old_balance, new_balance ))
                console.print("Stake:[blue]{}[/blue] :arrow_right: [green]{}[/green]".format( old_stake, new_stake ))


    def overview(self):
        r""" Prints an overview for the wallet's colkey.
        """
        console = Console()
        wallet = bittensor.wallet( config = self.config )
        subtensor = bittensor.subtensor( config = self.config )
        metagraph = bittensor.metagraph( subtensor = subtensor )
        with console.status(":satellite: Syncing with chain: [white]{}[/white] ...".format(self.config.subtensor.network)):
            metagraph.load()
            metagraph.sync()
            metagraph.save()
            balance = subtensor.get_balance( wallet.coldkeypub.ss58_address )

        owned_endpoints = [] 
        endpoints = metagraph.endpoint_objs
        for uid, cold in enumerate(metagraph.coldkeys):
            if cold == wallet.coldkeypub.ss58_address:
                owned_endpoints.append( endpoints[uid] )

        TABLE_DATA = []  
        total_stake = 0.0
        total_rank = 0.0
        total_trust = 0.0
        total_consensus = 0.0
        total_incentive = 0.0
        total_dividends = 0.0
        total_emission = 0.0      
        for ep in tqdm(owned_endpoints):
            uid = metagraph.coldkeys.index(wallet.coldkeypub.ss58_address)
            active = metagraph.active[uid ].item()
            stake = metagraph.S[uid ].item()
            rank = metagraph.R[uid ].item()
            trust = metagraph.T[uid ].item()
            consensus = metagraph.C[uid ].item()
            incentive = metagraph.I[uid ].item()
            dividends = metagraph.I[uid ].item()
            emission = metagraph.I[uid ].item()
            last_update = int(metagraph.block - metagraph.last_update[uid ])
            row = [
                str(ep.uid), 
                str(active), 
                '{:.5f}'.format(stake),
                '{:.5f}'.format(rank), 
                '{:.5f}'.format(trust), 
                '{:.5f}'.format(consensus), 
                '{:.5f}'.format(incentive),
                '{:.5f}'.format(dividends),
                '{:.5f}'.format(emission),
                str(last_update),
                ep.ip + ':' + str(ep.port) if ep.is_serving else '[yellow]none[/yellow]', 
                ep.hotkey
            ]
            total_stake += stake
            total_rank += rank
            total_trust += trust
            total_consensus += consensus
            total_incentive += incentive
            total_dividends += dividends
            total_emission += emission
            TABLE_DATA.append(row)
            
        total_neurons = len(owned_endpoints)                
        table = Table(show_footer=False)
        table.title = (
            "[white]Wallet - {}:{}".format(self.config.wallet.name, wallet.coldkeypub.ss58_address)
        )
        table.add_column("[overline white]UID",  str(total_neurons), footer_style = "overline white", style='yellow')
        table.add_column("[overline white]ACTIVE", justify='right', style='green', no_wrap=True)
        table.add_column("[overline white]STAKE", '{:.5f}'.format(total_stake), footer_style = "overline white", justify='right', style='green', no_wrap=True)
        table.add_column("[overline white]RANK", '{:.5f}'.format(total_rank), footer_style = "overline white", justify='right', style='green', no_wrap=True)
        table.add_column("[overline white]TRUST", '{:.5f}'.format(total_trust), footer_style = "overline white", justify='right', style='green', no_wrap=True)
        table.add_column("[overline white]CONSENSUS", '{:.5f}'.format(total_consensus), footer_style = "overline white", justify='right', style='green', no_wrap=True)
        table.add_column("[overline white]INCENTIVE", '{:.5f}'.format(total_incentive), footer_style = "overline white", justify='right', style='green', no_wrap=True)
        table.add_column("[overline white]DIVIDENDS", '{:.5f}'.format(total_dividends), footer_style = "overline white", justify='right', style='green', no_wrap=True)
        table.add_column("[overline white]EMISSION", '{:.5f}'.format(total_emission), footer_style = "overline white", justify='right', style='green', no_wrap=True)
        table.add_column("[overline white]LastUpdate (blocks)", justify='right', no_wrap=True)
        table.add_column("[overline white]AXON", justify='left', style='dim blue', no_wrap=True) 
        table.add_column("[overline white]HOTKEY", style='dim blue', no_wrap=False)
        table.show_footer = True
        table.caption = "[white]Wallet balance: [green]\u03C4" + str(balance.tao)

        console.clear()
        for row in TABLE_DATA:
            table.add_row(*row)
        table.box = None
        table.pad_edge = False
        table.width = None
        console.print(table)