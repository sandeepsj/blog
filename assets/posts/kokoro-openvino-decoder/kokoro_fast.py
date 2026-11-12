"""Make Kokoro-82M ~40% faster on a CPU without changing its sound.

Kokoro's decoder (the vocoder) is ~93% of the time. This runs only its convolution stack on OpenVINO and keeps
the two small ends in PyTorch, exactly as Kokoro wrote them:

    F0 curve -> sine/noise source + STFT        (PyTorch, Kokoro's code, torch's random noise)
    asr, F0, N, style -> convolutions           (OpenVINO)
    -> exp/sin + inverse STFT                   (PyTorch)

Kokoro's own ONNX export mode (disable_complex=True) is not used: it replaces the STFT with an approximation
and the audio comes out about 15% louder with a different spectrum.

    pip install kokoro openvino onnx soundfile   # plus CPU PyTorch
    python kokoro_fast.py                        # writes plain.wav and fast.wav and compares them

Tested with kokoro 0.9.4, torch 2.15 (CPU), openvino 2026.4.1, Python 3.12, on a Ryzen 7 5700U.
"""

from __future__ import annotations

import copy
import os
import time
import warnings
from pathlib import Path

import torch
import torch.nn.functional as F

CACHE = Path(os.environ.get("KOKORO_FAST_CACHE", Path.home() / ".cache/kokoro-fast"))


def _fold_weight_norm(module: torch.nn.Module) -> None:
    from torch.nn.utils import parametrize
    for m in module.modules():
        if parametrize.is_parametrized(m, "weight"):
            parametrize.remove_parametrizations(m, "weight", leave_parametrized=True)
        elif hasattr(m, "weight_g") and hasattr(m, "weight_v"):
            torch.nn.utils.remove_weight_norm(m)


class _Body(torch.nn.Module):
    """Kokoro's Decoder + Generator, minus the harmonic source at the start and the inverse STFT at the end."""

    def __init__(self, decoder):
        super().__init__()
        self.d = decoder

    def forward(self, asr, F0_curve, N, s, har):
        d, g = self.d, self.d.generator
        F0 = d.F0_conv(F0_curve.unsqueeze(1))
        Nn = d.N_conv(N.unsqueeze(1))
        x = d.encode(torch.cat([asr, F0, Nn], dim=1), s)
        asr_res = d.asr_res(asr)
        res = True
        for block in d.decode:
            if res:
                x = torch.cat([x, asr_res, F0, Nn], dim=1)
            x = block(x, s)
            if block.upsample_type != "none":
                res = False
        for i in range(g.num_upsamples):
            x = F.leaky_relu(x, negative_slope=0.1)
            x_source = g.noise_res[i](g.noise_convs[i](har), s)
            x = g.ups[i](x)
            if i == g.num_upsamples - 1:
                x = g.reflection_pad(x)
            x = x + x_source
            xs = None
            for j in range(g.num_kernels):
                r = g.resblocks[i * g.num_kernels + j](x, s)
                xs = r if xs is None else xs + r
            x = xs / g.num_kernels
        return g.conv_post(F.leaky_relu(x))


def _source(decoder, F0_curve):
    g = decoder.generator
    har_source, _, _ = g.m_source(g.f0_upsamp(F0_curve[:, None]).transpose(1, 2))
    spec, phase = g.stft.transform(har_source.transpose(1, 2).squeeze(1))
    return torch.cat([spec, phase], dim=1)


def _finish(decoder, x):
    g = decoder.generator
    k = g.post_n_fft // 2 + 1
    return g.stft.inverse(torch.exp(x[:, :k, :]), torch.sin(x[:, k:, :]))


def speed_up(model, threads: int = 8) -> None:
    """Patch `model.decoder` (a kokoro KModel, e.g. KPipeline(...).model) to run its body on OpenVINO.
    Exports once (~210 MB, a few seconds) on the first sentence. Falls back to PyTorch if anything fails."""
    import openvino as ov
    os.environ.setdefault("OPENVINO_TELEMETRY_DISABLED", "1")
    dec = model.decoder
    plain = dec.forward
    state = {"run": None, "failed": False}
    names = ("asr", "F0", "N", "s", "har")

    def build(asr, F0_curve, N, s):
        path = CACHE / f"kokoro-decoder-body-{sum(p.numel() for p in dec.parameters())}.onnx"
        if not path.exists():
            d = copy.deepcopy(dec).eval()
            _fold_weight_norm(d)
            with torch.no_grad():
                har = _source(d, F0_curve)
            path.parent.mkdir(parents=True, exist_ok=True)
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                torch.onnx.export(
                    _Body(d), (asr, F0_curve, N, s, har), str(path), input_names=list(names), output_names=["x"],
                    dynamic_axes={"asr": {2: "t"}, "F0": {1: "f"}, "N": {1: "f"}, "har": {2: "h"}, "x": {2: "o"}},
                    opset_version=17, dynamo=False,
                )
        # CPU_RUNTIME_CACHE_CAPACITY=0: every sentence has its own length, and by default OpenVINO keeps compiled
        # kernels for each shape it has seen, which grew memory by ~8 MB per sentence.
        cm = ov.Core().compile_model(str(path), "CPU", {"INFERENCE_NUM_THREADS": threads, "PERFORMANCE_HINT": "LATENCY",
                                                        "CPU_RUNTIME_CACHE_CAPACITY": 0})
        return lambda *a: torch.from_numpy(cm({k: v.numpy() for k, v in zip(names, a)})[0].copy())

    def forward(asr, F0_curve, N, s):
        if state["failed"]:
            return plain(asr, F0_curve, N, s)
        try:
            if state["run"] is None:
                state["run"] = build(asr, F0_curve, N, s)
            with torch.no_grad():
                return _finish(dec, state["run"](asr, F0_curve, N, s, _source(dec, F0_curve)))
        except Exception as e:
            state["failed"] = True
            print(f"kokoro_fast: OpenVINO failed ({e!r}); using PyTorch")
            return plain(asr, F0_curve, N, s)

    dec.forward = forward


if __name__ == "__main__":
    import numpy as np
    import soundfile as sf
    from kokoro import KPipeline

    torch.set_num_threads(8)  # physical cores; hyperthreads made Kokoro slower on the test machine
    text = ("Since life first appeared on Earth about 3.7 billion years ago, countless species have emerged and "
            "gone extinct. But their essence lives on through the species we see around us today.")
    pipe = KPipeline(lang_code="a", repo_id="hexgrad/Kokoro-82M")

    def say(seed: int):
        torch.manual_seed(seed)  # Kokoro adds random noise: fix it to compare runs
        t0 = time.time()
        audio = np.concatenate([r.audio.numpy() for r in pipe(text, voice="af_heart", split_pattern=None)])
        return audio, time.time() - t0

    say(0)  # warm-up
    plain, tp = say(0)
    speed_up(pipe.model)
    say(0)  # first call exports and compiles
    fast, tf = say(0)
    n = min(len(plain), len(fast))
    snr = 10 * np.log10((plain[:n] ** 2).sum() / ((plain[:n] - fast[:n]) ** 2).sum())
    secs = len(plain) / 24000
    print(f"{secs:.1f} s of audio: PyTorch {secs / tp:.2f}x real time, OpenVINO decoder {secs / tf:.2f}x; "
          f"difference {snr:.0f} dB SNR (same seed), lengths {len(plain)} / {len(fast)}")
    sf.write("plain.wav", plain, 24000)
    sf.write("fast.wav", fast, 24000)
