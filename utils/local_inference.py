"""Local Hugging Face model loading and inference (no API keys)."""

from __future__ import annotations

import json
import os
import re
import time
from functools import lru_cache
from pathlib import Path

import config
from utils.disk_space import (
    MIN_FREE_GB,
    ensure_writable_dir,
    estimate_video_bytes,
    is_disk_quota_error,
)


def _wan_progress_enabled() -> bool:
    return os.environ.get("WAN_PROGRESS", "1").lower() not in ("0", "false", "no")


def _configure_pipeline_progress(pipe, desc: str = "diffusion") -> None:
    """Enable diffusers tqdm on the pipeline (set WAN_PROGRESS=0 to disable)."""
    if hasattr(pipe, "set_progress_bar_config"):
        pipe.set_progress_bar_config(disable=not _wan_progress_enabled(), desc=desc)


def _make_wan_step_callback(total_steps: int):
    """Log one line per denoising step (works even when tqdm is off)."""

    def callback(_pipe, step_index: int, timestep, callback_kwargs):
        if _wan_progress_enabled():
            step = step_index + 1
            pct = 100.0 * step / total_steps
            print(
                f"[Local Video] Step {step}/{total_steps} ({pct:.0f}%) "
                f"timestep={float(timestep):.0f}",
                flush=True,
            )
        return callback_kwargs

    return callback

config.HF_CACHE_DIR.mkdir(parents=True, exist_ok=True)


def log_gpu_setup() -> None:
    """Print once which physical GPU the process will use."""
    import torch

    vis = os.environ.get("CUDA_VISIBLE_DEVICES", "(all)")
    dev = config.LOCAL_DEVICE
    if torch.cuda.is_available():
        idx = int(dev.split(":")[1]) if ":" in dev else 0
        name = torch.cuda.get_device_name(idx)
        print(
            f"[GPU] LOCAL_DEVICE={dev}  CUDA_VISIBLE_DEVICES={vis}  "
            f"torch.cuda.device_count()={torch.cuda.device_count()}  name={name}"
        )
    else:
        print(f"[GPU] CUDA unavailable; LOCAL_DEVICE={dev}  CUDA_VISIBLE_DEVICES={vis}")


_device_logged = False


def _device():
    """Resolve device; fall back to CPU if CUDA driver/runtime mismatch."""
    import torch

    global _device_logged
    if not _device_logged:
        log_gpu_setup()
        _device_logged = True

    requested = config.LOCAL_DEVICE
    if requested == "auto":
        return "cuda" if torch.cuda.is_available() else "cpu"
    if requested.startswith("cuda"):
        if not torch.cuda.is_available():
            print(
                f"[Local] WARNING: {requested} unavailable (driver/CUDA mismatch). "
                "Using CPU — set LOCAL_DEVICE=cpu or reinstall torch for cu124. See README."
            )
            return "cpu"
        if ":" in requested:
            try:
                idx = int(requested.split(":")[1])
                count = torch.cuda.device_count()
                if idx >= count:
                    fallback = f"cuda:{count - 1}"
                    print(
                        f"[Local] WARNING: {requested} is invalid (only {count} device(s) visible under current environment/CUDA_VISIBLE_DEVICES). "
                        f"Falling back to {fallback}."
                    )
                    return fallback
            except (ValueError, IndexError):
                pass
    return requested


def _torch_dtype():
    import torch
    return torch.bfloat16 if _device() != "cpu" else torch.float32


@lru_cache(maxsize=1)
def get_llm_pipeline():
    """Load causal LM for agent JSON generation."""
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    model_id = config.LOCAL_LLM_MODEL
    cache = str(config.HF_CACHE_DIR)
    token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN")
    print(f"[Local LLM] Loading {model_id} on {_device()} from {cache}...")
    tokenizer = AutoTokenizer.from_pretrained(
        model_id, cache_dir=cache, token=token, trust_remote_code=True
    )
    dev = _device()
    model = AutoModelForCausalLM.from_pretrained(
        model_id,
        cache_dir=cache,
        token=token,
        dtype=_torch_dtype(),
        device_map=dev if dev != "cpu" else None,
        trust_remote_code=True,
    )
    if dev == "cpu":
        model = model.to("cpu")
    model.eval()
    return tokenizer, model


@lru_cache(maxsize=1)
def get_image_pipeline():
    """Load image diffusion pipeline (SDXL-Turbo by default — fast, good quality)."""
    import torch
    from diffusers import AutoPipelineForText2Image

    model_id = config.LOCAL_IMAGE_MODEL
    cache = str(config.HF_CACHE_DIR)
    token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN")
    print(f"[Local Image] Loading {model_id} on {_device()} from {cache}...")
    kwargs = {
        "cache_dir": cache,
        "token": token,
        "torch_dtype": _torch_dtype(),
    }
    if "xl" in model_id.lower():
        kwargs["variant"] = "fp16"
    pipe = AutoPipelineForText2Image.from_pretrained(model_id, **kwargs)
    pipe = pipe.to(_device())
    if hasattr(pipe, "set_progress_bar_config"):
        pipe.set_progress_bar_config(disable=True)
    return pipe


def generate_text_local(
    system_prompt: str,
    user_prompt: str,
    max_tokens: int = 4000,
    temperature: float | None = None,
) -> str:
    """Run local causal LM with chat template."""
    if temperature is None:
        temperature = config.LLM_TEMPERATURE_DEFAULT
    import torch

    tokenizer, model = get_llm_pipeline()
    messages = [
        {
            "role": "system",
            "content": (
                system_prompt
                + "\nWhen asked for JSON: output ONE filled JSON object with real values. "
                "Never output JSON Schema types like {\"type\": \"string\"}."
            ),
        },
        {"role": "user", "content": user_prompt},
    ]
    if hasattr(tokenizer, "apply_chat_template"):
        text = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    else:
        text = f"{system_prompt}\n\n{user_prompt}"

    inputs = tokenizer(text, return_tensors="pt").to(model.device)
    with torch.no_grad():
        out = model.generate(
            **inputs,
            max_new_tokens=min(max_tokens, 4096),
            temperature=max(temperature, 0.01),
            do_sample=temperature > 0,
            pad_token_id=tokenizer.eos_token_id,
        )
    generated = out[0][inputs["input_ids"].shape[1]:]
    return tokenizer.decode(generated, skip_special_tokens=True).strip()


def generate_image_local(prompt: str, output_path: Path, seed: int | None = None) -> str:
    """Text-to-image for 9:16 Shorts keyframes."""
    import torch

    pipe = get_image_pipeline()
    full_prompt = (
        f"{prompt}, 3D Pixar cartoon style, Indian school educational scene, "
        "vibrant colors, child-friendly, highly detailed, vertical composition"
    )
    negative = "text, watermark, blurry, ugly, deformed, low quality, photorealistic horror"

    gen = torch.Generator(device=_device()).manual_seed(seed or config.LOCAL_IMAGE_SEED)

    kwargs = {
        "prompt": full_prompt,
        "negative_prompt": negative,
        "generator": gen,
        "num_inference_steps": config.LOCAL_IMAGE_STEPS,
    }
    # SDXL-Turbo uses 1 step; SD 1.5 uses more
    if "turbo" in config.LOCAL_IMAGE_MODEL.lower():
        kwargs["num_inference_steps"] = 4
        kwargs["guidance_scale"] = 0.0
    else:
        kwargs["guidance_scale"] = 7.5

    # Generate at 9:16 then upscale in ffmpeg if needed
    kwargs["height"] = min(config.VIDEO_HEIGHT, 1280)
    kwargs["width"] = min(config.VIDEO_WIDTH, 720)

    image = pipe(**kwargs).images[0]
    output_path = Path(output_path)
    ensure_writable_dir(output_path.parent, min_gb=0.5, label="SDXL image")
    image.save(output_path)
    print(f"[Local Image] Saved {output_path}")
    return str(output_path)


@lru_cache(maxsize=1)
def get_video_pipeline():
    """Load Wan2.1 T2V Diffusers pipeline (requires Wan-AI/Wan2.1-T2V-1.3B-Diffusers)."""
    import torch
    from diffusers import AutoencoderKLWan, WanPipeline

    model_id = config.LOCAL_VIDEO_MODEL
    if model_id == "Wan-AI/Wan2.1-T2V-1.3B":
        model_id = "Wan-AI/Wan2.1-T2V-1.3B-Diffusers"
        print(
            "[Local Video] WARNING: Wan2.1-T2V-1.3B is raw weights; "
            "using Wan-AI/Wan2.1-T2V-1.3B-Diffusers instead."
        )

    cache = str(config.HF_CACHE_DIR)
    token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN")
    dev = _device()
    print(f"[Local Video] Loading {model_id} on {dev} from {cache}...")

    if get_image_pipeline.cache_info().currsize > 0:
        get_image_pipeline.cache_clear()
        torch.cuda.empty_cache()
        print("[Local Video] Freed image pipeline VRAM")

    load_kw = dict(cache_dir=cache, token=token, torch_dtype=torch.bfloat16)
    try:
        try:
            vae_kw = load_kw.copy()
            vae_kw["torch_dtype"] = torch.float32
            vae_kw["local_files_only"] = True
            vae = AutoencoderKLWan.from_pretrained(
                model_id, subfolder="vae", **vae_kw
            )
            pipe_kw = load_kw.copy()
            pipe_kw["local_files_only"] = True
            pipe = WanPipeline.from_pretrained(model_id, vae=vae, **pipe_kw)
        except Exception:
            vae_kw = load_kw.copy()
            vae_kw["torch_dtype"] = torch.float32
            vae = AutoencoderKLWan.from_pretrained(
                model_id, subfolder="vae", **vae_kw
            )
            pipe = WanPipeline.from_pretrained(model_id, vae=vae, **load_kw)
    except OSError as e:
        raise RuntimeError(
            f"Failed to load {model_id}. Download Diffusers weights:\n"
            f"  export HF_TOKEN=hf_xxx\n"
            f"  huggingface-cli download {model_id} --cache-dir {cache}\n"
            f"Or set VIDEO_BACKEND=local_image in .env\n"
            f"Original error: {e}"
        ) from e

    pipe.to(dev)
    _configure_pipeline_progress(pipe, desc="Wan denoise")
    print(f"[Local Video] Pipeline ready on {dev}")
    return pipe


def generate_video_local(
    prompt: str,
    output_path: Path,
    num_frames: int = 81,
    height: int = 480,
    width: int = 832,
    guidance_scale: float = 6.0,
    num_inference_steps: int = 50,
    seed: int | None = None,
) -> str:
    """Generate a short video clip from a text prompt using Wan2.1-T2V.

    Returns path to the saved MP4.
    Default: 81 frames at 16fps ≈ 5 seconds, landscape 832×480.
    For 9:16 vertical: swap to height=832, width=480.
    """
    import torch
    from diffusers.utils import export_to_video

    pipe = get_video_pipeline()
    dev = _device()
    gen = torch.Generator(device=dev).manual_seed(seed or config.LOCAL_IMAGE_SEED)

    full_prompt = (
        f"{prompt}. "
        "Smooth animation, 3D cartoon educational style, "
        "vibrant colors, cinematic lighting, sharp detail, high quality"
    )
    neg = getattr(config, "WAN_NEGATIVE_PROMPT", "")

    width = (int(width) // 16) * 16
    height = (int(height) // 16) * 16
    if width < 16 or height < 16:
        raise ValueError(f"Invalid Wan size {width}x{height}; need both >= 16 and divisible by 16")

    print(
        f"[Local Video] Generating {num_frames} frames at {width}x{height}, "
        f"{num_inference_steps} steps (upsampled to {config.VIDEO_WIDTH}x{config.VIDEO_HEIGHT} in compose)..."
    )
    if os.environ.get("LOG_WAN_PROMPT", "1").lower() not in ("0", "false", "no"):
        print(f"[Local Video] Prompt:\n{full_prompt}\n")
    t0 = time.time()
    pipe_kw = dict(
        prompt=full_prompt,
        height=height,
        width=width,
        num_frames=num_frames,
        guidance_scale=guidance_scale,
        num_inference_steps=num_inference_steps,
        generator=gen,
        callback_on_step_end=_make_wan_step_callback(num_inference_steps),
        callback_on_step_end_tensor_inputs=[],
    )
    if neg:
        pipe_kw["negative_prompt"] = neg
    output = pipe(**pipe_kw)
    print(f"[Local Video] Denoise finished in {time.time() - t0:.1f}s — decoding VAE / writing mp4...")

    video_frames = output.frames[0]
    output_path = Path(output_path)
    need_gb = max(MIN_FREE_GB, estimate_video_bytes(len(video_frames), width, height) / (1024**3) * 1.2)
    ensure_writable_dir(output_path.parent, min_gb=need_gb, label="Wan mp4 export")
    try:
        export_to_video(video_frames, str(output_path), fps=16)
    except (OSError, BrokenPipeError) as e:
        if is_disk_quota_error(e):
            raise OSError(
                f"Disk quota exceeded writing {output_path}. "
                f"Free disk space or set NCERT_OUTPUT_DIR to a writable path and re-run."
            ) from e
        raise
    if not output_path.exists() or output_path.stat().st_size == 0:
        raise OSError(f"Wan mp4 export produced empty file: {output_path}")
    print(f"[Local Video] Saved {output_path} ({len(video_frames)} frames, {output_path.stat().st_size // 1024} KB)")
    return str(output_path)


def unload_video_pipelines() -> None:
    """Free VRAM when switching T2V ↔ I2V."""
    import torch

    get_video_pipeline.cache_clear()
    get_i2v_pipeline.cache_clear()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()


@lru_cache(maxsize=1)
def get_i2v_pipeline():
    """Wan2.1 image-to-video (14B 480P by default)."""
    import torch
    from diffusers import AutoencoderKLWan, WanImageToVideoPipeline
    from transformers import CLIPVisionModel

    model_id = config.WAN_I2V_MODEL
    cache = str(config.HF_CACHE_DIR)
    token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN")
    dev = _device()
    print(f"[Wan I2V] Loading {model_id} on {dev}...")

    base_kw = dict(cache_dir=cache, token=token)
    load_kw = {**base_kw, "torch_dtype": torch.bfloat16}
    enc_kw = {**base_kw, "torch_dtype": torch.float32}
    vae_kw = {**base_kw, "torch_dtype": torch.float32}

    try:
        enc_kw["local_files_only"] = True
        vae_kw["local_files_only"] = True
        pipe_kw = {**load_kw, "local_files_only": True}
        image_encoder = CLIPVisionModel.from_pretrained(
            model_id, subfolder="image_encoder", **enc_kw
        )
        vae = AutoencoderKLWan.from_pretrained(model_id, subfolder="vae", **vae_kw)
        pipe = WanImageToVideoPipeline.from_pretrained(
            model_id, vae=vae, image_encoder=image_encoder, **pipe_kw
        )
    except Exception:
        image_encoder = CLIPVisionModel.from_pretrained(
            model_id, subfolder="image_encoder", **enc_kw
        )
        vae = AutoencoderKLWan.from_pretrained(model_id, subfolder="vae", **vae_kw)
        pipe = WanImageToVideoPipeline.from_pretrained(
            model_id, vae=vae, image_encoder=image_encoder, **load_kw
        )
    pipe.to(dev)
    _configure_pipeline_progress(pipe, desc="Wan I2V denoise")
    print(f"[Wan I2V] Pipeline ready on {dev}")
    return pipe


def generate_video_i2v_local(
    prompt: str,
    image_path: Path,
    output_path: Path,
    num_frames: int = 81,
    height: int = 832,
    width: int = 480,
    guidance_scale: float = 5.0,
    num_inference_steps: int = 40,
    seed: int | None = None,
) -> str:
    """Animate from a seed frame using Wan2.1 I2V."""
    import numpy as np
    import torch
    from diffusers.utils import export_to_video
    from PIL import Image

    pipe = get_i2v_pipeline()
    dev = _device()
    gen = torch.Generator(device=dev).manual_seed(seed or config.LOCAL_IMAGE_SEED)

    image = Image.open(image_path).convert("RGB")
    width = (int(width) // 16) * 16
    height = (int(height) // 16) * 16
    mod = pipe.vae_scale_factor_spatial * pipe.transformer.config.patch_size[1]
    max_area = height * width
    aspect = image.height / max(image.width, 1)
    h = round(np.sqrt(max_area * aspect)) // mod * mod
    w = round(np.sqrt(max_area / aspect)) // mod * mod
    image = image.resize((w, h))

    full_prompt = (
        f"{prompt}. Smooth animation, 3D cartoon educational style, "
        "vibrant colors, cinematic motion, sharp detail, high quality"
    )
    neg = getattr(config, "WAN_NEGATIVE_PROMPT", "")
    print(
        f"[Wan I2V] {num_frames} frames from {Path(image_path).name} "
        f"at {w}x{h}, {num_inference_steps} steps"
    )
    if os.environ.get("LOG_WAN_PROMPT", "1").lower() not in ("0", "false", "no"):
        print(f"[Wan I2V] Prompt:\n{full_prompt}\n")

    t0 = time.time()
    pipe_kw = dict(
        image=image,
        prompt=full_prompt,
        height=h,
        width=w,
        num_frames=num_frames,
        guidance_scale=guidance_scale,
        num_inference_steps=num_inference_steps,
        generator=gen,
        callback_on_step_end=_make_wan_step_callback(num_inference_steps),
        callback_on_step_end_tensor_inputs=[],
    )
    if neg:
        pipe_kw["negative_prompt"] = neg
    output = pipe(**pipe_kw)
    print(f"[Wan I2V] Denoise finished in {time.time() - t0:.1f}s")
    video_frames = output.frames[0]
    output_path = Path(output_path)
    need_gb = max(MIN_FREE_GB, estimate_video_bytes(len(video_frames), w, h) / (1024**3) * 1.2)
    ensure_writable_dir(output_path.parent, min_gb=need_gb, label="Wan I2V mp4 export")
    export_to_video(video_frames, str(output_path), fps=16)
    if not output_path.exists() or output_path.stat().st_size == 0:
        raise OSError(f"Wan I2V export empty: {output_path}")
    print(f"[Wan I2V] Saved {output_path}")
    return str(output_path)


def repair_json(text: str) -> str:
    """Extract JSON object/array from model output."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    # Find first [ or {
    for start_char, end_char in [("[", "]"), ("{", "}")]:
        i = text.find(start_char)
        if i >= 0:
            depth = 0
            for j in range(i, len(text)):
                if text[j] == start_char:
                    depth += 1
                elif text[j] == end_char:
                    depth -= 1
                    if depth == 0:
                        candidate = text[i : j + 1]
                        try:
                            json.loads(candidate)
                            return candidate
                        except json.JSONDecodeError:
                            break
    return text
