"""MNIST handwritten digits synapse

This file demonstrates a bittensor.Synapse trained on Mnist

Example:
        $ python examples/mnist/main.py

"""

import bittensor

import torch
import torch.nn as nn
import torch.nn.functional as F
import torchvision
import torchvision.transforms as transforms
from typing import List, Tuple, Dict, Optional

class MnistSynapse(bittensor.Synapse):
    """ Bittensor endpoint trained on PIL images to detect handwritten characters.
    """
    def __init__(self):
        super(MnistSynapse, self).__init__()

        # Set up device.
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

        # Image encoder: transforms variable shaped PIL tensors to a common shape.
        # Image.PIL.toTensor() -> [Image Encoder]
        self._transform = bittensor.utils.batch_transforms.Normalize((0.1307,), (0.3081,))
        self._adaptive_pool = nn.AdaptiveAvgPool2d((28, 28))

        # Router object for training network connectivity.
        # [Image Encoder] -> [ROUTER] -> [Synapses] -> [ROUTER]
        self.router = bittensor.Router(x_dim = 784, key_dim = 100, topk = 10)
        
        # Forward Network: Transforms inputs and (student or network) context into 
        # a (batch_size, bittensor.__network_dim__) output. 
        # [Image Encoder + (Student or Network)] -> [Forward Net] -> [Target Net]
        self.forward_layer1 = nn.Linear((784 + bittensor.__network_dim__), 512)
        self.forward_layer2 = nn.Linear(512, bittensor.__network_dim__)
        
        # Student Network: Learns a mapping from inputs to network context.
        # [Image Encoder] -> [Student Net] -> [Forward Network]
        self.student_layer1 = nn.Linear(784, 512)
        self.student_layer2 = nn.Linear(512, bittensor.__network_dim__)
        
        # Target Network: Transforms the model output to targets and loss.
        # [Image Encoder] -> [Student Net] -> [Forward Net] -> [Target Net]
        self.target_layer1 = nn.Linear(bittensor.__network_dim__, 256)
        self.target_layer2 = nn.Linear(256, 256)
        self.target_layer3 = nn.Linear(256, 10)

    def forward_image(self, images: torch.Tensor):
        r""" Forward pass inputs and labels through the NSP BERT module.

            Args:
                inputs (:obj:`torch.FloatTensor` of shape :obj:`(batch_size, -1, -1, -1)`, `required`): 
                    batch_size list of image tensors. (batch index, channel, row, col) produced for images
                    by calling PIL.toTensor()
            
            Returns:
                local_output (:obj:`torch.FloatTensor` of shape :obj:`(batch_size, bittensor.network_size)`, `required`): 
                    Output encoding of inputs produced using the student model as context.
        """
        return self.forward (images = images, query = False) ['local_output']

    def forward (   self, 
                    images: torch.Tensor,
                    labels: torch.Tensor = None,
                    query: bool = False):

        r""" Forward pass inputs and labels through the MNIST model.

            Args:
                images (:obj:`torch.FloatTensor` of shape :obj:`(batch_size, -1, -1, -1)`, `required`): 
                    PIL.toTensor() encoded images.

                labels (:obj:`torch.FloatTensor`  of shape :obj:`(batch_size, 10)`, `optional`): 
                    Mnist labels.

                query (:obj:`bool')`, `optional`):
                    Switch to True if this forward pass makes a remote call to the network. 

            Returns:
                dictionary with { 
                    loss  (:obj:`List[str]` of shape :obj:`(batch_size)`, `required`):
                        Total loss acumulation to be used by loss.backward()

                    local_output (:obj:`torch.FloatTensor` of shape :obj:`(batch_size, bittensor.__network_dim__)`, `required`):
                        Output encoding of image inputs produced by using the local student distillation model as 
                        context rather than the network. 

                    local_target (:obj:`torch.FloatTensor` of shape :obj:`(batch_size, 10)`, `optional`):
                        MNIST Target predictions using student model as context. 

                    local_target_loss (:obj:`torch.FloatTensor` of shape :obj:`(1)`, `optional`): 
                        MNIST Classification loss computed using the local_output, student model and passed labels.

                    network_target (:obj:`torch.FloatTensor` of shape :obj:`(batch_size, 10)`, `optional`):
                        MNIST Target predictions using the network as context. 

                    network_output (:obj:`torch.FloatTensor` of shape :obj:`(batch_size, bittensor.__network_dim__)`, `optional`): 
                        Output encoding of inputs produced by using the network inputs as context to the model rather than 
                        the student.

                    network_target_loss (:obj:`torch.FloatTensor` of shape :obj:`(1)`, `optional`):
                        MNIST Classification loss computed using the local_output and passed labels.

                    distillation_loss (:obj:`torch.FloatTensor` of shape :obj:`(1)`, `optional`): 
                        Distillation loss produced by the student with respect to the network context.
                }
        """
        # Return vars.
        loss = torch.tensor(0.0)
        local_output = None
        local_target = None
        network_output = None
        network_target = None
        network_target_loss = None
        local_target_loss = None
        distillation_loss = None

        # images: torch.Tensor(batch_size, -1, -1, -1)
        # transform: torch.Tensor(batch_size, 784)
        # The images are encoded to a standard shape 784 
        # using an adaptive pooling layer and our normalization
        # transform.
        transform = self._transform(images)
        transform = self._adaptive_pool(transform).to(self.device)
        transform = torch.flatten(transform, start_dim = 1)

        # If query == True make a remote network call.
        # network: torch.Tensor(batch_size, bittensor.__network_dim__)
        if query:
            synapses = bittensor.metagraph.synapses() # Returns a list of synapses on the network.
            requests, _ = self.router.route( synapses, transform, images ) # routes inputs to network.
            responses = bittensor.dendrite.forward_image( synapses, requests ) # Makes network calls.
            network = self.router.join( responses ) # Joins responses based on scores..

        # student: torch.Tensor(batch_size, bittensor.network_dim)
        # The student model distills from the network and is used
        # to compute the local_outputs when there is no network
        # context.
        student = F.relu(self.student_layer1 (transform))
        student = F.relu(self.student_layer2 (student))
        if query:
            # Use the network context to train the student network.
            distillation_loss = F.mse_loss(student, network.detach())
            loss += distillation_loss

        # local_output: torch.Tensor(batch_size, bittensor.network_dim)
        # The local_output is a non-target output of this synapse.
        # Outputs are used by other models as training signals.
        # This output is local because it uses the student inputs to 
        # condition the outputs rather than the network context.
        local_output = torch.cat((transform, student.detach()), dim=1)
        local_output = F.relu(self.forward_layer1 (local_output))
        local_output = F.relu(self.forward_layer2 (local_output))
        if labels is not None:
            # local_target = torch.Tensor(batch_size, 10)
            # Compute the target loss using the student and passed labels.
            labels.to(self.device)
            local_target = F.relu(self.target_layer1 (local_output))
            local_target = F.relu(self.target_layer2 (local_target))
            local_target = F.relu(self.target_layer3 (local_target))
            local_target = F.log_softmax(local_target, dim=1)
            local_target_loss = F.nll_loss(local_target, labels)
            loss += local_target_loss

        # network_output = torch.Tensor(batch_size, bittensor.network_dim)
        # The network_output is a non-target output of this synapse.
        # This output is remote because it requries inputs from the network.
        if query:
            network_output = torch.cat((transform, network), dim=1)
            network_output = F.relu(self.forward_layer1 (network_output))
            network_output = F.relu(self.forward_layer2 (network_output))

        # network_target = torch.Tensor(batch_size, 10)
        # Compute a target loss using the network_output and passed labels.
        if query and labels is not None:
            network_target = F.relu(self.target_layer1 (network_output))
            network_target = F.relu(self.target_layer2 (network_target))
            network_target = F.relu(self.target_layer3 (network_target))
            network_target = F.log_softmax(network_target, dim=1)
            network_target_loss = F.nll_loss(network_target, labels)
            loss += network_target_loss

        return {
            'loss': loss,
            'local_output': local_output,
            'network_output': network_output,
            'local_target': local_target,
            'network_target': network_target,
            'network_target_loss': network_target_loss,
            'local_target_loss': local_target_loss,
            'distillation_loss': distillation_loss
        }