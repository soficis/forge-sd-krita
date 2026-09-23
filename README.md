# Forge SD-Krita Plugin

A Krita plugin for generating, transforming, and editing images with the [Forge Neo](https://github.com/Haoming02/sd-webui-forge-classic/tree/neo) backend.

> [!CAUTION]
> **DISCLAIMER: EXPERIMENTAL & WORK IN PROGRESS**
> This plugin is in active development and **most likely is NOT in a fully functional or stable state for end-user production use**. Expect rough edges, missing error handling, unhandled edge cases, breaking changes, and potential UI crashes.
> 
> Please review the [Known Issues & Limitations](#%EF%B8%8F-known-issues--limitations) and the [Testing & Verification Guide](#-testing--verification-guide) before attempting to use or test the plugin.

---

## 📦 What's New in 1.1.0

A feature-completion release on top of 1.0.0 — the automated suite grew from 330 to **1053 tests, all passing**.

- **Reliability**: History **Reuse** now restores every field (model, sampler, seed, CFG, prompt); ControlNet survives error payloads; thread-handle races guarded; silent failures are logged; connection failures surface in a top banner with disabled-button tooltips; timers stop on page close; mask visibility is restored after generation.
- **Validation**: empty prompts and invalid batch/steps/seed values are rejected client-side with an inline `Cannot generate: …` message before anything reaches the server.
- **Artist tools**: Prompt Presets (save/load/rename/delete, max 50), Smart-size resolution suggestions (img2img + inpaint), and a one-click **Quick Mask** bootstrap on inpaint.
- **Generation**: collapsible **Tiled (high-res)** controls on txt2img; live canvas preview (512 px capped, malformed frames skipped) during txt2img/img2img/inpaint; Flux dynamic sizing and control visibility per family; an IP-Adapter reference slot that appears only when the backend advertises it.
- **Extensions & data**: ADetailer model list fetched from the API; Segmentation Map page renders a searchable color list; dead `sd_api` file-IO helpers removed; `qt_compat` now exports explicit symbols instead of star imports.
- **Polish & docs**: measured performance fixes (settings save, history, API cache, preview), empty states / disabled-button tooltips / loading indicator, this README's User Guide, and a full walkthrough in `docs/GUIDE.md` (local-only).

Still open (not in 1.1.0): txt2img Hires Fix does not re-apply family size rules on model change, the Smart-size widget is not on the txt2img page, and `generate_widget.cleanup()` is never reached from `page.cleanup()` (latent). Full detail lives in the local-only `docs/CHANGELOG.md` and `docs/STATUS.md`.

---

## 🛠️ Requirements & Prerequisites

- **Krita**: Krita 5.2+ or Krita 6.0+ with Python Plugin Manager enabled (PyQt5 / PyQt6 auto-detected)
- **Python**: Krita-bundled Python — tested on 3.12 / 3.13 / 3.14
- **Backend**: Forge Neo backend (branch `neo` only, not A1111/classic) started with `--api` (`set COMMANDLINE_ARGS=--api`), default `http://127.0.0.1:7860`
- **Dependencies**: stdlib + krita + PyQt5/PyQt6 only — no pip needed

### Backend Requirement

This plugin specifically targets and requires **Forge Neo** (branch `neo`). Original Forge WebUI (A1111 legacy architecture) is not supported.

Forge Neo features utilized by this plugin:
- Native support for Flux, Flux2, Anima, Z-Image, Krea2, Qwen-Image, and Wan models
- Model-aware UI presets (`sd`, `xl`, `flux`, `klein`, `qwen`, `lumina`, `zit`, `wan`, `anima`, `ernie`, `pid`, `krea`)
- Additional modules system for text encoders and VAEs

---

## 📊 Status & Supported Model Families

The plugin auto-detects **9 model families** from checkpoint filenames and automatically configures Forge Neo presets, text encoders, VAEs, samplers, schedulers, CFG scales, size defaults, and UI visibility.

### 1. Model Matrix & Setup Requirements

| Model Family | Detection Keywords | Forge Preset | Text Encoder | VAE | Sampler / Scheduler | CFG Defaults |
|---|---|---|---|---|---|---|
| **SD 1.5** | (default fallback) | `sd` | — | — | Euler a / Automatic | 7.0 (range 0-30) |
| **SDXL** | `sdxl` | `xl` | — | — | Euler a / Automatic | 5.0 (range 0-30) |
| **Flux.1** | `flux`, `nunchaku` | `flux` | `clip_l` + `t5xxl_fp16` | `ae.safetensors` | Euler / Simple | 1.0 (Distilled CFG 3.5) |
| **Flux2 Klein** | `flux2`, `klein-4b`, `klein-9b` | `klein` | `qwen_3_4b` / `qwen_3_8b` | `flux2-vae.safetensors` | Euler / Simple | 1.0 (fixed 4 steps) |
| **Anima** | `anima`, `wai-anima` | `anima` | `qwen_3_06b_base` | `qwen_image_vae.safetensors` | ER SDE / Beta | 4.0 (shift 3.0, 32 steps) |
| **Z-Image Turbo** | `z-image`, `z_image` | `zit` | `qwen_3_4b` | `ae.safetensors` | Euler / Beta | 1.0 (fixed, 8-9 steps) |
| **Krea2** | `krea2`, `krea-2` | `krea` | `qwen3vl_4b_fp8_scaled` | `qwen_image_vae.safetensors` | Euler / Simple | RAW: 4.5 / Turbo: 0.0 (fixed) |
| **Qwen-Image** | `qwen-image` | `qwen` | `qwen_2.5_vl_7b_fp8_scaled` | `qwen_image_vae.safetensors` | Euler / Simple | 4.0 (range 0-10, 30 steps) |
| **Wan** | `wan` | `wan` | — | — | Euler a / Automatic | 7.0 (range 0-30) |

*Note: Model files go into Forge Neo's `models/` subdirectories: Checkpoints in `models/Stable-diffusion/`, VAEs in `models/VAE/`, and Text Encoders in `models/text_encoder/`.*

### 2. Architecture-Aware Size Defaults

When a model is detected, min/max generation bounds are set automatically:

| Architecture | Default Min Size | Default Max Size | Hard Floor |
|---|---|---|---|
| **SD 1.5** | 512 | 2048 | 256 |
| **SDXL / Flux / Flux2 / Anima / Z-Image / Krea2 / Qwen** | 512 | 2048 | 512 |
| **Wan** | 256 | 1024 | 256 |

### 3. UI Adaptation Per Model

- **Negative Prompt**: Hidden for Flux/Flux2/Z-Image/Krea2 Turbo. Shown for SD/SDXL/Anima/Krea2 RAW/Qwen/Wan.
- **Styles Selector**: Hidden for Flux/Flux2. Shown for all other models.
- **CFG Scale Label**: Displays as "Distilled CFG" for Flux, "Guidance Scale" for Krea2/Qwen, or "CFG fixed" for Turbo models.

### 4. Turbo Distill LoRA Detection

The plugin inspects prompt text for turbo/distill LoRA tags and automatically adjusts sampling steps and CFG:
- `<lora:*turbo*:*>` → 8 steps
- `<lora:*hyper-sd*:*>` / `<lora:*hyper_sd*:*>` → 8 steps, CFG 3.5
- `<lora:*lcm*:*>` → 4 steps, CFG 1.0
- `<lora:*alimama*:*>` → 8 steps, CFG 3.5

---

## ✨ Features & Generation Modes

### Txt2Img (Text-to-Image)
- Prompt & Negative Prompt input (negative prompt hides dynamically for unsupported models).
- Model selection with auto-configuration of sampler, scheduler, steps, and CFG.
- Batch generation and fixed or random seed generation.

### Img2Img (Image-to-Image)
- Transforms active selection or layer in Krita based on prompt.
- **Denoise Strength Guide**: `0.1–0.3` (subtle color/style tweaks), `0.3–0.5` (moderate restyle), `0.5–0.7` (major transformation), `0.7–1.0` (complete reinterpretation).

### Inpaint (Masked Region Generation)
- Fill masked regions seamlessly. White = inpaint area, Black = preserve area.
- Auto-update mask, mask blur adjustment, and Soft Inpainting blending support.

### Job Queue & History
- Sequential job queuing with queue status and job cancellation/clearing.
- Generation history with image thumbnails, search filtering, pagination, and settings restoration.

### Additional Tools & Extensions
- **Upscale**: Single-image upscaling via `extra-single-image` endpoint (Lanczos, 4x-UltraSharp, 4x-AnimeSharp).
- **Interrogate**: Image-to-prompt captioning using CLIP models.
- **Remove Background**: RemBG integration with alpha matting and mask outputs.
- **ControlNet & ADetailer**: Multi-unit ControlNet configuration and automatic face/hand detail enhancement.
- **Simplify UI**: Hide unused widgets while preserving default settings.

---

## 🚀 Installation & Setup

### 1. Enable API Access on Forge Neo

In your Forge Neo directory, edit `webui-user.bat` (or shell script equivalent) to include `--api`:

```bat
set COMMANDLINE_ARGS=--api
```

### 2. Install Plugin into Krita

#### Easy Install (Standard Copy)

1. Launch Krita → **Settings > Manage Resources** → click **Open Resource Folder** (bottom right).
2. Open the `pykrita` subfolder inside the opened file explorer window.
3. Copy both the `forge` directory and `forge.desktop` file into `pykrita`.
4. Restart Krita.

#### Symlink Install (Git Auto-Updates)

```bat
:: Windows (Run Command Prompt as Administrator)
mklink /j "%APPDATA%\krita\pykrita\forge" "C:\path\to\cyanic-sd-krita\forge"
mklink "%APPDATA%\krita\pykrita\forge.desktop" "C:\path\to\cyanic-sd-krita\forge.desktop"
```

```sh
# Linux
ln -s ~/.local/share/krita/pykrita/forge /path/to/cyanic-sd-krita/forge
ln -s ~/.local/share/krita/pykrita/forge.desktop /path/to/cyanic-sd-krita/forge.desktop
```

### 3. Enable Plugin in Krita

1. Restart Krita.
2. Go to **Settings > Configure Krita... > Python Plugin Manager**.
3. Check the box for **forge SD Plugin for Krita**.
4. Restart Krita.
5. Open Docker: **Settings > Dockers > Forge SD**.

---

## 🧭 User Guide

Quick start: open the **Settings** tab, enter your server URL (default `http://127.0.0.1:7860`), and click **Connect**. While disconnected, a banner at the top of the docker shows the failure reason and the Generate, Cancel, and Remove Background buttons stay disabled. Empty prompts are blocked before they reach the server with a `Cannot generate: ...` message under the Generate button.

One line per mode:

- **Txt2Img**: prompt to a new layer, with Prompt Presets (save/load/rename/delete, max 50) and a collapsible **Tiled (high-res)** section (tile size 512/768/1024, overlap 0-128 px).
- **Img2Img**: transform a selection, layer, or canvas with a Denoise Strength slider; **Smart size** suggests a step-aligned resolution; inline Interrogate block for quick captioning.
- **Inpaint**: paint white on the mask layer (**Quick Mask** bootstraps one), with mask blur, Soft Inpainting, and restore-after-generate mask visibility.
- **Upscale**: scale by factor or to exact dimensions via `extra-single-image`, with optional canvas resize.
- **Interrogate**: caption an image with CLIP; insert as replace, append, or prepend into a chosen mode's prompt.
- **Remove Background**: RemBG models (u2net, isnet, and friends) with alpha matting and mask output.
- **ControlNet**: multi-unit preprocessor/model configs under Extensions; the IP-Adapter reference slot appears only when the backend advertises it.
- **ADetailer**: face and detail enhancement; model list fetched from the API, not hardcoded.
- **Segmentation Map** (seg-map): searchable color list for ControlNet segmentation masks (browse and search only).

Shared workflow: live preview (512 px capped) updates on the canvas during txt2img, img2img, and inpaint jobs when enabled in Settings; generation history at the bottom of each page searches, pages 20 at a time, and **Reuse** restores a full entry (model, sampler, seed, CFG, prompt, and the rest).

For symptom-by-symptom fixes see `docs/TROUBLESHOOTING.md`; for checkpoint, text encoder, and VAE requirements see `docs/MODELS.md` or the [Model Matrix](#1-model-matrix--setup-requirements) above. A longer walkthrough lives in `docs/GUIDE.md` (local-only docs folder, not tracked).

---

## 🧪 Testing & Verification Guide

The project includes an automated test suite for domain logic alongside manual testing procedures.

### 1. Automated Unit Tests

Execute the unit test suite across domain logic and critical widget paths (**1053 tests** as of 1.1.0):

```bash
# Run all 1053 tests
python -m pytest tests/ -v
```

#### Test Suite Breakdown

| Module | Tests | Focus Area |
|---|---|---|
| `test_model_registry.py` | 149 | 9-model family regex detection, forge presets, CFG profiles, and size defaults |
| `test_smart_resolution.py` | 130 | Step-aligned resolution suggestion math |
| `test_ui_surface.py` | 92 | Widget/page surface construction tests |
| `test_controlnet_dict_guards.py` | 83 | Non-dict / error-payload guards in ControlNet and sd_api |
| `test_qt_compat_imports.py` | 67 | Explicit `qt_compat` symbol surface |
| `test_controlnet_ip_adapter.py` | 48 | IP-Adapter capability gating and wiring |
| `test_generation_validation.py` | 46 | Client-side prompt/batch/steps/seed validation |
| `test_generation_plan.py` | 40 | Aspect ratio math, canvas bounds scaling, and pixel alignment |
| `test_payload_builder.py` | 36 | Translation of plugin parameters to API payload formats and model overrides |
| `test_settings_controller.py` | 35 | Settings migration, loading defaults, fallback defaults, and debounced saving |
| `test_flux_ui.py` | 35 | Flux dynamic sizing and control visibility |
| `test_ux_polish.py` | 32 | Empty states, disabled tooltips, loading indicator, spacing |
| `test_prompt_presets.py` | 29 | Prompt preset CRUD |
| `test_connection_errors.py` | 28 | Connection failure modes and banner surfacing |
| `test_seg_map.py` | 28 | Segmentation map list rendering and search |
| `test_sd_api.py` | 26 | Backend connection state machine, retry logic, and payload dispatching |
| `test_progress_state.py` | 26 | Parsing Forge progress polling API responses |
| `test_task18_widget_todos.py` | 22 | Triaged widget TODO paths |
| `test_tiled_txt2img.py` | 17 | Tiled generation control wiring |
| `test_timer_cleanup.py` | 15 | Timer teardown on page/widget cleanup |
| `test_history_manager.py` | 18 | Generation history storage, search filtering, pagination, and TTL cleanup |
| `test_adetailer_models.py` | 13 | API-driven ADetailer model list |
| `test_live_preview.py` | 12 | Live preview frames and 512 px cap |
| `test_mask_visibility.py` | 9 | Mask layer snapshot/restore around generation |
| `test_quick_mask.py` | 8 | Quick Mask layer bootstrap |
| `test_krita_adapter_thread.py` | 5 | Concurrent-thread guard in `run_as_thread()` |
| `test_models_history_reuse.py` | 4 | Full history entry restore via copy-on-reuse |
| **Total** | **1053** | |

### 2. Manual Verification Checklist

When deploying changes to Krita (`pykrita/forge`), manually verify:
1. **Connection**: Connect to `http://127.0.0.1:7860` in Settings tab. Verify status turns green.
2. **Txt2Img**: Select an SDXL or Flux model. Verify prompt generation creates a new layer.
3. **Img2Img**: Select a canvas area and generate with Denoise 0.5.
4. **Inpaint**: Paint a white mask on a new layer and generate inpaint content.
5. **RemBG & Upscale**: Test background removal and single image upscaling.

### 3. Compilation Check

Verify Python syntax across all codebase files:

```bash
python -m py_compile forge/*.py forge/*/*.py
```

---

## ⚠️ Known Issues & Limitations

> [!WARNING]
> **Most UI code still lacks dedicated unit tests, and a few follow-ups remain open.**
> 
> Core domain logic and critical widget paths have **1053 unit tests**, but most of the ~5,600 lines of PyQt widget, page, and docker code remain untested — expect occasional unhandled Qt edge cases. The critical 1.0.0 issues (history reuse, ControlNet error crashes, thread races, silent exception swallowing, missing prompt validation, mask visibility, timer leaks, hardcoded ADetailer models, skeleton Segmentation Map page) were fixed in 1.1.0 — see [What's New](#-whats-new-in-110).
> 
> Still open:
> - **Open follow-ups**: txt2img Hires Fix does not re-apply per-family size rules on model change; the Smart-size widget is not on the txt2img page; and `generate_widget.cleanup()` is never reached from `page.cleanup()` because `self.widgets` excludes it (latent).
> - **Untested UI infrastructure**: the majority of PyQt widget and page implementation code still has no dedicated test coverage (critical paths are covered).
> - **Single-model backend (no concurrent model switching)**: Forge Neo serves ONE model at a time (single model loaded) — switching models unloads/reloads the backend, so concurrent multi-model generation or instant switching is unsupported by design.
> - **Flux2 Dev 32B unsupported (Klein 4B/9B only)**: Only Flux2 Klein 4B (`klein-4b`) and 9B (`klein-9b`) checkpoints are supported via the `klein` preset; Flux2 Dev 32B is unsupported and has no registry entry — do not expect 32B checkpoints to be detected or configured.

---

## 📐 System Architecture

```
forge/
├── __init__.py              Plugin registration with Krita
├── forge.py                 Main docker widget & tab navigation
├── qt_compat.py             PyQt5 / PyQt6 abstraction layer
├── settings_controller.py   Settings load/save/migration controller
├── default_settings.json    Default configuration schema
├── adapters/
│   ├── sd_api.py            Forge API client (state machine, retry logic)
│   └── krita_adapter.py     Krita canvas and layer manipulation
├── domain/
│   ├── model_registry.py    9-family detection & configuration registry
│   ├── payload_builder.py   Payload translator for API requests
│   ├── generation_plan.py   Resize & dimension bounding math
│   ├── history_manager.py   History persistence & cleanup
│   └── progress_state.py    Progress polling parser
├── pages/
│   ├── txt2img.py, img2img.py, inpaint.py, settings.py, upscale.py, rembg.py, etc.
└── widgets/
    ├── generate.py, models.py, prompts.py, cfg.py, history.py, mask.py, etc.
```

---

## 📜 License

This project is licensed under the **GNU General Public License v3.0**. See the [LICENSE](LICENSE) file for details.
