#!/bin/python3
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
""" Advanced server neuron.

Example:
    $ python miners/text/multitron_server/main.py

"""
from re import I

import bittensor
import torch
import wandb
import pandas
import datetime
import traceback
import sys
import os
import wandb

from loguru import logger; logger = logger.opt(colors=True)
from torch.nn.utils import clip_grad_norm_
from datetime import datetime,timedelta
from threading import Lock
from torch.nn.parallel import DistributedDataParallel as DDP
import torch.distributed as dist
import torch.multiprocessing as mp
import time
from multiprocessing import Process, Manager, Event 
import threading 

os.environ['TOKENIZERS_PARALLELISM'] = 'false'

torch.autograd.set_detect_anomaly(True) 

class DDPPipe():
    def __init__( self, config: 'bittensor.config', gp_server, wallet: 'bittensor.wallet', forward_q, events, outputs):
        r""" Initializes the neuron with the passed config.
        """
        torch.autograd.set_detect_anomaly(True) 
        self.config = config
        self.config.to_defaults()
        self.gp_server = gp_server# .to(gp_server.device)
        self.wallet = wallet
        self.world_size = config.neuron.world_size
        self.forward_q = forward_q
        self.events = events
        self.outputs = outputs

        if self.config.wandb.api_key != 'default':
            bittensor.wandb(
                config = self.config,
                cold_pubkey = self.wallet.coldkeypub.ss58_address,
                hot_pubkey = self.wallet.hotkey.ss58_address,
                root_dir = self.config.neuron.full_path
            )

    
    def init_process(self, rank):
        r""" For each process, anchor them to the process group 
        so that they know how to communication with each other.

        Args:
            rank (int):
                rank (id) of the process.
        """
        os.environ['MASTER_ADDR'] = self.config.neuron.address
        os.environ['MASTER_PORT'] = self.config.neuron.port
        if 'cuda' in self.config.neuron.device:
            backend = 'nccl'
        else:
            backend = 'gloo'

        dist.init_process_group(
                backend, 
                rank=rank, 
                world_size=self.world_size, 
        )
    
    def init_bit(self, rank = 0):
        r""" Init bittensor modules .
        
        Args:
            rank (int):
                rank (id) of the process.
        """
        self.device = torch.device( device = f'cuda:{rank}' )        
        self.gp_server.device = self.device
        self.gp_server = self.gp_server.to(self.device)
        self.subtensor = bittensor.subtensor ( config = self.config )
        self.metagraph = bittensor.metagraph ( config = self.config, subtensor = self.subtensor )
        self.metagraph.sync()
        self.optimizer = torch.optim.SGD(
            [ {'params': self.gp_server.parameters() } ],
            lr = self.config.neuron.learning_rate,
            momentum = self.config.neuron.momentum,
        )
        
        if rank == 0 :
            logger.success( self.subtensor )
            self.subtensor.register( self.wallet )

        bittensor.tokenizer()

    def cleanup(self):
        r""" Kill the process.
        """
        dist.destroy_process_group()

    def run_parallel( self, ready = None):
        r""" Spawn multiple processes.
        """
        self.process_ctx = mp.spawn(self.run,
            args=(self.world_size, ready),
            nprocs=self.world_size,
            join = True
        )

    def run(self, rank = 0, world_size = 0, ready= None):
        self.init_bit(rank)
        if self.config.neuron.no_restart != True:
            self.gp_server.load(self.config.neuron.full_path)
        
        self.gp_server = self.gp_server.to(self.device) 

        # --- Init Wandb.

        nn = self.subtensor.neuron_for_pubkey(self.wallet.hotkey.ss58_address)
        uid = nn.uid

        # --- last sync block 
        last_sync_block = self.subtensor.get_current_block()
        last_set_block = last_sync_block
        last_log_block = last_sync_block
        last_log_time = time.time()
        # -- Main Training loop --
        if ready != None and rank == 0 :
            ready.set()

        if rank == 0:
            wandb.init()

        try:
            torch.cuda.empty_cache()
            while True: 
                try:
                    request_id, inputs_x = self.forward_q.get(timeput = self.config.neuron.console_log_time)
                    if inputs_x != None:
                        inputs_x = inputs_x.to(self.device)
                        output = self.gp_server.encode_forward(inputs_x)
                        output_clone = output.detach().clone().to(device = 'cpu')
                        self.outputs[request_id] = output_clone
                        self.events[request_id].set()
                        del output
                        del output_clone
                    del inputs_x
                    torch.cuda.empty_cache()
                except Exception as e:
                    logger.warning(e)
                    if 'out of memory' in str(e):                    
                        for p in self.gp_server.pre_model.parameters():
                            if p.grad is not None:
                                del p.grad                    
                        if inputs_x != None:
                            del inputs_x
                        torch.cuda.empty_cache()
                        bittensor.logging.success('cleaned memory', sufix = f'rank: {rank}, {e}')
                
                # log if a certain time period had passed
                # checking with time instead of block here to avoid frequent syncing from subtensor in a while loop
                if time.time() - last_log_time > self.config.neuron.console_log_time:
                    last_log_time = time.time()

                    # ---- syncing metagraph for all rank
                    current_block = self.subtensor.get_current_block()
                    if current_block - last_sync_block > self.config.neuron.metagraph_sync:
                        self.metagraph.sync()
                        last_sync_block = current_block

                    # ---- console logging and wandb logging for only rank 0                    
                    if rank == 0:
                        # ---- data
                        wandb_data = {
                            'block': current_block,
                            'stake': nn.stake,
                            'rank': nn.rank,
                            'incentive': nn.incentive,
                            'trust': nn.trust,
                            'consensus': nn.consensus,
                            'incentive': nn.incentive,
                            'dividends': nn.dividends,
                            'emission':  nn.emission,
                        } 
                        
                        # ---- console logging
                        bittensor.__console__.print('[green]Current Status:[/green]', wandb_data)

                        # ---- wandb logging
                        if current_block - last_log_block > self.config.neuron.wandb_log_block_time and self.config.wandb.api_key != 'default':
                            nn = self.subtensor.neuron_for_pubkey(self.wallet.hotkey.ss58_address)
                            last_log_block = current_block

                            # ---- Additional wandb data for metagraph
                            df = pandas.concat( [
                                bittensor.utils.indexed_values_to_dataframe( prefix = 'w_i_{}'.format(nn.uid), index = self.metagraph.uids, values = self.metagraph.W[:, uid] ),
                                bittensor.utils.indexed_values_to_dataframe( prefix = 's_i'.format(nn.uid), index = self.metagraph.uids, values = self.metagraph.S ),
                            ], axis = 1)
                            df['uid'] = df.index
                            stats_data_table = wandb.Table( dataframe = df ) 
                            wandb.log( { **wandb_data}, step = current_block )
                            wandb.log( { 'stats': stats_data_table }, step = current_block )
                            wandb.log( { 'axon_query_times': wandb.plot.scatter( stats_data_table, "uid", "axon_query_time", title="Axon Query time by UID") } )
                            wandb.log( { 'in_weights': wandb.plot.scatter( stats_data_table, "uid", 'w_i_{}'.format(nn.uid), title="Inward weights by UID") } )
                            wandb.log( { 'stake': wandb.plot.scatter( stats_data_table, "uid", 's_i', title="Stake by UID") } )
        
        except KeyboardInterrupt:
            if rank == 0:
                wandb.finish()

        except Exception as e:
            # --- Unknown error ----
            logger.exception('Unknown exception: {} with traceback {}', e, traceback.format_exc())

class Server:
    def __init__( self, config: 'bittensor.config', gp_server):
        r""" Initializes the neuron with the passed config.
        """
        self.config = config
        self.wallet = bittensor.wallet( config = config ).create().register()
        self.subtensor = bittensor.subtensor ( config = self.config )
        logger.success( self.subtensor )
        
        ctx = mp.get_context('spawn')
        self.forward_q = ctx.Queue()
        
        self.manager = Manager()
        self.events = self.manager.dict()
        self.outputs = self.manager.dict()
        
        self.axon = bittensor.axon (
            wallet = self.wallet,
            forward_text = self.forward_text,
            backward_text = lambda x : None,
            blacklist = self.blacklist,
            priority = self.priority
        ) 
    
        self.axon_pipe = DDPPipe(config, gp_server, self.wallet, self.forward_q, self.events, self.outputs )
        self.timecheck = {}
        self.subtensor = bittensor.subtensor ( config = self.config )
        self.metagraph = bittensor.metagraph ( config = self.config, subtensor = self.subtensor )
        self.futures = {}
        self.last_sync_block = None
        self.last_set_weight_block = None

    # Instantiate the model we are going to serve on the network.
    # Creating a threading lock for updates to the model
    # Define our forward function.
    def forward_text ( self, inputs_x):
        r""" Forward function that is called when the axon recieves a forward request from other peers
            Args:
                inputs_x ( :obj:`torch.Tensor`, `required`):
                    torch inputs to be forward processed.

            Returns:
                outputs (:obj:`torch.FloatTensor`):
                    The nucleus's outputs as a torch tensor of shape [batch_size, sequence_len, __network_dim__]
        """
        result = None
        request_id = id(inputs_x)
        self.forward_q.put( (request_id, inputs_x) )
        self.events[request_id] = self.manager.Event()
        
        if self.events[request_id].wait(12):
            result = self.outputs[request_id]

        del self.events[request_id]
        del self.outputs[request_id]

        return result

    def priority(self, pubkey:str, request_type:bittensor.proto.RequestType, inputs_x) -> float:
        r"""Calculates the priority on requests based on stake and size of input

            Args:
                pubkey ( str, `required`):
                    The public key of the caller.
                inputs_x ( :obj:`torch.Tensor`, `required`):
                    torch inputs to be forward processed.
                request_type ( bittensor.proto.RequestType, `required`):
                    the request type ('FORWARD' or 'BACKWARD').
        """        
        uid = self.metagraph.hotkeys.index(pubkey)
        priority = self.metagraph.S[uid].item()/ sys.getsizeof(inputs_x)

        return priority

    def blacklist(self, pubkey:str, request_type:bittensor.proto.RequestType) -> bool:
        r"""Axon security blacklisting, used to blacklist message from low stake members
            Args:
                pubkey ( str, `required`):
                    The public key of the caller.
                request_type ( bittensor.proto.RequestType, `required`):
                    the request type ('FORWARD' or 'BACKWARD').
        """

        # Check for stake
        def stake_check() -> bool:
            # If we allow non-registered requests return False = not blacklisted.
            is_registered = pubkey in self.metagraph.hotkeys
            if not is_registered:
                if self.config.neuron.blacklist_allow_non_registered:
                    return False
                else:
                    return True

            # Check stake.
            uid = self.metagraph.hotkeys.index(pubkey)
            if request_type == bittensor.proto.RequestType.FORWARD:
                if self.metagraph.S[uid].item() < self.config.neuron.blacklist.stake.forward:
                    return True
                else:
                    return False

            elif request_type == bittensor.proto.RequestType.BACKWARD:
                if self.metagraph.S[uid].item() < self.config.neuron.blacklist.stake.backward:
                    return True
                else:
                    return False

        # Check for time
        def time_check():
            current_time = datetime.now()
            if pubkey in self.timecheck.keys():
                prev_time = self.timecheck[pubkey]
                if current_time - prev_time >= timedelta(seconds=self.config.neuron.blacklist.time):
                    self.timecheck[pubkey] = current_time
                    return False
                else:
                    self.timecheck[pubkey] = current_time
                    return True
            else:
                self.timecheck[pubkey] = current_time
                return False

        # Black list or not
        if stake_check() or time_check():
            return True
        else: 
            return False

    def run(self):
        def serve_when_ready(serve_kwargs, pipe_ready):
            r""" Start to serve Axon when DDP have started
                Args:
                    serve_kwargs(map):
                        Arguments for serving axon.
                    pipe_ready(manager.Event):
                        The Event when the DDP is ready
            """
            if pipe_ready.wait():
                self.axon.start().serve(**serve_kwargs)
            
            return 
        
        def sync(keyboard_interupt):
            r""" Sync with metagraph and set weight to chain.
                Args:
                    keyboard_interupt(manager.Event):
                        Whether we have tried to stop the program with keyboard_interupt.
            """
            while not keyboard_interupt.is_set():
                current_block = self.subtensor.get_current_block()
                if (self.last_sync_block == None) or (current_block - self.last_sync_block > self.config.neuron.metagraph_sync):
                    self.last_sync_block = current_block
                    self.metagraph.sync()
                    bittensor.logging.success('Metagraph synced', sufix = f'{self.last_sync_block} --> {current_block}')
                    
                if (self.last_set_weight_block == None) or (current_block - self.last_set_weight_block > self.config.neuron.blocks_per_set_weights):
                    self.last_set_weight_block = current_block
                    chain_weights = torch.zeros(self.metagraph.n)
                    chain_weights [ self.uid ] = 1 
                    did_set = self.subtensor.set_weights(
                        uids=self.metagraph.uids,
                        weights = chain_weights,
                        wait_for_inclusion = False,
                        wallet = self.wallet,
                    )
                    
                    if did_set:
                        logger.success('Successfully set weights on the chain')
                    else:
                        logger.error('Failed to set weights on chain. (Timeout)')
                
                time.sleep(self.config.neuron.check_sync_time)
            
        try: 
            self.wallet.create()
            self.subtensor.register( self.wallet )
            self.metagraph.sync()
            neuron = self.subtensor.neuron_for_pubkey(self.wallet.hotkey.ss58_address)
            self.uid = neuron.uid

            pipe_ready = self.manager.Event()
            keyboard_interupt = self.manager.Event()
            axon_start_thread = threading.Thread( target = serve_when_ready, args = ({'subtensor': self.subtensor}, pipe_ready) )
            sync_thread = threading.Thread( target = sync, args = (keyboard_interupt, ))
            axon_start_thread.start()
            sync_thread.start()
            self.axon_pipe.run_parallel(ready = pipe_ready)
            
            # Just to keep this run function alive.
            while True:
                time.sleep(20)

        except KeyboardInterrupt:
            keyboard_interupt.set()
            logger.success('Keyboard Interuped')
            self.axon.stop()
            axon_start_thread.join()
            sync_thread.join()
        except Exception as e:
            # --- Unknown error ----
            logger.exception('Unknown exception: {} with traceback {}', e, traceback.format_exc())



