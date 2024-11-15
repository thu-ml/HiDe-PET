import torch
import torch.nn as nn


class ContinualPrompt(nn.Module):
    def __init__(self, length=5, embed_dim=768, prompt_init='uniform',  
                 batchwise_prompt=False, num_layers=5, use_prefix_tune_for_e_prompt=False, num_heads=-1, same_key_value=False):
        super().__init__()
        self.length = length
        self.prompt_init = prompt_init
        self.batchwise_prompt = batchwise_prompt
        self.num_layers = num_layers
        self.use_prefix_tune_for_e_prompt = use_prefix_tune_for_e_prompt
        self.num_heads = num_heads

        # user prefix style
        if self.use_prefix_tune_for_e_prompt:
            assert embed_dim % self.num_heads == 0
            prompt_shape = (self.num_layers, 2, self.length, 
                            self.num_heads, embed_dim // self.num_heads)
            if prompt_init == 'zero':
                self.prompt = nn.Parameter(torch.zeros(prompt_shape))
            elif prompt_init == 'uniform':
                self.prompt = nn.Parameter(torch.randn(prompt_shape)) # num_layers, length, num_heads, embed_dim // num_heads
                nn.init.uniform_(self.prompt, -1, 1)
        else:
            prompt_shape = (self.num_layers, 2, self.length, embed_dim)  # TODO fix self.num_layers = 1
            if prompt_init == 'zero':
                self.prompt = nn.Parameter(torch.zeros(prompt_shape))
            elif prompt_init == 'uniform':
                self.prompt = nn.Parameter(torch.randn(prompt_shape))
                nn.init.uniform_(self.prompt, -1, 1)
    
    def forward(self, x_embed, **kwargs):
        out = dict()
        if self.use_prefix_tune_for_e_prompt:
            batched_prompt = self.prompt.unsqueeze(1).repeat(1, x_embed.shape[0], 1, 1, 1, 1)  # num_layers, B, length, num_heads, embed_dim // num_heads
        else:
            batched_prompt = self.prompt.unsqueeze(1).repeat(1, x_embed.shape[0], 1, 1, 1)  # num_layers, B, length, embed_dim
        
        out['batched_prompt'] = batched_prompt

        return out
    
    def after_taks(self, *args):
        pass

