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
import json
import torch
import asyncio
import bittensor
from typing import Callable, List, Dict

class TextPromptingDendritePool( torch.nn.Module ):

    def __init__(
            self, 
            metagraph: bittensor.metagraph.Metagraph, 
            wallet: bittensor.wallet.Wallet
        ):
        self.metagraph = metagraph
        self.wallet = wallet
        self.dendrites = []
        for uid, endpoint in enumerate( self.metagraph.endpoint_objs ):
            module = bittensor.text_prompting( endpoint = endpoint, wallet = self.wallet )
            self.dendrites.append( module )
            self.add_module( "dendrite-{}".format( uid ) , module )

    def forward( 
            self, 
            message: str, 
            prompt: str = None,
            uids: List[int] = None, 
            timeout: float = 12 
        ) -> List[str]:
        r""" Queries uids on the network for a response to the passed message.
        Args:
            message (str): The message to query the network with.
            uids (List[int]): The uids to query. If None, queries all uids.
            timeout (float): The timeout for the query.
        Returns:
            responses (List[str]): The responses from the network.
        """
        # We optionally set the uids to all if uids is None.
        if uids is None: uids = len( self.dendrites )

        # We optionally set the prompt to the message if prompt is None.
        if prompt is not None: 
            roles = ['system', 'user']
            messages = [ prompt, message ]
        else:
            roles = ['user']
            messages = [ message ]

        # The following asyncio defintion queries a single endpoint with the message
        # prompt and returns the response.
        async def call_single_uid( uid: int ) -> str:
            response = await self.dendrites[ uid ].async_forward( 
                roles = roles, 
                messages = messages, 
                timeout = timeout 
            )
            return response.response
        
        # The following asyncio definition gathers the responses
        # from multiple coroutines for each uid.
        async def query():
            coroutines = [ call_single_uid( uid ) for uid in uids ]                
            all_responses = await asyncio.gather(*coroutines)
            return all_responses
        
        # Return the message responses running the query in asyncio.
        return asyncio.run(query())

class TextPromptingDendrite(bittensor.Dendrite):
    """Dendrite for the text_prompting synapse."""

    # Dendrite name.
    name: str = "text_prompting"

    def __str__(self) -> str:
        return "TextPrompting"

    def get_stub(self, channel) -> Callable:
        return bittensor.grpc.TextPromptingStub(channel)

    def pre_process_forward_call_to_request_proto(
        self, forward_call: "bittensor.TextPromptingForwardCall"
    ) -> "bittensor.ForwardTextPromptingRequest":
        return bittensor.ForwardTextPromptingRequest( timeout = forward_call.timeout, messages = forward_call.messages )

    def post_process_response_proto_to_forward_call(
        self,
        forward_call: bittensor.TextPromptingForwardCall,
        response_proto: bittensor.ForwardTextPromptingResponse,
    ) -> bittensor.TextPromptingForwardCall:
        forward_call.response_code = response_proto.return_code
        forward_call.response_message = response_proto.message
        forward_call.response = response_proto.response
        return forward_call

    def forward(
        self,
        roles: str,
        messages: List[Dict[str, str]],
        timeout: float = bittensor.__blocktime__,
    ) -> "bittensor.TextPromptingForwardCall":
        loop = asyncio.get_event_loop()
        return loop.run_until_complete( 
            self._async_forward( 
                forward_call = bittensor.TextPromptingForwardCall(
                    messages = [json.dumps({"role": role, "content": message}) for role, message in zip(roles, messages)],
                    timeout = timeout,
                ) 
            ) 
        )
    
    def async_forward(
        self,
        roles: str,
        messages: List[Dict[str, str]],
        timeout: float = bittensor.__blocktime__,
    ) -> "bittensor.TextPromptingForwardCall":
        return self._async_forward(
            forward_call=bittensor.TextPromptingForwardCall(
                messages = [json.dumps({"role": role, "content": message}) for role, message in zip(roles, messages)],
                timeout = timeout,
            )
        )