# The MIT License (MIT)
# Copyright © 2021 Yuma Rao
# Copyright © 2022 Opentensor Foundation
import os

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

import numpy as np
import base64
import msgpack
import pydantic
import msgpack_numpy
from typing import Optional, Union, List
from bittensor.utils.registration import torch, use_torch

NUMPY_DTYPES = {
    "float16": np.float16,
    "float32": np.float32,
    "float64": np.float64,
    "uint8": np.uint8,
    "int16": np.int16,
    "int8": np.int8,
    "int32": np.int32,
    "int64": np.int64,
    "bool": bool,
}

if use_torch():
    TORCH_DTYPES = {
        "torch.float16": torch.float16,
        "torch.float32": torch.float32,
        "torch.float64": torch.float64,
        "torch.uint8": torch.uint8,
        "torch.int16": torch.int16,
        "torch.int8": torch.int8,
        "torch.int32": torch.int32,
        "torch.int64": torch.int64,
        "torch.bool": torch.bool,
    }


def cast_dtype(raw: Union[None, np.dtype, "torch.dtype", str]) -> str:
    """
    Casts the raw value to a string representing the
    `numpy data type <https://numpy.org/doc/stable/user/basics.types.html>`_, or the
    `torch data type <https://pytorch.org/docs/stable/tensor_attributes.html>`_ if using torch.

    Args:
        raw (Union[None, numpy.dtype, torch.dtype, str]): The raw value to cast.

    Returns:
        str: The string representing the numpy/torch data type.

    Raises:
        Exception: If the raw value is of an invalid type.
    """
    if not raw:
        return None
    if isinstance(raw, np.dtype):
        return NUMPY_DTYPES[raw]
    elif use_torch():
        if isinstance(raw, torch.dtype):
            return TORCH_DTYPES[raw]
    elif isinstance(raw, str):
        if use_torch():
            assert (
                raw in TORCH_DTYPES
            ), f"{raw} not a valid torch type in dict {TORCH_DTYPES}"
            return raw
        else:
            assert (
                raw in NUMPY_DTYPES
            ), f"{raw} not a valid numpy type in dict {NUMPY_DTYPES}"
            return raw
    else:
        raise Exception(
            f"{raw} of type {type(raw)} does not have a valid type in Union[None, numpy.dtype, torch.dtype, str]"
        )


def cast_shape(raw: Union[None, List[int], str]) -> str:
    """
    Casts the raw value to a string representing the tensor shape.

    Args:
        raw (Union[None, List[int], str]): The raw value to cast.

    Returns:
        str: The string representing the tensor shape.

    Raises:
        Exception: If the raw value is of an invalid type or if the list elements are not of type int.
    """
    if not raw:
        return None
    elif isinstance(raw, list):
        if len(raw) == 0:
            return raw
        elif isinstance(raw[0], int):
            return raw
        else:
            raise Exception(f"{raw} list elements are not of type int")
    elif isinstance(raw, str):
        shape = list(map(int, raw.split("[")[1].split("]")[0].split(",")))
        return shape
    else:
        raise Exception(
            f"{raw} of type {type(raw)} does not have a valid type in Union[None, List[int], str]"
        )


class tensor:
    def __new__(cls, tensor: Union[list, np.ndarray, "torch.Tensor"]):
        if isinstance(tensor, list) or isinstance(tensor, np.ndarray):
            tensor = (
                torch.tensor(tensor) if use_torch() else np.array(tensor)
            )
        return Tensor.serialize(tensor=tensor)


class Tensor(pydantic.BaseModel):
    """
    Represents a Tensor object.

    Args:
        buffer (Optional[str]): Tensor buffer data.
        dtype (str): Tensor data type.
        shape (List[int]): Tensor shape.
    """

    class Config:
        validate_assignment = True

    def tensor(self) -> Union[np.ndarray, "torch.Tensor"]:
        return self.deserialize()

    def tolist(self) -> List[object]:
        return self.deserialize().tolist()

    def numpy(self) -> "numpy.ndarray":
        return (
            self.deserialize().detach().numpy()
            if use_torch()
            else self.deserialize()
        )

    def deserialize(self) -> Union["np.ndarray", "torch.Tensor"]:
        """
        Deserializes the Tensor object.

        Returns:
            np.array or torch.Tensor: The deserialized tensor object.

        Raises:
            Exception: If the deserialization process encounters an error.
        """
        shape = tuple(self.shape)
        buffer_bytes = base64.b64decode(self.buffer.encode("utf-8"))
        numpy_object = msgpack.unpackb(
            buffer_bytes, object_hook=msgpack_numpy.decode
        ).copy()
        if use_torch():
            torch_object = torch.as_tensor(numpy_object)
            # Reshape does not work for (0) or [0]
            if not (len(shape) == 1 and shape[0] == 0):
                torch_object = torch_object.reshape(shape)
            return torch_object.type(TORCH_DTYPES[self.dtype])
        else:
            # Reshape does not work for (0) or [0]
            if not (len(shape) == 1 and shape[0] == 0):
                numpy_object = numpy_object.reshape(shape)
            return numpy_object.astype(NUMPY_DTYPES[self.dtype])

    @staticmethod
    def serialize(tensor: Union["np.ndarray", "torch.Tensor"]) -> "Tensor":
        """
        Serializes the given tensor.

        Args:
            tensor (np.array or torch.Tensor): The tensor to serialize.

        Returns:
            Tensor: The serialized tensor.

        Raises:
            Exception: If the serialization process encounters an error.
        """
        dtype = str(tensor.dtype)
        shape = list(tensor.shape)
        if len(shape) == 0:
            shape = [0]
        if use_torch():
            torch_numpy = tensor.cpu().detach().numpy().copy()
            data_buffer = base64.b64encode(
                msgpack.packb(torch_numpy, default=msgpack_numpy.encode)
            ).decode("utf-8")
        else:
            data_buffer = base64.b64encode(
                msgpack.packb(tensor, default=msgpack_numpy.encode)
            ).decode("utf-8")
        return Tensor(buffer=data_buffer, shape=shape, dtype=dtype)

    buffer: Optional[str] = pydantic.Field(
        title="buffer",
        description="Tensor buffer data. This field stores the serialized representation of the tensor data.",
        examples="0x321e13edqwds231231231232131",
        allow_mutation=False,
        repr=False,
    )  # Represents the tensor buffer data.

    dtype: str = pydantic.Field(
        title="dtype",
        description="Tensor data type. "
        "This field specifies the data type of the tensor, such as numpy.float32 or torch.int64.",
        examples="np.float32",
        allow_mutation=False,
        repr=True,
    )  # Represents the data type of the tensor.
    _extract_dtype = pydantic.validator("dtype", pre=True, allow_reuse=True)(cast_dtype)

    shape: List[int] = pydantic.Field(
        title="shape",
        description="Tensor shape. This field defines the dimensions of the tensor as a list of integers, such as [10, 10] for a 2D tensor with shape (10, 10).",
        examples="[10,10]",
        allow_mutation=False,
        repr=True,
    )  # Represents the shape of the tensor.
    _extract_shape = pydantic.validator("shape", pre=True, allow_reuse=True)(cast_shape)
