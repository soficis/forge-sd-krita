# Forge SD-Krita Plugin

A Krita plugin for generating, transforming, and editing images with the [Forge Neo](https://github.com/Haoming02/sd-webui-forge-classic/tree/neo) backend.

> [!CAUTION]
> **DISCLAIMER: EXPERIMENTAL & WORK IN PROGRESS**
> This plugin is in active development and **most likely is NOT in a fully functional or stable state for end-user production use**. Expect rough edges, missing error handling, unhandled edge cases, breaking changes, and potential UI crashes.
> 
> Please review the [Known Issues & Limitations](#%EF%B8%8F-known-issues--limitations) and the [Testing & Verification Guide](#-testing--verification-guide) before attempting to use or test the plugin.

---

## 🛠️ Requirements & Prerequisites

- **Krita**: Krita 5.2+ or Krita 6.0+ (PyQt5 / PyQt6 auto-detected)
- **Python**: Python 3.x (bundled with Krita)
- **Backend Server**: A running instance of **[Forge Neo](https://github.com/Haoming02/sd-webui-forge-classic/tree/neo)** with `--api` access enabled

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

## 🧪 Testing & Verification Guide

The project includes an automated test suite for domain logic alongside manual testing procedures.

### 1. Automated Unit Tests

Execute the unit test suite across all 7 domain modules (330 tests total):

```bash
# Run all 330 unit tests
python -m pytest tests/ -v
```

#### Test Suite Breakdown

| Module | Tests | Focus Area |
|---|---|---|
| `test_model_registry.py` | 149 | 9-model family regex detection, forge presets, CFG profiles, and size defaults |
| `test_payload_builder.py` | 36 | Translation of plugin parameters to API payload formats and model overrides |
| `test_sd_api.py` | 26 | Backend connection state machine, retry logic, and payload dispatching |
| `test_settings_controller.py` | 35 | Settings migration, loading defaults, fallback defaults, and debounced saving |
| `test_history_manager.py` | 18 | Generation history storage, search filtering, pagination, and TTL cleanup |
| `test_generation_plan.py` | 40 | Aspect ratio math, canvas bounds scaling, and pixel alignment |
| `test_progress_state.py` | 26 | Parsing Forge progress polling API responses |

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
> **There are far too many known issues, unhandled UI edge cases, and missing error guards to count.**
> 
> While core domain logic and payload construction have 330 unit tests, over **~5,600 lines of UI widget, page, and docker code have zero unit test coverage**. Users and developers should expect unhandled exceptions, silent failures, thread race conditions, broken UI states, missing error prompts, and incomplete features.
> 
> Major categories of known issues include:
> - **Untested UI Infrastructure**: Over 5,600 lines of PyQt widget and page implementation code lack automated test coverage. Expect unexpected widget behavior and Qt runtime exceptions.
> - **Partial Feature Restoration**: History entry reuse only partially restores settings (restoring models, VAEs, and samplers from history entries is partially broken).
> - **Extension & API Error Handling**: Extensions (such as ControlNet and RemBG) lack defensive error parsing and can crash the plugin Docker if the backend returns unexpected error payloads.
> - **Thread Safety & Race Conditions**: Asynchronous thread execution in `KritaAdapter` overwrites active thread handles, causing potential race conditions during concurrent generations or quick task cancellations.
> - **Silent Exception Swallowing**: Background update checks, layer polling, and progress timers catch generic `Exception`s silently without reporting issues to the user log.
> - **Placeholder & Skeleton Pages**: Features like the Segmentation Map page exist only as skeleton UI placeholders without backing backend integration.

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
