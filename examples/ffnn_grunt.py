"""FFNN Grunt node

This fil demonstrates how to train a FeedForward Neural network on the network
without a training ste.

Example:
        $ python examples/ffnn_grunt.py

"""
import argparse
import math
import os
import pathlib
import time
import torch
import torch.nn.functional as F

from munch import Munch
from loguru import logger
from termcolor import colored
from datasets import load_dataset
from torch.utils.tensorboard import SummaryWriter

import bittensor
from bittensor.neuron import Neuron
from bittensor.config import Config
from bittensor.synapses.ffnn import FFNNSynapse

class Session():

    def __init__(self, config: Munch):
        self.config = config

        # ---- Build Neuron ----
        self.neuron = Neuron(config)

        # ---- Build FFNN Model ----
        self.model = FFNNSynapse( self.config )
        self.model.to(torch.device("cuda" if torch.cuda.is_available() else "cpu"))
        self.neuron.axon.serve( self.model )

        # ---- Optimizer ----
        self.optimizer = torch.optim.SGD(self.model.parameters(), lr = self.config.session.learning_rate, momentum=self.config.session.momentum)

        # ---- Logging ----
        self.tensorboard = SummaryWriter(log_dir = self.config.session.full_path)
        if self.config.session.record_log:
            logger.add(self.config.session.full_path + "/{}_{}.log".format(self.config.session.name, self.config.session.trial_uid),format="{time:YYYY-MM-DD at HH:mm:ss} | {level} | {message}")

            
    @staticmethod
    def add_args(parser: argparse.ArgumentParser):    
        parser.add_argument('--session.learning_rate', default=0.01, type=float, help='Training initial learning rate.')
        parser.add_argument('--session.momentum', default=0.9, type=float, help='Training initial momentum for SGD.')
        parser.add_argument('--session.batch_size_train', default=64, type=int, help='Training batch size.')
        parser.add_argument('--session.batch_size_test', default=64, type=int, help='Testing batch size.')
        parser.add_argument('--session.log_interval', default=150, type=int, help='Batches until session prints log statements.')
        parser.add_argument('--session.sync_interval', default=150, type=int, help='Batches before we we sync with chain and emit new weights.')
        parser.add_argument('--neuron.apply_remote_gradients', default=False, type=bool, help='If true, neuron applies gradients which accumulate from remotes calls.')
        parser.add_argument('--session.root_dir', default='data/', type=str,  help='Root path to load and save data associated with each session')
        parser.add_argument('--session.name', default='ffnn-grunt', type=str, help='Trials for this session go in session.root / session.name')
        parser.add_argument('--session.trial_uid', default=str(time.time()).split('.')[0], type=str, help='Saved models go in session.root_dir / session.name / session.uid')
        parser.add_argument('--session.record_log', default=True, help='Record all logs when running this session')
        Neuron.add_args(parser)
        FFNNSynapse.add_args(parser)

    @staticmethod
    def check_config(config: Munch):
        assert config.session.log_interval > 0, "log_interval dimension must be positive"
        assert config.session.momentum > 0 and config.session.momentum < 1, "momentum must be a value between 0 and 1"
        assert config.session.batch_size_train > 0, "batch_size_train must be a positive value"
        assert config.session.batch_size_test > 0, "batch_size_test must be a positive value"
        assert config.session.learning_rate > 0, "learning rate must be be a positive value."
        full_path = '{}/{}/{}/'.format(config.session.root_dir, config.session.name, config.session.trial_uid)
        config.session.full_path = full_path
        if not os.path.exists(config.session.full_path):
            os.makedirs(config.session.full_path)
        FFNNSynapse.check_config(config)
        Neuron.check_config(config)

    # ---- Main loop ----
    def run(self):

        # --- Subscribe / Update neuron ---
        with self.neuron:

            # ---- Train forever ----
            self.model.train()
            step = -1; 
            while True:
                step += 1

                # ---- Poll until gradients ----
                public_key, inputs_x, grads_dy, modality_x = self.neuron.axon.gradients.get(block = True)

                # ---- Backward Gradients ----
                # TODO (const): batch normalization over the gradients for consistency.
                grads_dy = torch.where(torch.isnan(grads_dy), torch.zeros_like(grads_dy), grads_dy)
                self.model.backward(inputs_x, grads_dy, modality_x)

                # ---- Apply Gradients ----
                self.optimizer.step() # Apply accumulated gradients.
                self.optimizer.zero_grad() # Clear any lingering gradients

                # ---- Serve latest model ----
                self.neuron.axon.serve( self.model ) # Serve the newest model.
                logger.info('Step: {} \t Key: {} \t sum(W[:,0])', step, public_key, torch.sum(self.neuron.metagraph.col).item())
            
                # ---- Sync State ----
                if (step + 1) % self.config.session.sync_interval == 0:

                    # --- Display Epoch ----
                    print(self.neuron.axon.__full_str__())
                    print(self.neuron.dendrite.__full_str__())
                    print(self.neuron.metagraph)
                    
                    # ---- Sync metagrapn from chain ----
                    self.neuron.metagraph.sync() # Sync with the chain.
                    
                    # --- Save Model ----
                    logger.info( 'Saving model: epoch: {}, sum(W[:,0]): {}, path: {}/{}/{}/model.torch', step, torch.sum(self.neuron.metagraph.col).item(), self.config.session.full_path)
                    torch.save( {'epoch': step, 'model': self.model.state_dict(), 'loss': torch.sum(self.neuron.metagraph.col).item()},"{}//model.torch".format(self.config.session.full_path))                
                

   
if __name__ == "__main__":
    # ---- Load command line args ----
    parser = argparse.ArgumentParser(); Session.add_args(parser) 
    config = Config.to_config(parser); Session.check_config(config)
    logger.info(Config.toString(config))

    # ---- Build and Run ----
    session = Session(config)
    session.run()