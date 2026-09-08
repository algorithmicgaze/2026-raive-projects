# /// script
# requires-python = ">=3.10"
# dependencies = ["onnx", "onnxruntime", "onnxconverter-common", "numpy<2"]
# ///
"""Remove no-op Cast(to=float) nodes, constant-fold with onnxruntime (its CPU
provider cannot fold fp16 reductions, so fold while still fp32), then convert
to float16 with float32 I/O, letting Resize run in fp16 too.
onnxconverter-common retypes the tensors around an existing Cast but leaves
its `to` attribute, which makes ORT reject the model."""
import sys, warnings, collections
import numpy as np, onnx
from onnx import TensorProto
from onnxconverter_common import float16

src, dst = sys.argv[1], sys.argv[2]
m = onnx.load(src)
g = m.graph
rename = {}
kept = []
for n in g.node:
    if n.op_type == 'Cast' and n.attribute[0].i == TensorProto.FLOAT:
        rename[n.output[0]] = n.input[0]
    else:
        kept.append(n)
def resolve(name):
    while name in rename: name = rename[name]
    return name
for n in kept:
    for i, name in enumerate(n.input): n.input[i] = resolve(name)
for o in g.output: o.name = resolve(o.name)
del g.node[:]; g.node.extend(kept)
del g.value_info[:]
onnx.checker.check_model(m)
print('removed', len(rename), 'Cast nodes')
import onnxruntime as ort, tempfile, os
folded = os.path.join(tempfile.mkdtemp(), 'folded.onnx')
so = ort.SessionOptions(); so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_BASIC; so.optimized_model_filepath = folded
ort.InferenceSession(m.SerializeToString(), so, providers=['CPUExecutionProvider'])
m = onnx.load(folded)
print('after folding:', dict(sorted(collections.Counter(n.op_type for n in m.graph.node).items())))
block = [op for op in float16.DEFAULT_OP_BLOCK_LIST if op not in ('Resize', 'Upsample')]
with warnings.catch_warnings():
    warnings.simplefilter('ignore')
    m16 = float16.convert_float_to_float16(m, keep_io_types=True, op_block_list=block)
# Resize's roi and scales inputs must stay float32; the converter halves them too.
from onnx import numpy_helper
producers = {n.output[0]: n for n in m16.graph.node if n.op_type == 'Constant'}
inits16 = {i.name: i for i in m16.graph.initializer}
def to_f32(name):
    if name in producers:
        t = producers[name].attribute[0].t
        if t.data_type == TensorProto.FLOAT16:
            t.CopyFrom(numpy_helper.from_array(numpy_helper.to_array(t).astype(np.float32), name))
    elif name in inits16 and inits16[name].data_type == TensorProto.FLOAT16:
        inits16[name].CopyFrom(numpy_helper.from_array(numpy_helper.to_array(inits16[name]).astype(np.float32), name))
for n in m16.graph.node:
    if n.op_type == 'Resize':
        for name in n.input[1:3]:
            if name: to_f32(name)
onnx.checker.check_model(m16)
onnx.save(m16, dst)
print('ops', dict(sorted(collections.Counter(n.op_type for n in m16.graph.node).items())))
# validate on CPU: fp32 original vs fp16 (CPU EP runs fp16 via casts; slow but exact enough)
import onnxruntime as ort
x = np.random.RandomState(0).uniform(-1, 1, [1, 3, 512, 512]).astype(np.float32)
def run(path):
    s = ort.InferenceSession(path, providers=['CPUExecutionProvider']); return s.run(None, {'input': x})[0]
a, b = run(src), run(dst)
print(f'fp32 vs fp16 on CPU: max abs diff {np.abs(a-b).max():.4f}, mean {np.abs(a-b).mean():.5f}, range [{a.min():.2f},{a.max():.2f}]')
