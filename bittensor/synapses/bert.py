import bittensor

import torch
from torch import nn
import torch.nn.functional as F
import transformers
from transformers import BertModel, BertConfig

def mlm_batch(data, batch_size, tokenizer, collator):
    """ Returns a random batch from text dataset with 50 percent NSP.

        Args:
            data: (List[dict{'text': str}]): Dataset of text inputs.
            batch_size: size of batch to create.
        
        Returns:
            tensor_batch torch.Tensor (batch_size, sequence_length): List of tokenized sentences.
            labels torch.Tensor (batch_size, sequence_length)
    """
    batch_text = []
    for _ in range(batch_size):
        batch_text.append(data[random.randint(0, len(data))]['text'])

    # Tokenizer returns a dict { 'input_ids': list[], 'attention': list[] }
    # but we need to convert to List [ dict ['input_ids': ..., 'attention': ... ]]
    # annoying hack...
    tokenized = tokenizer(batch_text)
    tokenized = [dict(zip(tokenized,t)) for t in zip(*tokenized.values())]

    # Produces the masked language model inputs aw dictionary dict {'inputs': tensor_batch, 'labels': tensor_batch}
    # which can be used with the Bert Language model. 
    collated_batch =  collator(tokenized)
    return collated_batch['input_ids'], collated_batch['labels']

class BertSynapseConfig (bittensor.SynapseConfig):
    r"""
    This is the configuration class for a :class:`~BERTNSPSynapse`.
    

    Args:
        huggingface_config (:obj:`transformers.BertConfig`, `required`, defaults to BertSynapseConfig.__default_huggingface_config__):
            huggingface config for underlying transformer model.      

    examples:

        >>> from bittensor.synapses.bert import BertSynapseConfig, BertNSPSynapse

        >>> # Initializing a BertSynapseConfig configuration.
        >>> configuration = BertSynapseConfig()

        >>> # Initializing the synapse
        >>> configuration = BertNSPSynapse ( configuration )
    """

    __default_huggingface_config__ = BertConfig(vocab_size=bittensor.__vocab_size__, 
                                                hidden_size=bittensor.__network_dim__, 
                                                num_hidden_layers=2, 
                                                num_attention_heads=2, 
                                                intermediate_size=bittensor.__network_dim__, 
                                                is_decoder=False)

    
    def __init__(self, **kwargs):
        super(BertSynapseConfig, self).__init__(**kwargs)
        self.huggingface_config = kwargs.pop("huggingface_config", self.__default_huggingface_config__)
        self.run_checks()
    
    def run_checks(self):
        assert isinstance(self.huggingface_config, BertConfig)
        assert self.huggingface_config.hidden_size == bittensor.__network_dim__, "BERT hidden_size dim {} != {}".format(self.huggingface_config.hidden_size, bittensor.__network_dim__)
        assert self.huggingface_config.vocab_size == bittensor.__vocab_size__, "BERT vocab size must match bittensor.__vocab_size {} != {}".format(self.huggingface_config.vocab_size, bittensor.__vocab_size__)

class BertSynapseBase (bittensor.Synapse):
    def __init__(   self,
                config: BertSynapseConfig,
                session: bittensor.Session):
        r""" Init a new base-bert synapse.

            Args:
                config (:obj:`bittensor.bert.BertSynapseConfig`, `required`): 
                    BertNSP configuration class.

                btsession (:obj:`bittensor.Session`, `optional`): 
                    bittensor training session.

        """
        super(BertSynapseBase, self).__init__(
            config = config,
            session = session)
        
        self.router = bittensor.Router(x_dim=bittensor.__network_dim__,
                                       key_dim=100,
                                       topk=10)

        # encoder_layer: encodes tokenized sequences to network dim.
        # [batch_size, sequence_len] -> [batch_size, sequence_len, bittensor.__network_dim__]
        self.encoder_transformer = BertModel(self.config.huggingface_config, add_pooling_layer=True)

        # context_transformer: distills the remote_context from inputs
        # [batch_size, sequence_len] -> [batch_size, sequence_len, bittensor.__network_dim__]
        self.context_transformer = BertModel(self.config.huggingface_config, add_pooling_layer=False)

        # router: (PKM layer) queries network using pooled embeddings as context.
        # [batch_size, bittensor.__network_dim__] -> topk * [batch_size, bittensor.__network_dim__]
        self.router = bittensor.Router(x_dim=bittensor.__network_dim__, key_dim=100, topk=10)

        # hidden_layer: transforms context and encoding to network_dim hidden units.
        # [batch_size, sequence_dim, 2 * bittensor.__network_dim__] -> [batch_size, sequence_len, bittensor.__network_dim__]
        self.hidden_layer = torch.nn.Linear(2 * bittensor.__network_dim__, bittensor.__network_dim__)


    def forward_text(self, inputs: torch.LongTensor):
        """ Local forward inputs through the BERT NSP Synapse.

            Args:
                inputs (:obj:`torch.LongTensor` of shape :obj:`(batch_size, sequence_len)`, `required`): 
                    Batch_size length list of tokenized sentences.
            
            Returns:
                hidden (:obj:`torch.FloatTensor` of shape :obj:`(batch_size, sequence_len, bittensor.__network_dim__)`, `required`): 
                    Hidden layer representation produced using the local_context.
        """
        hidden = self.forward(inputs=inputs, remote = False).local_hidden
        return hidden

    def forward(self,
                inputs: torch.LongTensor,
                remote: bool = False):
        r""" Forward pass inputs and labels through the NSP BERT module.

            Args:
                inputs (:obj:`torch.LongTensor` of shape :obj:`(batch_size, sequence_len)`, `required`): 
                    Batch_size length list of text sentences.

                remote (:obj:`bool')`, `optional`):
                    Switch to True if this forward pass queries the network for the remote_context.

            bittensor.SynapseOutput ( 
                    loss  (:obj:`List[str]` of shape :obj:`(batch_size)`, `required`):
                        Total loss acumulation used by loss.backward()

                    local_hidden (:obj:`torch.FloatTensor` of shape :obj:`(batch_size, sequence_len, bittensor.__network_dim__)`, `required`):
                        Hidden layer encoding produced using local_context.

                    remote_hidden (:obj:`torch.FloatTensor` of shape :obj:`(batch_size, sequence_len, bittensor.__network_dim__)`, `optional`): 
                        Hidden layer encoding produced using the remote_context.

                    distillation_loss (:obj:`torch.FloatTensor` of shape :obj:`(1)`, `optional`): 
                        Distillation loss between local_context and remote_context.
                )
        """

        # Return vars to be filled.
        output = bittensor.SynapseOutput(loss = torch.tensor(0.0))
   
        # encoding: transformer encoded sentences.
        # encoding.shape = [batch_size, sequence_len, bittensor.__network_dim__]
        encoding = self.encoder_transformer(input_ids=inputs, return_dict=True)
        encoding_hidden = encoding.last_hidden_state
        encoding_pooled = encoding.pooler_output

        # remote_context: joined responses from a bittensor.forward_text call.
        # remote_context.shape = [batch_size, sequence_len, bittensor.__network_dim__]
        if remote:
            # network = torch.Tensor(batch_size, bittensor.__network_dim__)
            synapses = bittensor.metagraph.synapses()  # Returns a list of synapses on the network.
            requests, _ = self.router.route(synapses, encoding_pooled, inputs)  # routes inputs to network.
            responses = bittensor.dendrite.forward_text(synapses, requests)  # Makes network calls.
            remote_context = self.router.join(responses)  # Join responses with scores.

        # local_context: distilled version of remote_context.
        # local_context.shape = [batch_size, sequence_len, bittensor.__network_dim__]
        local_context = self.context_transformer(input_ids=inputs, return_dict=True).last_hidden_state
        if remote:
            # distillation_loss: distillation loss between local_context and remote_context
            # distillation_loss.shape = [1]
            distillation_loss = F.mse_loss(local_context, remote_context.detach())
            output.distillation_loss = distillation_loss
            output.loss = output.loss + distillation_loss

        # local_hidden: hidden layer encoding of sequence with local_context.
        # local_hidden.shape = [batch_size, sequence_len, bittensor.__network_dim__]
        local_hidden = torch.cat([encoding_hidden, local_context], dim=2)
        local_hidden = self.hidden_layer(local_hidden)
        output.local_hidden = local_hidden

        if remote:
            # remote_hidden: hidden layer encoding using remote_context.
            # remote_hidden.shape = [batch_size, sequence_len, bittensor.__network_dim__]
            remote_hidden = torch.cat([encoding_hidden, remote_context], dim=2)
            remote_hidden = self.hidden_layer(remote_hidden)
            output.remote_hidden = remote_hidden

        return output

class BertNSPSynapse (BertSynapseBase):
    def __init__(   self,
                    config: BertSynapseConfig,
                    dendrite: bittensor.Dendrite = None,
                    metagraph: bittensor.Metagraph = None):
        r""" Init a new bert nsp synapse module.

            Args:
                config (:obj:`bittensor.bert.BertSynapseConfig`, `required`): 
                    BertNSP configuration class.

                dendrite (:obj:`bittensor.Dendrite`, `optional`, bittensor.dendrite): 
                    bittensor dendrite object used for queries to remote synapses.
                    Defaults to bittensor.dendrite global.

                metagraph (:obj:`bittensor.Metagraph`, `optional`, bittensor.metagraph): 
                    bittensor metagraph containing network graph information. 
                    Defaults to bittensor.metagraph global.

        """
        super(BertNSPSynapse, self).__init__(
            config = config,
            dendrite = dendrite,
            metagraph = metagraph)
        
        # target_layer: maps from hidden layer to vocab dimension for each token. Used by MLM loss.
        # [batch_size, sequence_len, bittensor.__network_dim__] -> [batch_size, sequence_len, bittensor.__vocab_size__]
        self.target_layer = transformers.modeling_bert.BertOnlyNSPHead(self.config.huggingface_config)

        # Loss function: MLM cross-entropy loss.
        # predicted: [batch_size, sequence_len, 1], targets: [batch_size, sequence_len, 1] -> [1]
        self.loss_fct = torch.nn.CrossEntropyLoss()

    def forward_text(self, inputs: torch.LongTensor):
        """ Local forward inputs through the BERT NSP Synapse.

            Args:
                inputs (:obj:`torch.LongTensor` of shape :obj:`(batch_size, sequence_len)`, `required`): 
                    Batch_size length list of tokenized sentences.
            
            Returns:
                hidden (:obj:`torch.FloatTensor` of shape :obj:`(batch_size, sequence_len, bittensor.__network_dim__)`, `required`): 
                    Hidden layer representation produced using the local_context.
        """
        hidden = self.forward(inputs = inputs, remote = False).local_hidden
        return hidden


    def forward(self,
                inputs: torch.LongTensor,
                attention_mask: torch.LongTensor = None,
                targets: torch.Tensor = None,
                remote: bool = False):
        r""" Forward pass inputs and labels through the NSP BERT module.

            Args:
                inputs (:obj:`torch.LongTensor` of shape :obj:`(batch_size, sequence_len)`, `required`): 
                    Batch_size length list of text sentences.

                token_type_ids (:obj:`torch.LongTensor` of shape :obj:`(batch_size, sequence_len)`, `optional`): 
                    Token Type IDs for training to distinguish between the sentence context and the next sentence.

                attention_mask (:obj:`torch.LongTensor` of shape :obj:`(batch_size, sequence_len)`, `optional`): 
                    Mask to avoid performing attention on padding token indices.
                    Mask values selected in ``[0, 1]``:
                        - 1 for tokens that are **not masked**,
                        - 0 for tokens that are **maked**.        

                targets (``torch.LongTensor`` of shape ``(batch_size,)``, `optional`):
                    Targets for computing the next sequence prediction (classification) loss. 
                    Indices should be in ``[0, 1]``:
                        - 0 indicates sequence B is a continuation of sequence A,
                        - eqw1 indicates sequence B is a random sequence.

                remote (:obj:`bool')`, `optional`):
                    Switch to True if this forward pass queries the network for the remote_context.

            bittensor.SynapseOutput ( 
                    loss  (:obj:`List[str]` of shape :obj:`(batch_size)`, `required`):
                        Total loss acumulation used by loss.backward()

                    local_hidden (:obj:`torch.FloatTensor` of shape :obj:`(batch_size, sequence_len, bittensor.__network_dim__)`, `required`):
                        Hidden layer encoding produced using local_context.

                    local_target (:obj:`torch.FloatTensor` of shape :obj:`(batch_size, sequence_len, bittensor.__vocab_size__)`, `optional`):
                        BERT MLM Target predictions produced using local_context. 

                    local_target_loss (:obj:`torch.FloatTensor` of shape :obj:`(1)`, `optional`): 
                        BERT MLM loss using local_context.

                    remote_hidden (:obj:`torch.FloatTensor` of shape :obj:`(batch_size, sequence_len, bittensor.__network_dim__)`, `optional`): 
                        Hidden layer encoding produced using the remote_context.

                    remote_target (:obj:`torch.FloatTensor` of shape :obj:`(batch_size,  bittensor.__vocab_size__)`, `optional`):
                        BERT MLM Target predictions using the remote_context.

                    remote_target_loss (:obj:`torch.FloatTensor` of shape :obj:`(1)`, `optional`):
                        BERT MLM loss using the remote_context.

                    distillation_loss (:obj:`torch.FloatTensor` of shape :obj:`(1)`, `optional`): 
                        Distillation loss between local_context and remote_context.
                )
        """

        # Call forward method from bert base.
        output = BertSynapseBase.forward(self, inputs = inputs, remote = remote) 

        if targets is not None:
            # local_target: projection the local_hidden to target dimension.
            # local_target.shape = [batch_size, 2]
            local_target = self.target_layer(output.local_hidden)
            local_target = F.softmax(local_target, dim=1)
            output.local_target = local_target
            
            # local_target_loss: logit(1) > logit(0) if next_inputs are the real next sequences.
            # local_target_loss: [1]
            local_target_loss = self.loss_fct(local_target.view(-1, 2), targets)
            output.local_target_loss = local_target_loss
            output.loss = output.loss + local_target_loss


        if remote and targets is not None:
            # remote_target: projection the local_hidden to target dimension.
            # remote_target.shape = [batch_size, 2]
            remote_target = self.target_layer(output.remote_hidden)
            remote_target = F.softmax(remote_target, dim=1)
            output.remote_target = remote_target
            
            # remote_target_loss: logit(1) > logit(0) if next_inputs are the real next sequences.
            # remote_target_loss: [1]
            remote_target_loss = self.loss_fct(remote_target.view(-1, 2), targets)
            output.remote_target_loss = remote_target_loss
            output.loss = output.loss + remote_target_loss

        return output


class BertMLMSynapse (BertSynapseBase):
    def __init__(   self,
                    config: BertSynapseConfig,
                    dendrite: bittensor.Dendrite = None,
                    metagraph: bittensor.Metagraph = None):
        r""" Bert synapse for MLM training

            Args:
                config (:obj:`bittensor.bert.BertSynapseConfig`, `required`): 
                    BertNSP configuration class.

                dendrite (:obj:`bittensor.Dendrite`, `optional`, bittensor.dendrite): 
                    bittensor dendrite object used for queries to remote synapses.
                    Defaults to bittensor.dendrite global.

                metagraph (:obj:`bittensor.Metagraph`, `optional`, bittensor.metagraph): 
                    bittensor metagraph containing network graph information. 
                    Defaults to bittensor.metagraph global.

        """
        super(BertMLMSynapse, self).__init__(
            config = config,
            dendrite = dendrite,
            metagraph = metagraph)
      
        # target_layer: maps from hidden layer to vocab dimension for each token. Used by MLM loss.
        # [batch_size, sequence_len, bittensor.__network_dim__] -> [batch_size, sequence_len, bittensor.__vocab_size__]
        self.target_layer = transformers.modeling_bert.BertLMPredictionHead(self.config.huggingface_config)

        # Loss function: MLM cross-entropy loss.
        # predicted: [batch_size, sequence_len, 1], targets: [batch_size, sequence_len, 1] -> [1]
        self.loss_fct = torch.nn.CrossEntropyLoss()

    def forward_text(self, inputs: torch.LongTensor):
        """ Local forward inputs through the BERT NSP Synapse.

            Args:
                inputs (:obj:`torch.LongTensor` of shape :obj:`(batch_size, sequence_len)`, `required`): 
                    Batch_size length list of tokenized sentences.
            
            Returns:
                hidden (:obj:`torch.FloatTensor` of shape :obj:`(batch_size, sequence_len, bittensor.__network_dim__)`, `required`): 
                    Hidden layer representation produced using the local_context.
        """
        hidden = self.forward(inputs = inputs, remote = False).local_hidden
        return hidden

    def forward(self,
                inputs: torch.LongTensor,
                targets: torch.LongTensor = None,
                remote: bool = False):
        r""" Forward pass inputs and labels through the MLM BERT module.

            Args:
                inputs (:obj:`torch.LongTensor` of shape ``(batch_size, sequence_length)``, `required`):
                    Batch_size length list of tokenized sentences.
                
                targets (:obj:`torch.LongTensor` of shape ``(batch_size, sequence_length)``, `optional`):
                    Targets for computing the masked language modeling loss.
                    Indices should be in ``[-100, 0, ..., config.vocab_size]`` (see ``input_ids`` docstring)
                    Tokens with indices set to ``-100`` are ignored (masked), the loss is only computed for the tokens with targets
                    in ``[0, ..., config.vocab_size]``   

                remote (:obj:`bool')`, `optional`):
                    Switch to True if this forward pass queries the network for the remote_context.

            bittensor.SynapseOutput  ( 
                    loss  (:obj:`List[str]` of shape :obj:`(batch_size)`, `required`):
                        Total loss acumulation used by loss.backward()

                    local_hidden (:obj:`torch.FloatTensor` of shape :obj:`(batch_size, sequence_len, bittensor.__network_dim__)`, `required`):
                        Hidden layer encoding produced using local_context.

                    local_target (:obj:`torch.FloatTensor` of shape :obj:`(batch_size, sequence_len, bittensor.__vocab_size__)`, `optional`):
                        BERT MLM Target predictions produced using local_context. 

                    local_target_loss (:obj:`torch.FloatTensor` of shape :obj:`(1)`, `optional`): 
                        BERT MLM loss using local_context.

                    remote_hidden (:obj:`torch.FloatTensor` of shape :obj:`(batch_size, sequence_len, bittensor.__network_dim__)`, `optional`): 
                        Hidden layer encoding produced using the remote_context.

                    remote_target (:obj:`torch.FloatTensor` of shape :obj:`(batch_size,  bittensor.__vocab_size__)`, `optional`):
                        BERT MLM Target predictions using the remote_context.

                    remote_target_loss (:obj:`torch.FloatTensor` of shape :obj:`(1)`, `optional`):
                        BERT MLM loss using the remote_context.

                    distillation_loss (:obj:`torch.FloatTensor` of shape :obj:`(1)`, `optional`): 
                        Distillation loss between local_context and remote_context.
                )
        """
        # Call forward method from bert base.
        output = BertSynapseBase.forward(self, inputs = inputs, remote = remote) 

        if targets is not None:
            # local_target: projection the local_hidden to target dimension.
            # local_target.shape = [batch_size, bittensor.__vocab_size__]
            local_target = self.target_layer(output.local_hidden)
            local_target = F.softmax(local_target, dim=1)
            output.local_target = local_target
            
            # local_target_loss: logit(1) > logit(0) if next_inputs are the real next sequences.
            # local_target_loss: [1]
            local_target_loss = self.loss_fct(local_target.view(-1, bittensor.__vocab_size__), targets.view(-1))
            output.local_target_loss = local_target_loss
            output.loss = output.loss + local_target_loss

        if remote and targets is not None:
            # remote_target: projection the local_hidden to target dimension.
            # remote_target.shape = [batch_size, bittensor.__vocab_size__]
            remote_target = self.target_layer(output.remote_hidden)
            remote_target = F.softmax(remote_target, dim=1)
            output.remote_target = remote_target

            # remote_target_loss: cross entropy between predicted token and realized.
            # remote_target_loss: [1]
            remote_target_loss = self.loss_fct(remote_target.view(-1, bittensor.__vocab_size__), targets.view(-1))
            output.remote_target_loss = remote_target_loss
            output.loss = output.loss + remote_target_loss

        return output
