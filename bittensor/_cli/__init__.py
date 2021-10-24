"""
Create and init the CLI class, which handles the coldkey, hotkey and money transfer 
"""
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

import os
import sys
import argparse

from termcolor import colored
import bittensor
from rich.prompt import Prompt
from rich.prompt import Confirm
from rich.console import Console
from substrateinterface.utils.ss58 import ss58_decode, ss58_encode
from . import cli_impl
console = bittensor.__console__

class cli:
    """
    Create and init the CLI class, which handles the coldkey, hotkey and tau transfer 
    """
    def __new__(
            cls, 
            config: 'bittensor.Config' = None,
        ) -> 'bittensor.CLI':
        r""" Creates a new bittensor.cli from passed arguments.
            Args:
                config (:obj:`bittensor.Config`, `optional`): 
                    bittensor.cli.config()
        """
        if config == None: 
            config = cli.config()
        cli.check_config( config )
        return cli_impl.CLI( config = config)

    @staticmethod   
    def config() -> 'bittensor.config':
        """ From the argument parser, add config to bittensor.executor and local config 
            Return: bittensor.config object
        """
        parser = argparse.ArgumentParser(description="Bittensor cli", usage="btcli <command> <command args>", add_help=True)

        cmd_parsers = parser.add_subparsers(dest='command')
        overview_parser = cmd_parsers.add_parser(
            'overview', 
            help='''Show account overview.'''
        )
        overview_parser.add_argument(
            '--no_prompt', 
            dest='no_prompt', 
            action='store_true', 
            help='''Set protect the generated bittensor key with a password.''',
            default=False,
        )
        bittensor.wallet.add_args( overview_parser )
        bittensor.subtensor.add_args( overview_parser )
        
        run_parser = cmd_parsers.add_parser(
            'run', 
            help='''Run the miner.'''
        )
        run_parser.add_argument(
            '--no_prompt', 
            dest='no_prompt', 
            action='store_true', 
            help='''Set protect the generated bittensor key with a password.''',
            default=False,
        )
        list_parser = cmd_parsers.add_parser(
            'list', 
            help='''List wallets'''
        )
        list_parser.add_argument(
            '--no_prompt', 
            dest='no_prompt', 
            action='store_true', 
            help='''Set protect the generated bittensor key with a password.''',
            default=False,
        )
        bittensor.wallet.add_args( list_parser )

        transfer_parser = cmd_parsers.add_parser(
            'transfer', 
            help='''Transfer Tao between accounts.'''
        )
        register_parser = cmd_parsers.add_parser(
            'register', 
            help='''Register a wallet to a network.'''
        )
        unstake_parser = cmd_parsers.add_parser(
            'unstake', 
            help='''Unstake from hotkey accounts.'''
        )
        stake_parser = cmd_parsers.add_parser(
            'stake', 
            help='''Stake to your hotkey accounts.'''
        )
        regen_coldkey_parser = cmd_parsers.add_parser(
            'regen_coldkey',
            help='''Regenerates a coldkey from a passed mnemonic'''
        )
        regen_hotkey_parser = cmd_parsers.add_parser(
            'regen_hotkey',
            help='''Regenerates a hotkey from a passed mnemonic'''
        )
        new_coldkey_parser = cmd_parsers.add_parser(
            'new_coldkey', 
            help='''Creates a new hotkey (for running a miner) under the specified path. '''
        )
        new_hotkey_parser = cmd_parsers.add_parser(
            'new_hotkey', 
            help='''Creates a new coldkey (for containing balance) under the specified path. '''
        )
         
        # Fill arguments for the regen coldkey command.
        regen_coldkey_parser.add_argument(
            "--mnemonic", 
            required=False, 
            nargs="+", 
            help='Mnemonic used to regen your key i.e. horse cart dog ...'
        )
        regen_coldkey_parser.add_argument(
            '--use_password', 
            dest='use_password', 
            action='store_true', 
            help='''Set protect the generated bittensor key with a password.''',
            default=True,
        )
        regen_coldkey_parser.add_argument(
            '--no_password', 
            dest='use_password', 
            action='store_false', 
            help='''Set off protects the generated bittensor key with a password.''',
        )
        regen_coldkey_parser.add_argument(
            '--no_prompt', 
            dest='no_prompt', 
            action='store_true', 
            help='''Set protect the generated bittensor key with a password.''',
            default=False,
        )
        bittensor.wallet.add_args( regen_coldkey_parser )


        # Fill arguments for the regen hotkey command.
        regen_hotkey_parser.add_argument(
            "--mnemonic", 
            required=False, 
            nargs="+", 
            help='Mnemonic used to regen your key i.e. horse cart dog ...'
        )
        regen_hotkey_parser.add_argument(
            '--use_password', 
            dest='use_password', 
            action='store_true', 
            help='''Set protect the generated bittensor key with a password.''',
            default=False
        )
        regen_hotkey_parser.add_argument(
            '--no_password', 
            dest='use_password', 
            action='store_false', 
            help='''Set off protects the generated bittensor key with a password.'''
        )
        regen_hotkey_parser.add_argument(
            '--no_prompt', 
            dest='no_prompt', 
            action='store_true', 
            help='''Set protect the generated bittensor key with a password.''',
            default=False,
        )
        bittensor.wallet.add_args( regen_hotkey_parser )


        # Fill arguments for the new coldkey command.
        new_coldkey_parser.add_argument(
            '--n_words', 
            type=int, 
            choices=[12,15,18,21,24], 
            default=12, 
            help='''The number of words representing the mnemonic. i.e. horse cart dog ... x 24'''
        )
        new_coldkey_parser.add_argument(
            '--use_password', 
            dest='use_password', 
            action='store_true', 
            help='''Set protect the generated bittensor key with a password.''',
            default=True,
        )
        new_coldkey_parser.add_argument(
            '--no_password', 
            dest='use_password', 
            action='store_false', 
            help='''Set off protects the generated bittensor key with a password.'''
        )
        new_coldkey_parser.add_argument(
            '--no_prompt', 
            dest='no_prompt', 
            action='store_true', 
            help='''Set protect the generated bittensor key with a password.''',
            default=False,
        )
        bittensor.wallet.add_args( new_coldkey_parser )


        # Fill arguments for the new hotkey command.
        new_hotkey_parser.add_argument(
            '--n_words', 
            type=int, 
            choices=[12,15,18,21,24], 
            default=12, 
            help='''The number of words representing the mnemonic. i.e. horse cart dog ... x 24'''
        )
        new_hotkey_parser.add_argument(
            '--use_password', 
            dest='use_password', 
            action='store_true', 
            help='''Set protect the generated bittensor key with a password.''',
            default=False
        )
        new_hotkey_parser.add_argument(
            '--no_password', 
            dest='use_password', 
            action='store_false', 
            help='''Set off protects the generated bittensor key with a password.'''
        )
        new_hotkey_parser.add_argument(
            '--no_prompt', 
            dest='no_prompt', 
            action='store_true', 
            help='''Set protect the generated bittensor key with a password.''',
            default=False,
        )
        bittensor.wallet.add_args( new_hotkey_parser )


        # Fill arguments for unstake command. 
        unstake_parser.add_argument(
            '--all', 
            dest="unstake_all", 
            action='store_true'
        )
        unstake_parser.add_argument(
            '--uid', 
            dest="uid", 
            type=int, 
            required=False
        )
        unstake_parser.add_argument(
            '--amount', 
            dest="amount", 
            type=float, 
            required=False
        )
        unstake_parser.add_argument(
            '--no_prompt', 
            dest='no_prompt', 
            action='store_true', 
            help='''Set protect the generated bittensor key with a password.''',
            default=False,
        )
        bittensor.wallet.add_args( unstake_parser )
        bittensor.subtensor.add_args( unstake_parser )


        # Fill arguments for stake command.
        stake_parser.add_argument(
            '--all', 
            dest="stake_all", 
            action='store_true'
        )
        stake_parser.add_argument(
            '--uid', 
            dest="uid", 
            type=int, 
            required=False
        )
        stake_parser.add_argument(
            '--amount', 
            dest="amount", 
            type=float, 
            required=False
        )
        stake_parser.add_argument(
            '--no_prompt', 
            dest='no_prompt', 
            action='store_true', 
            help='''Set protect the generated bittensor key with a password.''',
            default=False,
        )
        bittensor.wallet.add_args( stake_parser )
        bittensor.subtensor.add_args( stake_parser )


        # Fill arguments for transfer
        transfer_parser.add_argument(
            '--dest', 
            dest="dest", 
            type=str, 
            required=False
        )
        transfer_parser.add_argument(
            '--amount', 
            dest="amount", 
            type=float, 
            required=False
        )
        transfer_parser.add_argument(
            '--no_prompt', 
            dest='no_prompt', 
            action='store_true', 
            help='''Set protect the generated bittensor key with a password.''',
            default=False,
        )
        bittensor.wallet.add_args( transfer_parser )
        bittensor.subtensor.add_args( transfer_parser )


        # Fill arguments for transfer
        register_parser.add_argument(
            '--email', 
            dest="email", 
            type=str, 
            required=False
        )
        register_parser.add_argument(
            '--no_prompt', 
            dest='no_prompt', 
            action='store_true', 
            help='''Set protect the generated bittensor key with a password.''',
            default=False,
        )
        bittensor.wallet.add_args( register_parser )
        bittensor.subtensor.add_args( register_parser )

        # Fill run parser.
        run_parser.add_argument(
            '--path', 
            dest="path", 
            default=os.path.expanduser('~/Workspace/bittensor/miners/text/template_miner.py'),
            type=str, 
            required=False
        )
        

        # Hack to print formatted help
        if len(sys.argv) == 1:
            parser.print_help()
            sys.exit(0)

        return bittensor.config( parser )

    @staticmethod   
    def check_config (config: 'bittensor.Config'):
        """ Check if the essential condig exist under different command
        """
        if config.command == "run":
            cli.check_run_config( config )
        elif config.command == "transfer":
            cli.check_transfer_config( config )
        elif config.command == "register":
            cli.check_register_config( config )
        elif config.command == "unstake":
            cli.check_unstake_config( config )
        elif config.command == "stake":
            cli.check_stake_config( config )
        elif config.command == "overview":
            cli.check_overview_config( config )
        elif config.command == "new_coldkey":
            cli.check_new_coldkey_config( config )
        elif config.command == "new_hotkey":
            cli.check_new_hotkey_config( config )
        elif config.command == "regen_coldkey":
            cli.check_regen_coldkey_config( config )
        elif config.command == "regen_hotkey":
            cli.check_regen_hotkey_config( config )

    def check_transfer_config( config: 'bittensor.Config'):
        if config.subtensor.network == bittensor.defaults.subtensor.network and not config.no_prompt:
            if not Confirm.ask("Use network: [bold]'{}'[/bold]?".format(config.subtensor.network)):
                config.subtensor.network = Prompt.ask("Enter subtensor network", choices=bittensor.__networks__, default = bittensor.defaults.subtensor.network)

        if config.wallet.name == 'default' and not config.no_prompt:
            if not Confirm.ask("Use wallet: [bold]'default'[/bold]?"):
                wallet_name = Prompt.ask("Enter wallet name")
                config.wallet.name = str(wallet_name)

        # Get destination.
        if not config.dest:
            dest = Prompt.ask("Enter destination public key: (ss58 or ed2519)")
            if len(dest) == 48:
                try:
                    ss58_decode(dest)
                    config.dest = str(dest)
                except ValueError:
                    console.print(":cross_mark:[red] Invalid public key format[/red] [bold white]{}[/bold white]".format(dest))
                    sys.exit()
            elif len(dest) == 66 or len(dest) == 64:
                try:
                    ss58_encode(dest)
                    config.dest = str(dest)
                except ValueError:
                    console.print(":cross_mark:[red] Invalid ss58 address format[/red] [bold white]{}[/bold white]".format(dest))
                    sys.exit()
            else:
                console.print(":cross_mark:[red] Invalid address format[/red] [bold white]{}[/bold white]".format(dest))
                sys.exit()
                    
        # Get amount.
        if not config.amount:
            amount = Prompt.ask("Enter Tao amount to transfer")
            try:
                config.amount = float(amount)
            except ValueError:
                console.print(":cross_mark:[red] Invalid Tao amount[/red] [bold white]{}[/bold white]".format(amount))
                sys.exit()

    def check_unstake_config( config: 'bittensor.Config' ):
        if config.subtensor.network == bittensor.defaults.subtensor.network and not config.no_prompt:
            if not Confirm.ask("Use network: [bold]'{}'[/bold]?".format(config.subtensor.network)):
                config.subtensor.network = Prompt.ask("Enter subtensor network", choices=bittensor.__networks__, default = bittensor.defaults.subtensor.network)

        if config.wallet.name == 'default' and not config.no_prompt:
            if not Confirm.ask("Use wallet: [bold]'default'[/bold]?"):
                wallet_name = Prompt.ask("Enter wallet name")
                config.wallet.name = str(wallet_name)

        # Get destination.
        if config.uid == None:
            uid = Prompt.ask("Enter uid to unstake from")
            try:
                config.uid = int(uid)     
            except ValueError:
                console.print(":cross_mark:[red] Invalid uid[/red] [bold white]{}[/bold white]".format(uid))
                sys.exit()
                    
        # Get amount.
        if not config.amount and not config.unstake_all:
            if not Confirm.ask("Unstake all Tao from uid: [bold]'{}'[/bold]?".format(config.uid)):
                amount = Prompt.ask("Enter Tao amount to unstake")
                try:
                    config.amount = float(amount)
                except ValueError:
                    console.print(":cross_mark:[red] Invalid Tao amount[/red] [bold white]{}[/bold white]".format(amount))
                    sys.exit()
            else:
                config.unstake_all = True


    def check_stake_config( config: 'bittensor.Config' ):
        if config.subtensor.network == bittensor.defaults.subtensor.network and not config.no_prompt:
            if not Confirm.ask("Use network: [bold]'{}'[/bold]?".format(config.subtensor.network)):
                config.subtensor.network = Prompt.ask("Enter subtensor network", choices=bittensor.__networks__, default = bittensor.defaults.subtensor.network)

        if config.wallet.name == bittensor.defaults.wallet.name and not config.no_prompt:
            if not Confirm.ask("Use wallet: [bold]'default'[/bold]?"):
                wallet_name = Prompt.ask("Enter wallet name")
                config.wallet.name = str(wallet_name)

        # Get destination.
        if config.uid == None:
            uid = Prompt.ask("Enter uid to stake to")
            try:
                config.uid = int(uid)     
            except ValueError:
                console.print(":cross_mark:[red] Invalid uid[/red] [bold white]{}[/bold white]".format(uid))
                sys.exit()
                    
        # Get amount.
        if not config.amount and not config.stake_all:
            if not Confirm.ask("Stake all Tao from account: [bold]'{}'[/bold]?".format(config.wallet.name)):
                amount = Prompt.ask("Enter Tao amount to stake")
                try:
                    config.amount = float(amount)
                except ValueError:
                    console.print(":cross_mark:[red]Invalid Tao amount[/red] [bold white]{}[/bold white]".format(amount))
                    sys.exit()
            else:
                config.stake_all = True

    def check_overview_config( config: 'bittensor.Config' ):
        if config.subtensor.network == bittensor.defaults.subtensor.network and not config.no_prompt:
            if not Confirm.ask("Use network: [bold]'{}'[/bold]?".format(config.subtensor.network)):
                config.subtensor.network = Prompt.ask("Enter subtensor network", choices=bittensor.__networks__, default = bittensor.defaults.subtensor.network)

        if config.wallet.name == 'default' and not config.no_prompt:
            if not Confirm.ask("Use wallet: [bold]'default'[/bold]?"):
                wallet_name = Prompt.ask("Enter wallet name")
                config.wallet.name = str(wallet_name)

    def check_register_config( config: 'bittensor.Config' ):
        if config.subtensor.network == bittensor.defaults.subtensor.network and not config.no_prompt:
            if not Confirm.ask("Use network: [bold]'{}'[/bold]?".format(config.subtensor.network)):
                config.subtensor.network = Prompt.ask("Enter subtensor network", choices=bittensor.__networks__, default = bittensor.defaults.subtensor.network)

        if config.wallet.name == 'default' and not config.no_prompt:
            if not Confirm.ask("Use wallet: [bold]'default'[/bold]?"):
                wallet_name = Prompt.ask("Enter wallet name")
                config.wallet.name = str(wallet_name)

        if config.wallet.hotkey == 'default' and not config.no_prompt:
            if not Confirm.ask("Use wallet hotkey: [bold]'default'[/bold]?"):
                hotkey = Prompt.ask("Enter hotkey name")
                config.wallet.hotkey = str(hotkey)

        if config.wallet.email == None:
            if config.email == None:
                email_name = Prompt.ask("Enter registration email")
                config.email = str(email_name)

    def check_new_coldkey_config( config: 'bittensor.Config' ):
        if config.wallet.name == 'default' and not config.no_prompt:
            if not Confirm.ask("Use wallet name: [bold]'default'[/bold]?"):
                wallet_name = Prompt.ask("Enter wallet name")
                config.wallet.name = str(wallet_name)

    def check_new_hotkey_config( config: 'bittensor.Config' ):
        if config.wallet.name == 'default' and not config.no_prompt:
            if not Confirm.ask("Use wallet name: [bold]'default'[/bold]?"):
                wallet_name = Prompt.ask("Enter wallet name")
                config.wallet.name = str(wallet_name)
        if config.wallet.hotkey == 'default' and not config.no_prompt:
            if not Confirm.ask("Use wallet hotkey: [bold]'default'[/bold]?"):
                hotkey = Prompt.ask("Enter hotkey name")
                config.wallet.hotkey = str(hotkey)

    def check_regen_hotkey_config( config: 'bittensor.Config' ):
        if config.wallet.name == 'default' and not config.no_prompt:
            if not Confirm.ask("Use wallet name: [bold]'default'[/bold]?"):
                wallet_name = Prompt.ask("Enter wallet name")
                config.wallet.name = str(wallet_name)
        if config.wallet.hotkey == 'default' and not config.no_prompt:
            if not Confirm.ask("Use wallet hotkey: [bold]'default'[/bold]?"):
                hotkey = Prompt.ask("Enter hotkey name")
                config.wallet.hotkey = str(hotkey)
        if config.mnemonic == None:
            config.mnemonic = Prompt.ask("Enter mnemonic")

    def check_regen_coldkey_config( config: 'bittensor.Config' ):
        if config.wallet.name == 'default' and not config.no_prompt:
            if not Confirm.ask("Use wallet name: [bold]'default'[/bold]?"):
                wallet_name = Prompt.ask("Enter wallet name")
                config.wallet.name = str(wallet_name)
        if config.mnemonic == None:
            config.mnemonic = Prompt.ask("Enter mnemonic")

    def check_run_config( config: 'bittensor.Config' ):

        # Copy accross keys.
        import importlib
        from pathlib import Path

        file_path = Path(str(Path(__file__).resolve()) + "/../../../miners/text/template_miner.py").resolve()
        miner = importlib.machinery.SourceFileLoader('Miner',os.path.expanduser(file_path)).load_module()
        miner_config = miner.Miner.config()
        for k in miner_config.keys():
            config[k] = miner_config[k]

        # Check network.
        if config.subtensor.network == bittensor.defaults.subtensor.network and not config.no_prompt:
            if not Confirm.ask("Run miner on network: [bold]'{}'[/bold]?".format(config.subtensor.network)):
                config.subtensor.network = Prompt.ask("Enter subtensor network", choices=bittensor.__networks__, default = bittensor.defaults.subtensor.network)

        # Check wallet.
        if config.wallet.name == 'default' and not config.no_prompt:
            if not Confirm.ask("Use wallet name: [bold]'default'[/bold]?"):
                wallet_name = Prompt.ask("Enter wallet name")
                config.wallet.name = str(wallet_name)

        # Check hotkey.
        if config.wallet.hotkey == 'default' and not config.no_prompt:
            if not Confirm.ask("Use wallet hotkey: [bold]'default'[/bold]?"):
                hotkey = Prompt.ask("Enter hotkey name")
                config.hotkey = str(hotkey)



                
                