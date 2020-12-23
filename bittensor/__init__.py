from loguru import logger
import os
import sys
from bittensor.subtensor.interface import Keypair
from transformers import GPT2Tokenizer

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bittensor.config import Config
from bittensor.session import Session

__version__ = 0
__compatability__ = [ 0 ] # Version compatability
__blocktime__ = 6 # seconds
__network_dim__ = 512 # Tensor.shape = [batch_size, sequence_lenght, 512]
__tokenizer__ = GPT2Tokenizer.from_pretrained("gpt2", local_files_only=False)
__tokenizer__.pad_token = '[PAD]'
__tokenizer__.mask_token = -100
__vocab_size__ = 204483


# Default logger
logger_config = {
    "handlers": [{
        "sink":
            sys.stdout,
        "format":
            "<level>{level: <8}</level>|<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    }]
}
logger.configure(**logger_config)

# Initialize the global bittensor session object.
session = None
def init(config: Config):
    global session

    session = Session(config)
    return session


