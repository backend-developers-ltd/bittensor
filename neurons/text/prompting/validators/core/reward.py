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

import torch
from torch import nn
from typing import List,Dict
from transformers import AutoModel, AutoTokenizer, LlamaConfig
import math

import transformers


DEFAULT_PAD_TOKEN = "[PAD]"
DEFAULT_EOS_TOKEN = "</s>"
DEFAULT_BOS_TOKEN = "</s>"
DEFAULT_UNK_TOKEN = "</s>"


def prepare_llama_tokenizer_and_embedding(
        tokenizer: transformers.PreTrainedTokenizer,
        model: transformers.PreTrainedModel,
        special_tokens_dict: Dict = dict(pad_token=DEFAULT_PAD_TOKEN),
):
    """prepare llama tokenizer and embedding.

    """

    if tokenizer.pad_token is None:
        smart_tokenizer_and_embedding_resize(
            special_tokens_dict=dict(pad_token=DEFAULT_PAD_TOKEN),
            tokenizer=tokenizer,
            model=model,
        )

    tokenizer.add_special_tokens({
        "eos_token": DEFAULT_EOS_TOKEN,
        "bos_token": DEFAULT_BOS_TOKEN,
        "unk_token": DEFAULT_UNK_TOKEN,
    })

    return tokenizer


def smart_tokenizer_and_embedding_resize(
        tokenizer: transformers.PreTrainedTokenizer,
        model: transformers.PreTrainedModel,
        special_tokens_dict: Dict = dict(pad_token=DEFAULT_PAD_TOKEN),
):
    """Resize tokenizer and embedding.

    Note: This is the unoptimized version that may make your embedding size not be divisible by 64.
    """

    if tokenizer.pad_token is None:
        num_new_tokens = tokenizer.add_special_tokens(special_tokens_dict)

        if isinstance(model, RewardModel):
            model = model.get_base_model()

        model.resize_token_embeddings(len(tokenizer))

        if num_new_tokens > 0:
            input_embeddings = model.get_input_embeddings().weight.data
            # output_embeddings = model.model.get_output_embeddings().weight.data

            input_embeddings_avg = input_embeddings[:-num_new_tokens].mean(dim=0, keepdim=True)
            # output_embeddings_avg = output_embeddings[:-num_new_tokens].mean(dim=0, keepdim=True)

            input_embeddings[-num_new_tokens:] = input_embeddings_avg
            # output_embeddings[-num_new_tokens:] = output_embeddings_avg


class RewardModel(nn.Module):
    def __init__(self, model_path=None, config=None, lora_rank=0, lora_train_bias: str = 'none') -> None:
        super().__init__()
        if model_path is not None:
            self.model = AutoModel.from_pretrained(model_path)
        elif config is not None:
            self.model = AutoModel.from_config(config)
        else:
            self.model = AutoModel.from_config(LlamaConfig())

        self.value_head = nn.Linear(self.model.config.hidden_size, 1)
        self.value_head.weight.data.normal_(mean=0.0, std=1 / (self.model.config.hidden_size + 1))

        self.tokenizer = AutoTokenizer.from_pretrained('./llama_tokenizer')
        self.tokenizer = prepare_llama_tokenizer_and_embedding(self.tokenizer, self.model)
        self.PAD_ID = self.tokenizer(self.tokenizer.pad_token)["input_ids"][0]
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    def reward( self, completions: List[str] ) -> torch.FloatTensor:
        def reward_fn( samples ):
            if samples is None: return 0
            scores_list = []
            batch_size = 1
            for i in range(0, len(samples), batch_size):
                sub_samples = samples[i : i + batch_size]
                sub_samples = [
                    "<|startoftext|>" + chosen + "<|endoftext|>" for chosen in sub_samples
                ]
                encodings_dict = self.tokenizer(
                    sub_samples,
                    truncation=False,
                    max_length=550,
                    padding="max_length",
                    return_tensors="pt",
                )
                input_ids = encodings_dict["input_ids"].to( self.device )
                attn_masks = encodings_dict["attention_mask"].to( self.device )
                input_ids = input_ids.repeat(2, 1)
                attn_masks = attn_masks.repeat(2, 1)
                with torch.no_grad():
                    sub_scores = self.forward(input_ids=input_ids, attention_mask=attn_masks)
                scores_list.append(sub_scores["chosen_end_scores"])
            scores = torch.cat(scores_list, dim=0).mean().item()
            return scores
        
        with torch.no_grad():
            rewards = [reward_fn([completion]) for completion in completions]
            for completion, reward in zip(completions, rewards):
                print(completion)
                print(reward)
            return torch.tensor(rewards, dtype=torch.float32)
        
    def forward(
        self,
        input_ids=None,
        past_key_values=None,
        attention_mask=None,
        token_type_ids=None,
        position_ids=None,
        head_mask=None,
        inputs_embeds=None,
        mc_token_ids=None,
        labels=None,
        return_dict=False,
        output_attentions=False,
        output_hidden_states=False,
    ):
        loss = None
        transformer_outputs = self.model(
            input_ids,
            attention_mask=attention_mask
        )

        hidden_states = transformer_outputs['last_hidden_state']

        rewards = self.value_head(hidden_states)[:, :-1]
        chosen_end_scores = []
        rejected_end_scores = []

        # Split the inputs and rewards into two parts, chosen and rejected
        assert len(input_ids.shape) == 2
        bs = input_ids.shape[0] // 2
        chosen = input_ids[:bs]
        rejected = input_ids[bs:]
        chosen_rewards = rewards[:bs]
        rejected_rewards = rewards[bs:]

        loss = 0
        inference = False
        for i in range(bs):
            if torch.all(torch.eq(chosen[i], rejected[i])).item():
                c_inds = (chosen[i] == self.PAD_ID).nonzero()
                c_ind = c_inds[0].item() if len(c_inds) > 0 else chosen.shape[1]
                chosen_end_scores.append(chosen_rewards[i, c_ind - 1])
                inference = True
                continue

            # Check if there is any padding otherwise take length of sequence
            c_inds = (chosen[i] == self.PAD_ID).nonzero()
            c_ind = c_inds[0].item() if len(c_inds) > 0 else chosen.shape[1]
            r_inds = (rejected[i] == self.PAD_ID).nonzero()
            r_ind = r_inds[0].item() if len(r_inds) > 0 else rejected.shape[1]
            end_ind = max(c_ind, r_ind)

            # Retrieve first index where trajectories diverge
            divergence_ind = (chosen[i] != rejected[i]).nonzero()[0]
            assert divergence_ind > 0

            # Index into the correct rewards
            c_truncated_reward = chosen_rewards[i][divergence_ind:end_ind]
            r_truncated_reward = rejected_rewards[i][divergence_ind:end_ind]

            # Append the last rewards to the list of end scores
            chosen_end_scores.append(c_truncated_reward[-1])
            rejected_end_scores.append(r_truncated_reward[-1])

            # Compute loss based on truncated rewards (ignore padding)
            loss += -torch.log(torch.sigmoid(c_truncated_reward - r_truncated_reward)).mean()
        loss = loss / bs

        if not inference:
            chosen_end_scores = torch.stack(chosen_end_scores)
            rejected_end_scores = torch.stack(rejected_end_scores)

        if inference:
            chosen_end_scores = torch.stack(chosen_end_scores)
            return {"chosen_end_scores": chosen_end_scores}

        return {
            "loss": loss,
            "chosen_end_scores": chosen_end_scores,
            "rejected_end_scores": rejected_end_scores,
        }