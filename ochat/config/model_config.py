from typing import Optional, Callable, Union
from dataclasses import dataclass
from functools import partial

import torch
import transformers
import ochat.models


@dataclass
class ModelConfig:
    name: str

    # Prompt
    system: Optional[str]

    role_prefix: Union[dict, Callable]
    ai_role: str
    eot_token: str
    bos_token: Optional[str] = None

    # Label
    group_fn: Optional[Callable] = None

    # Model
    model_max_context: Optional[int] = None
    model_create: Optional[Callable] = None
    model_tokenizer_create: Optional[Callable] = None

    # Get template
    def generate_conversation_template(self, tokenize_fn, tokenize_special_fn, message_list, message_props=None):
        tokens = []
        masks = []

        # begin of sentence (bos)
        if self.bos_token:
            t = tokenize_special_fn(self.bos_token)
            tokens.append(t)
            masks.append(False)

        # System
        if self.system:
            t = tokenize_fn(self.system) + [tokenize_special_fn(self.eot_token)]
            tokens.extend(t)
            masks.extend([False] * len(t))

        # Messages
        for idx, message in enumerate(message_list):
            # Prefix
            if callable(self.role_prefix):
                role_prefix = self.role_prefix(message["from"], message_props)
            else:
                role_prefix = self.role_prefix[message["from"]]

            t = tokenize_fn(role_prefix)
            tokens.extend(t)
            masks.extend([False] * len(t))

            # Message
            if "value" in message:
                t = tokenize_fn(message["value"]) + [tokenize_special_fn(self.eot_token)]
                tokens.extend(t)
                masks.extend([message["from"] == self.ai_role] * len(t))
            else:
                assert idx == len(message_list) - 1, "Empty message for completion must be on the last."

        group = 0
        if self.group_fn:
            group = self.group_fn(message_props)

        return tokens, masks, group


def _v2_conditional_prefix(from_role, props):
    human_prefix = "User:"
    gpt4_prefix  = "Assistant GPT4:"
    other_prefix = "Assistant GPT3:"

    if from_role == "human":
        return human_prefix
    
    if from_role == "gpt":
        if props is None:
            return gpt4_prefix  # inference using gpt-4 prefix
        
        return gpt4_prefix if props["is_gpt4"] else other_prefix
    
    raise NotImplementedError(f"Unknown role {from_role}")


def _v2_group(props):
    if props is None:
        return 1

    return 1 if props["is_gpt4"] else 0


MODEL_CONFIG_MAP = {
    # OpenChat 8192
    "openchat_8192": ModelConfig(
        name="OpenChat_8192",

        # Prompt
        system=None,

        role_prefix={
            "human": "Human: ",
            "gpt": "Assistant: "
        },
        ai_role="gpt",
        eot_token="<|end_of_turn|>",
        bos_token="<s>",

        # Model
        model_max_context=8192,
        model_create=partial(ochat.models.UnpaddedLlamaForCausalLM.from_pretrained,
                             extend_context_to=8192,
                             low_cpu_mem_usage=True,
                             torch_dtype=torch.bfloat16),
        model_tokenizer_create=partial(transformers.AutoTokenizer.from_pretrained,
                                       use_fast=False,
                                       use_auth_token=True),
    ),

    # OpenChat
    "openchat": ModelConfig(
        name="OpenChat",

        # Prompt
        system=None,

        role_prefix={
            "human": "Human: ",
            "gpt": "Assistant: "
        },
        ai_role="gpt",
        eot_token="<|end_of_turn|>",
        bos_token="<s>",

        # Tokenize
        model_max_context=2048,
        model_create=partial(ochat.models.UnpaddedLlamaForCausalLM.from_pretrained,
                             low_cpu_mem_usage=True,
                             torch_dtype=torch.bfloat16),
        model_tokenizer_create=partial(transformers.AutoTokenizer.from_pretrained,
                                       use_fast=False,
                                       use_auth_token=True),
    ),

    # OpenChat
    "openchat_v2": ModelConfig(
        name="OpenChat_v2",

        # Prompt
        system=None,

        role_prefix=_v2_conditional_prefix,
        ai_role="gpt",
        eot_token="<|end_of_turn|>",
        bos_token="<s>",

        # Label
        group_fn=_v2_group,

        # Tokenize
        model_max_context=2048,
        model_create=partial(ochat.models.UnpaddedLlamaForCausalLM.from_pretrained,
                             low_cpu_mem_usage=True,
                             torch_dtype=torch.bfloat16),
        model_tokenizer_create=partial(transformers.AutoTokenizer.from_pretrained,
                                       use_fast=False,
                                       use_auth_token=True),
    ),

    # OpenCoder / OpenCoderPlus
    "opencoder": ModelConfig(
        name="OpenCoder",

        # Prompt
        system=None,

        role_prefix={
            "human": "User:",
            "gpt": "Assistant:"
        },
        ai_role="gpt",
        eot_token="<|end_of_turn|>",
        bos_token=None,

        # Tokenize
        model_max_context=8192,
        model_create=partial(ochat.models.GPTBigCodeForCausalLM.from_pretrained,
                             low_cpu_mem_usage=True,
                             torch_dtype=torch.bfloat16),
        model_tokenizer_create=partial(transformers.AutoTokenizer.from_pretrained,
                                       use_fast=False,
                                       use_auth_token=True)
    )
}
