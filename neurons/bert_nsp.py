"""BERT Next Sentence Prediction Neuron.

This file demonstrates training the BERT neuron with next sentence prediction.

Example:
        $ python examples/bert_nsp.py

"""
import bittensor
import argparse
from bittensor.config import Config
from bittensor.utils.logging import log_outputs
from bittensor.subtensor import Keypair
from bittensor.synapses.bert import BertNSPSynapse


from loguru import logger
from datasets import load_dataset
from bittensor.utils.logging import log_batch_weights, log_chain_weights, log_request_sizes
import random
import time
import torch
import torch.nn.functional as F
from munch import Munch
import math
import os

def nsp_batch(data, batch_size, tokenizer):
    """ Returns a random batch from text dataset with 50 percent NSP.

        Args:
            data: (List[dict{'text': str}]): Dataset of text inputs.
            batch_size: size of batch to create.
        
        Returns:
            input_ids List[str]: List of sentences.
            batch_labels torch.Tensor(batch_size): 1 if random next sentence, otherwise 0.
    """

    batch_inputs = []
    batch_next = []
    batch_labels = []
    for _ in range(batch_size):
        if random.random() > 0.5:
            pos = random.randint(0, len(data))
            batch_inputs.append(data[pos]['text'])
            batch_next.append(data[pos + 1]['text'])
            batch_labels.append(0)
        else:
            while True:
                pos_1 = random.randint(0, len(data))
                pos_2 = random.randint(0, len(data))
                batch_inputs.append(data[pos_1]['text'])
                batch_next.append(data[pos_2]['text'])
                batch_labels.append(1)
                if (pos_1 != pos_2) and (pos_1 != pos_2 - 1):
                    break

    tokenized = tokenizer(batch_inputs, text_pair = batch_next, return_tensors='pt', padding=True)
    return tokenized, torch.tensor(batch_labels, dtype=torch.long)

def add_args(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:    
    parser.add_argument('--neuron.datapath', default='data/', type=str, 
                        help='Path to load and save data.')
    parser.add_argument('--neuron.learning_rate', default=0.01, type=float, 
                        help='Training initial learning rate.')
    parser.add_argument('--neuron.momentum', default=0.98, type=float, 
                        help='Training initial momentum for SGD.')
    parser.add_argument('--neuron.batch_size_train', default=20, type=int, 
                        help='Training batch size.')
    parser.add_argument('--neuron.batch_size_test', default=20, type=int, 
                        help='Testing batch size.')
    parser.add_argument('--neuron.sync_interval', default=100, type=int, 
                        help='Batches before we we sync with chain and emit new weights.')
    parser.add_argument('--neuron.name', default='bert_nsp', type=str, help='Trials for this neuron go in neuron.datapath / neuron.name')
    parser.add_argument('--neuron.trial_id', default=str(time.time()).split('.')[0], type=str, help='Saved models go in neuron.datapath / neuron.name / neuron.trial_id')
    parser = BertNSPSynapse.add_args(parser)
    return parser

def check_config(config: Munch) -> Munch:
    assert config.neuron.momentum > 0 and config.neuron.momentum < 1, "momentum must be a value between 0 and 1"
    assert config.neuron.batch_size_train > 0, "batch_size_train must a positive value"
    assert config.neuron.batch_size_test > 0, "batch_size_test must a positive value"
    assert config.neuron.learning_rate > 0, "learning_rate must be a positive value."
    Config.validate_path_create('neuron.datapath', config.neuron.datapath)
    config = BertNSPSynapse.check_config(config)
    return config

def train(model, config, session, optimizer, scheduler, dataset):
    step = 0
    best_loss = math.inf
    model.train()  # Turn on the train mode.
    weights = None
    history = []
    batch_idx = 0
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    while True:
        optimizer.zero_grad() # Clear gradients.

         # Sync with chain.
        if step % config.neuron.sync_interval == 0:
            weights = session.metagraph.sync(weights)
            weights = weights.to(device)


         # Next batch.
        inputs, targets = nsp_batch(dataset['train'], config.neuron.batch_size_train, bittensor.__tokenizer__)

        # Forward pass.
        output = model (inputs = inputs['input_ids'].to(model.device), 
                        targets = targets.to(model.device),
                        remote = True )
        history.append(output)

        # Backprop.
        output.loss.backward()
        optimizer.step()
        scheduler.step()

        # Update weights.
        batch_weights = F.softmax(torch.mean(output.weights, axis=0), dim=0) # Softmax weights.
        weights = (1 - 0.05) * weights + 0.05 * batch_weights # Moving Avg
        weights = weights / torch.sum(weights) # Normalize.
        
        # Log.
        step += 1
        logger.info('Step: {} \t Remote Loss: {:.6f}\t Local Loss: {:.6f}\t Distilation Loss: {:.6f}'.format(
            step, output.loss.item(), output.remote_target_loss.item(), output.distillation_loss.item()))
        log_outputs(history)
        log_batch_weights(session, history)
        log_chain_weights(session)
        log_request_sizes(session, history)
        history = []

        # After each epoch, checkpoint the losses and re-serve the network.
        if output.loss.item() < best_loss:
            best_loss = output.loss
            logger.info( 'Saving/Serving model: epoch: {}, loss: {}, path: {}/{}/{}/model.torch', step, output.loss, config.neuron.datapath, config.neuron.name, config.neuron.trial_id)
            torch.save( {'epoch': step, 'model': model.state_dict(), 'loss': output.loss},"{}/{}/{}/model.torch".format(config.neuron.datapath , config.neuron.name, config.neuron.trial_id))
            # Save experiment metrics
            session.serve( model.deepcopy() )


def main(config, session):
    # Build Synapse
    model = BertNSPSynapse(config, session)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model.to(device)
    session.serve( model )

    # Dataset: 74 million sentences pulled from books.
    dataset = load_dataset('bookcorpus')

    # Optimizer.
    optimizer = torch.optim.SGD(model.parameters(), lr = config.neuron.learning_rate)
    scheduler = torch.optim.lr_scheduler.StepLR(optimizer, step_size=5, gamma=0.1)

    # Create directory if it does not exist.
    data_directory = '{}/{}/{}'.format(config.neuron.datapath, config.neuron.name, config.neuron.trial_id)
    if not os.path.exists(data_directory):
        os.makedirs(data_directory)

    # train forever.
    train(model, config, session, optimizer, scheduler, dataset)
    

if __name__ == "__main__":
    # 1. Load bittensor config.
    parser = argparse.ArgumentParser()
    parser = add_args(parser)
    config = Config.load(parser)
    config = check_config(config)
    logger.info(Config.toString(config))

    # 2. Load Keypair.
    mnemonic = Keypair.generate_mnemonic()
    keypair = Keypair.create_from_mnemonic(mnemonic)
   
    # 3. Load Session.
    session = bittensor.init(config, keypair)

    # 4. Start Neuron.
    with session:
        main(config, session)
            
