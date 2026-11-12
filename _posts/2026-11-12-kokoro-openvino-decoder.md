---
layout: post
title: "Kokoro text-to-speech 40% faster on a laptop CPU, with the same sound"
description: "Kokoro spends 93% of its time in one part of the model. Running just that part on OpenVINO took a laptop CPU from 2.8× to 3.9× real time, and the audio still matches to 97 dB."
result: "2.8× → 3.9× real time, audio unchanged (97 dB)"
project: kokoro
tags: [kokoro, text-to-speech, performance]
---

[Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M) is a small, good-sounding text-to-speech model that runs
offline on a CPU. With the `af_heart` voice, out of the box, it runs at **2.8× real time**: a ten-hour book takes about
3 hours 35 minutes. With the change below it runs at **3.9×**, so the same book takes about 2 hours 35 minutes,
and you can't hear the difference, because there isn't one to speak of.

Test machine: a Ryzen 7 5700U laptop CPU (8 cores, 16 threads, AVX2, no AVX-512), 12 GB of RAM, Linux, no
usable GPU (the integrated Radeon has no PyTorch support). Software: kokoro 0.9.4, PyTorch 2.15 (CPU), OpenVINO 2026.4.1,
Python 3.12.

## Where the time goes

I timed each part of the model on one sentence:

| Part | Share of the time |
|---|---|
| Decoder (the vocoder that makes the waveform: 53M parameters of 1-D convolutions) | **93%** |
| Text model (bert, duration and pitch predictor) | 4% |
| Text → phonemes (misaki) | under 1% |

So the decoder is the whole story. Everything else, including the part that decides how long each word
lasts, can stay exactly as it is. That matters if you use Kokoro's per-word timestamps, for example to highlight
text as it's spoken: they come from the front of the model.

## Things that didn't help

- **More threads.** PyTorch's default here is 8 threads, one per physical core: 2.78× real time. Forcing all 16
  (hyperthreads included) made it *slower*, 1.7–1.9×. Four threads gave 2.31×.
- **Several processes.** Four processes with two threads each reached 3.25×, but every process holds its own copy
  of the model, about 6 GB in all. Not worth it once the next trick worked.
- **Folding weight-norm into the weights.** No change.
- **int8 or fp16.** This CPU has no VNNI and no native fp16, so both are slower here, not faster.
- **Kokoro's own ONNX export.** To export, Kokoro swaps its STFT for an approximation (`disable_complex=True`).
  Run through PyTorch with the same random seed, that version came out **about 15% louder**, with a measurably
  different spectrum. Fast, but it no longer sounds exactly like Kokoro.

## The decoder on other runtimes

The decoder is a stack of convolutions sandwiched between two small signal-processing steps: it builds a
sine-and-noise source from the pitch curve and takes its STFT, runs the convolutions, then turns the result back
into audio with an inverse STFT. The convolutions are the slow part. So I exported **only the convolutions** to
ONNX and kept both ends in PyTorch, exactly as Kokoro wrote them. The STFT stays the real one, and so does the
random noise.

Same 23 sentences (120 s of audio), 8 threads, whole-sentence speed:

| Decoder runs on | Speed | Gain | Audio vs PyTorch (same seed) |
|---|---|---|---|
| PyTorch (out of the box) | 2.56× | — | reference |
| PyTorch, traced and frozen | 2.88× | +12% | identical |
| ONNX Runtime 1.31 | 3.17× | +24% | 97 dB SNR |
| **OpenVINO 2026.4** | **3.80×** | **+48%** | **97 dB SNR**, same length, same loudness |

The baseline here is lower than 2.8× because other things were running; the gains held either way. End to end
with OpenVINO, nothing else running: **3.75–3.95× real time** over 600–900 words, against 2.78× before.

How close is "97 dB"? Kokoro adds random noise inside the decoder on every run, so two ordinary PyTorch runs with
*different* seeds differ from each other at about 20 dB. With the *same* seed, the OpenVINO version is 77 dB
closer than that. It's the same waveform, give or take float rounding.

## One trap: memory

Every sentence has a different length, and by default OpenVINO's CPU plugin caches compiled kernels for every
input shape it has seen. Over 200 sentences, memory went from 1.3 GB to 4.1 GB and kept climbing, which on a
12 GB machine ends with it freezing. One setting fixes it:

```python
cm = ov.Core().compile_model(path, "CPU", {"INFERENCE_NUM_THREADS": 8, "CPU_RUNTIME_CACHE_CAPACITY": 0})
```

With that, memory stays flat at about 2.7 GB (plain PyTorch: 1.9 GB) and the speed doesn't change.

## Do it yourself

[`kokoro_fast.py`]({{ '/assets/posts/kokoro-openvino-decoder/kokoro_fast.py' | relative_url }}) is the whole thing in one file,
about 160 lines. It works with stock Kokoro:

```python
from kokoro import KPipeline
from kokoro_fast import speed_up

pipe = KPipeline(lang_code="a", repo_id="hexgrad/Kokoro-82M")
speed_up(pipe.model, threads=8)          # use your physical core count
for r in pipe("Hello there.", voice="af_heart"):
    audio = r.audio                      # 24 kHz, as before
```

```
pip install kokoro openvino onnx soundfile    # plus CPU PyTorch, and espeak-ng as Kokoro's README says
python kokoro_fast.py                         # makes plain.wav and fast.wav, prints both speeds and the difference
```

The first sentence exports the convolution stack (about 210 MB, cached in `~/.cache/kokoro-fast`) and takes a
few seconds longer. If OpenVINO fails for any reason, it falls back to plain PyTorch.

## Limits

- Measured on one AMD laptop CPU. OpenVINO is usually at its best on Intel CPUs, so the gain may be larger
  there; on other AMD or ARM machines, measure first.
- Tested with the `af_heart` voice and English text. Other voices use the same decoder, so they should behave the
  same, but I haven't measured them.
- One process. The trick and the multi-process approach can be combined, but each process then holds a 210 MB
  model plus its own runtime.

## Sources

- [Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M) and its [code](https://github.com/hexgrad/kokoro)
- [OpenVINO](https://docs.openvino.ai/)
- Other Kokoro exports, for comparison: [nvidia/kokoro-82M-onnx-opt](https://huggingface.co/nvidia/kokoro-82M-onnx-opt),
  [an OpenVINO FP16 conversion](https://huggingface.co/Echo9Zulu/Kokoro-82M-FP16-OpenVINO), and
  [notes on the export's phase difference](https://huggingface.co/christopherthompson81/kokoro-82m-onnx)
- [A CPU benchmark of Kokoro on PyTorch and ONNX](https://bittide.aicompass.dev/article/213f0a6c-be96-402b-8672-c2d9d3cb6029)
