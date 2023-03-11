""" Create and init Axon, whcih services Forward and Backward requests from other neurons.
"""
# The MIT License (MIT)
# Copyright © 2021 Yuma Rao
# Copyright © 2022 Opentensor Foundation

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

import argparse
import os
import copy
import inspect
import time
from concurrent import futures
from typing import Dict, List, Callable, Optional, Tuple, Union
from bittensor._threadpool import prioritythreadpool

import torch
import grpc
from substrateinterface import Keypair

import bittensor
from . import axon_impl

class axon:
    """ The factory class for bittensor.Axon object
    The Axon is a grpc server for the bittensor network which opens up communication between it and other neurons.    
    Examples:: 
            >>> wallet = bittensor.wallet()
            >>> axon = bittensor.axon( config = bittensor.axon.config() )
            >>> class TextLastHiddenStateSynapse( bittensor.proto.TextLastHiddenStateSynapse ):
            >>>     def forward( self, text_inputs: torch.LongTensor ) -> torch.FloatTensor:
            >>>         return torch.zeros( ( text_inputs.shape[0], text_inputs.shape[1], bittensor.__network_dim__ ) )
            >>> axon.attach( TextLastHiddenStateSynapse() )
            >>> axon.start()
    """

    def __new__(
            cls,
            config: Optional['bittensor.config'] = None,
            wallet: Optional['bittensor.Wallet'] = None,
            thread_pool: Optional['futures.ThreadPoolExecutor'] = None,
            server: Optional['grpc._Server'] = None,
            port: Optional[int] = None,
            ip: Optional[str] = None,
            external_ip: Optional[str] = None,
            external_port: Optional[int] = None,
            max_workers: Optional[int] = None, 
            maximum_concurrent_rpcs: Optional[int] = None,
            blacklist: Optional[Callable] = None,
        ) -> 'bittensor.Axon':
        r""" Creates a new bittensor.Axon object from passed arguments.
            Args:
                config (:obj:`Optional[bittensor.Config]`, `optional`): 
                    bittensor.axon.config()
                wallet (:obj:`Optional[bittensor.Wallet]`, `optional`):
                    bittensor wallet with hotkey and coldkeypub.
                thread_pool (:obj:`Optional[ThreadPoolExecutor]`, `optional`):
                    Threadpool used for processing server queries.
                server (:obj:`Optional[grpc._Server]`, `required`):
                    Grpc server endpoint, overrides passed threadpool.
                port (:type:`Optional[int]`, `optional`):
                    Binding port.
                ip (:type:`Optional[str]`, `optional`):
                    Binding ip.
                external_ip (:type:`Optional[str]`, `optional`):
                    The external ip of the server to broadcast to the network.
                external_port (:type:`Optional[int]`, `optional`):
                    The external port of the server to broadcast to the network.
                max_workers (:type:`Optional[int]`, `optional`):
                    Used to create the threadpool if not passed, specifies the number of active threads servicing requests.
                maximum_concurrent_rpcs (:type:`Optional[int]`, `optional`):
                    Maximum allowed concurrently processed RPCs.
                blacklist (:obj:`Optional[callable]`, `optional`):
                    function to blacklist requests.
        """   
        if config == None: 
            config = axon.config()
        config = copy.deepcopy(config)
        config.axon.port = port if port != None else config.axon.port
        config.axon.ip = ip if ip != None else config.axon.ip
        config.axon.external_ip = external_ip if external_ip != None else config.axon.external_ip
        config.axon.external_port = external_port if external_port != None else config.axon.external_port
        config.axon.max_workers = max_workers if max_workers != None else config.axon.max_workers
        config.axon.maximum_concurrent_rpcs = maximum_concurrent_rpcs if maximum_concurrent_rpcs != None else config.axon.maximum_concurrent_rpcs
        axon.check_config( config )
        if wallet == None:
            wallet = bittensor.wallet( config = config )
        if thread_pool == None:
            thread_pool = futures.ThreadPoolExecutor( max_workers = config.axon.max_workers )
        if server == None:
            receiver_hotkey = wallet.hotkey.ss58_address
            server = grpc.server( 
                thread_pool,
                interceptors=(AuthInterceptor(receiver_hotkey=receiver_hotkey, blacklist=blacklist),),
                maximum_concurrent_rpcs = config.axon.maximum_concurrent_rpcs,
                options = [('grpc.keepalive_time_ms', 100000),
                            ('grpc.keepalive_timeout_ms', 500000)]
            )
            full_address = str( config.axon.ip ) + ":" + str( config.axon.port )
            server.add_insecure_port( full_address )

        return axon_impl.Axon(
            wallet = wallet, 
            server = server,
            ip = config.axon.ip,
            port = config.axon.port,
            external_ip = config.axon.external_ip, # don't use internal ip if it is None, we will try to find it later
            external_port = config.axon.external_port or config.axon.port, # default to internal port if external port is not set
        )

    @classmethod   
    def config(cls) -> 'bittensor.Config':
        """ Get config from the argument parser
        Return: bittensor.config object
        """
        parser = argparse.ArgumentParser()
        axon.add_args( parser )
        return bittensor.config( parser )

    @classmethod   
    def help(cls):
        """ Print help to stdout
        """
        parser = argparse.ArgumentParser()
        cls.add_args( parser )
        print (cls.__new__.__doc__)
        parser.print_help()

    @classmethod
    def add_args( cls, parser: argparse.ArgumentParser, prefix: str = None  ):
        """ Accept specific arguments from parser
        """
        prefix_str = '' if prefix == None else prefix + '.'
        try:
            parser.add_argument('--' + prefix_str + 'axon.port', type=int, 
                    help='''The local port this axon endpoint is bound to. i.e. 8091''', default = bittensor.defaults.axon.port)
            parser.add_argument('--' + prefix_str + 'axon.ip', type=str, 
                help='''The local ip this axon binds to. ie. [::]''', default = bittensor.defaults.axon.ip)
            parser.add_argument('--' + prefix_str + 'axon.external_port', type=int, required=False,
                    help='''The public port this axon broadcasts to the network. i.e. 8091''', default = bittensor.defaults.axon.external_port)
            parser.add_argument('--' + prefix_str + 'axon.external_ip', type=str, required=False,
                help='''The external ip this axon broadcasts to the network to. ie. [::]''', default = bittensor.defaults.axon.external_ip)
            parser.add_argument('--' + prefix_str + 'axon.max_workers', type=int, 
                help='''The maximum number connection handler threads working simultaneously on this endpoint. 
                        The grpc server distributes new worker threads to service requests up to this number.''', default = bittensor.defaults.axon.max_workers)
            parser.add_argument('--' + prefix_str + 'axon.maximum_concurrent_rpcs', type=int, 
                help='''Maximum number of allowed active connections''',  default = bittensor.defaults.axon.maximum_concurrent_rpcs)
        except argparse.ArgumentError:
            # re-parsing arguments.
            pass

        bittensor.wallet.add_args( parser, prefix = prefix )

    @classmethod   
    def add_defaults(cls, defaults):
        """ Adds parser defaults to object from enviroment variables.
        """
        defaults.axon = bittensor.Config()
        defaults.axon.port = os.getenv('BT_AXON_PORT') if os.getenv('BT_AXON_PORT') != None else 8091
        defaults.axon.ip = os.getenv('BT_AXON_IP') if os.getenv('BT_AXON_IP') != None else '[::]'
        defaults.axon.external_port = os.getenv('BT_AXON_EXTERNAL_PORT') if os.getenv('BT_AXON_EXTERNAL_PORT') != None else None
        defaults.axon.external_ip = os.getenv('BT_AXON_EXTERNAL_IP') if os.getenv('BT_AXON_EXTERNAL_IP') != None else None
        defaults.axon.max_workers = os.getenv('BT_AXON_MAX_WORERS') if os.getenv('BT_AXON_MAX_WORERS') != None else 10
        defaults.axon.maximum_concurrent_rpcs = os.getenv('BT_AXON_MAXIMUM_CONCURRENT_RPCS') if os.getenv('BT_AXON_MAXIMUM_CONCURRENT_RPCS') != None else 400

    @classmethod   
    def check_config(cls, config: 'bittensor.Config' ):
        """ Check config for axon port and wallet
        """
        assert config.axon.port > 1024 and config.axon.port < 65535, 'port must be in range [1024, 65535]'
        assert config.axon.external_port is None or (config.axon.external_port > 1024 and config.axon.external_port < 65535), 'external port must be in range [1024, 65535]'
        bittensor.wallet.check_config( config )

class AuthInterceptor(grpc.ServerInterceptor):
    """Creates a new server interceptor that authenticates incoming messages from passed arguments."""

    def __init__(
        self,
        receiver_hotkey: str,
        blacklist: Callable = None,
    ):
        r"""Creates a new server interceptor that authenticates incoming messages from passed arguments.
        Args:
            receiver_hotkey(str):
                the SS58 address of the hotkey which should be targeted by RPCs
            black_list (Function, `optional`):
                black list function that prevents certain pubkeys from sending messages
        """
        super().__init__()
        self.nonces = {}
        self.blacklist = blacklist
        self.receiver_hotkey = receiver_hotkey

    def parse_legacy_signature(
        self, signature: str
    ) -> Union[Tuple[int, str, str, str, int], None]:
        r"""Attempts to parse a signature using the legacy format, using `bitxx` as a separator"""
        parts = signature.split("bitxx")
        if len(parts) < 4:
            return None
        try:
            nonce = int(parts[0])
            parts = parts[1:]
        except ValueError:
            return None
        receptor_uuid, parts = parts[-1], parts[:-1]
        signature, parts = parts[-1], parts[:-1]
        sender_hotkey = "".join(parts)
        return (nonce, sender_hotkey, signature, receptor_uuid, 1)

    def parse_signature_v2(
        self, signature: str
    ) -> Union[Tuple[int, str, str, str, int], None]:
        r"""Attempts to parse a signature using the v2 format"""
        parts = signature.split(".")
        if len(parts) != 4:
            return None
        try:
            nonce = int(parts[0])
        except ValueError:
            return None
        sender_hotkey = parts[1]
        signature = parts[2]
        receptor_uuid = parts[3]
        return (nonce, sender_hotkey, signature, receptor_uuid, 2)

    def parse_signature(
        self, metadata: Dict[str, str]
    ) -> Tuple[int, str, str, str, int]:
        r"""Attempts to parse a signature from the metadata"""
        signature = metadata.get("bittensor-signature")
        if signature is None:
            raise Exception("Request signature missing")
        for parser in [self.parse_signature_v2, self.parse_legacy_signature]:
            parts = parser(signature)
            if parts is not None:
                return parts
        raise Exception("Unknown signature format")

    def check_signature(
        self,
        nonce: int,
        sender_hotkey: str,
        signature: str,
        receptor_uuid: str,
        format: int,
    ):
        r"""verification of signature in metadata. Uses the pubkey and nonce"""
        keypair = Keypair(ss58_address=sender_hotkey)
        # Build the expected message which was used to build the signature.
        if format == 2:
            message = f"{nonce}.{sender_hotkey}.{self.receiver_hotkey}.{receptor_uuid}"
        elif format == 1:
            message = f"{nonce}{sender_hotkey}{receptor_uuid}"
        else:
            raise Exception("Invalid signature version")
        # Build the key which uniquely identifies the endpoint that has signed
        # the message.
        endpoint_key = f"{sender_hotkey}:{receptor_uuid}"

        if endpoint_key in self.nonces.keys():
            previous_nonce = self.nonces[endpoint_key]
            # Nonces must be strictly monotonic over time.
            if nonce <= previous_nonce:
                raise Exception("Nonce is too small")

        if not keypair.verify(message, signature):
            raise Exception("Signature mismatch")
        self.nonces[endpoint_key] = nonce

    def black_list_checking( self, hotkey: str ):
        r"""Tries to call to blacklist function in the miner and checks if it should blacklist the pubkey"""
        if self.blacklist == None:
            return

        if self.blacklist(hotkey):
            raise Exception("Request type is blacklisted")

    def intercept_service(self, continuation, handler_call_details):
        r"""Authentication between bittensor nodes. Intercepts messages and checks them"""
        method = handler_call_details.method
        metadata = dict(handler_call_details.invocation_metadata)

        try:
            (
                nonce,
                sender_hotkey,
                signature,
                receptor_uuid,
                signature_format,
            ) = self.parse_signature(metadata)

            # signature checking
            self.check_signature(
                nonce, sender_hotkey, signature, receptor_uuid, signature_format
            )

            # blacklist checking
            self.black_list_checking( sender_hotkey )

            return continuation(handler_call_details)

        except Exception as e:
            message = str(e)
            abort = lambda _, ctx: ctx.abort(grpc.StatusCode.UNAUTHENTICATED, message)
            return grpc.unary_unary_rpc_method_handler(abort)
