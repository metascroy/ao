# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

import copy

import glob
import os

import sys
import unittest

import torch

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../../.."))
)
from quant_api import (
    _Int8DynActIntxWeightQuantizedLinearFallback,
    Int8DynActIntxWeightQuantizer,
)

libs = glob.glob("/tmp/cmake-out/torchao/liblowbit_op_aten.*")
libs = list(filter(lambda l: (l.endswith("so") or l.endswith("dylib")), libs))
if len(libs) == 0:
    print(
        "Could not find library lowbit_op_aten; please run `sh build_custom_op.sh` to build the library.  A slow fallback kernel will be used instaed."
    )
else:
    torch.ops.load_library(libs[0])


class TestInt8DynActIntxWeightQuantizer(unittest.TestCase):
    def test_accuracy(self):
        group_size = 128
        m = 1
        n = 1071
        k = 4096
        activations = torch.randn(m, k, dtype=torch.float32)
        model = torch.nn.Sequential(*[torch.nn.Linear(k, n, bias=False)])

        for nbit in [1, 2, 3, 4, 5, 6, 7]:
            for has_weight_zeros in [True, False]:
                print(f"Testing nbit={nbit}, has_weight_zeros={has_weight_zeros}")
                quantized_model = copy.deepcopy(model)
                quantizer = Int8DynActIntxWeightQuantizer(
                    device="cpu",
                    precision=torch.float32,
                    bitwidth=nbit,
                    groupsize=group_size,
                    has_weight_zeros=has_weight_zeros,
                )
                quantized_model = quantizer.quantize(quantized_model)

                with torch.no_grad():
                    result = quantized_model(activations)
                    reference_impl = _Int8DynActIntxWeightQuantizedLinearFallback()
                    reference_impl.quantize_and_pack_weights(
                        model[0].weight, nbit, group_size, has_weight_zeros
                    )
                    expected_result = reference_impl(activations)

                num_mismatch_at_low_tol = 0
                num_total = result.reshape(-1).shape[0]
                for i in range(num_total):
                    actual_val = result.reshape(-1)[i]
                    expected_val = expected_result.reshape(-1)[i]
                    self.assertTrue(torch.allclose(actual_val, expected_val, atol=1e-6))
                    if not torch.allclose(actual_val, expected_val):
                        num_mismatch_at_low_tol += 1

                # Assert at most 5% of entries are not close at a low tolerance
                self.assertTrue(num_mismatch_at_low_tol / num_total <= 0.05)


if __name__ == "__main__":
    unittest.main()
