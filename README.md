# Forge SD-Krita Plugin

A modern, production-grade Krita docker plugin for generating, transforming, and editing images with the [Forge Neo](https://github.com/Haoming02/sd-webui-forge-classic/tree/neo) backend.

> [!NOTE]
> **Status: Active Development & Stable Core Generation**
> Core generation workflows (**Txt2Img**, **Img2Img**, and **Inpaint**) are functional, resilient, and backed by a comprehensive **1290-test automated suite**. Advanced extension hooks (ControlNet multi-unit and ADetailer face/hand repair) have verified payload schemas and API bindings, but should be tested individually against your specific Forge Neo extension configuration.

---

## 📦 What's New in 1.1.0

A major UX, stability, and feature-completion release — test suite expanded from 330 to **1290 tests, all passing**.

- **Modern Top Rail Layout**: Navigation tabs (`Txt2Img`, `Img2Img`, `Inpaint`, `Upscale`, `Rembg`, `Seg-Map`, `Settings`) are positioned along a clean, space-efficient horizontal top rail across the docker header.
- **Visual Hierarchy (Prompt First)**: Prompt and Negative Prompt inputs are positioned prominently at the top of each generation page, putting creative iteration first before secondary settings.
- **Scroll Protection (Mousewheel Filtering)**: Spinboxes, sliders, and dropdown menus ignore accidental mousewheel scroll changes (`NoWheelComboBox`, `NoWheelSlider`, `NoWheelSpinBox`), preventing accidental parameter edits while navigating the docker.
- **Robust Inpainting & Quick Mask**:
  - One-click **Quick Mask** action bootstraps the `"Forge Mask"` layer, switches to the brush tool, and enters paint mode.
  - Zero-dimension layer bounds (e.g. freshly created or cleared mask layers) gracefully fall back to canvas dimensions, eliminating empty payload captures and backend `404: Init image not found` errors.
  - Mask layer visibility is cleanly preserved and restored after generation, even upon error or user cancellation.
  - Soft Inpainting controls are merged directly into Inpaint mask settings.
  - Client-side validation prevents generation attempts when no active canvas image is available.
- **Streamlined Model & Generation Settings**:
  - **Scheduler Disambiguation**: The scheduler dropdown includes an explicit `"Use Preset Default (Automatic)"` option to clearly differentiate backend family defaults from generic Automatic.
  - **Refiner Controls**: Refiner checkpoint and step controls are tucked into an expandable section, visible only when enabled.
  - **VAE Sentinel Filtering**: The internal `"None"` sentinel is stripped from payloads and defaults reconcile cleanly with the backend.
  - **Styles Collapsed by Default**: Styles drawer is collapsed by default to minimize visual noise.
  - **Denoise Protection**: Denoise strength is automatically capped for distilled/turbo models to prevent blown-out outputs.
- **Lifecycle & Memory Management**:
  - Page destruction cascades cleanly to `generate_widget.cleanup()`.
  - Defensive handling for deleted Qt C++ objects (`QLabel`, `QWidget`) prevents runtime crashes during rapid page switching or background return.
  - Timer teardown stops background polling immediately when tabs are closed.
- **Simplify UI Section**: The Simplify UI tool is integrated directly as a collapsible section inside the **Settings** tab.
- **Interrogate Deprecation**: Removed the defunct Interrogate button since Forge Neo does not expose the legacy A1111 interrogate endpoint.
- **Artist Tools & Reliability**:
  - Full **History Reuse** copies all generation parameters (model, sampler, scheduler, seed, CFG, prompt, dimensions).
  - **Prompt Presets**: Save, load, rename, and delete prompt templates (up to 50).
  - **Smart Size**: Dimension suggestion assistant for resolution alignment on img2img and inpaint.
  - **Tiled High-Res**: Collapsible high-resolution tiled generation controls on Txt2Img.
  - **Live Preview**: Canvas preview layer (512px capped) during generation when enabled.
  - **Client-Side Validation**: Prompt emptiness and invalid numeric inputs are rejected before sending requests.

---

## 🛠️ Requirements & Prerequisites

- **Krita**: Krita 5.2+ or Krita 6.0+ (PyQt5 and PyQt6 auto-detected)
- **Python**: Bundled with Krita (Python 3.10 / 3.11 / 3.12 / 3.13 / 3.14)
- **Backend**: [Forge Neo](https://github.com/Haoming02/sd-webui-forge-classic/tree/neo) (branch `neo` required; classic A1111 legacy architecture is not supported) started with `--api` (`set COMMANDLINE_ARGS=--api`), default address `http://127.0.0.1:7860`
- **Dependencies**: None beyond Krita's built-in Python environment (PyQt5/PyQt6 + standard library)

### Backend Compatibility Note

This plugin is specifically engineered for **Forge Neo** (`neo` branch). Key Forge Neo capabilities utilized:
- Native model families: Flux.1, Flux2 Klein, Anima, Z-Image, Krea2, Qwen-Image, and Wan
- Automatic preset profiles: `sd`, `xl`, `flux`, `klein`, `qwen`, `lumina`, `zit`, `wan`, `anima`, `ernie`, `pid`, `krea`
- Dynamic text encoder and VAE additional module orchestration

---

## 📊 Supported Model Families & Presets

The plugin detects **9 model families** automatically from checkpoint filenames and applies presets, text encoders, VAEs, samplers, schedulers, CFG scales, and UI adaptations:

### 1. Model Matrix & Setup Requirements

| Model Family | Detection Keywords | Forge Preset | Text Encoder | VAE | Sampler / Scheduler | CFG Defaults |
|---|---|---|---|---|---|---|
| **SD 1.5** | (fallback default) | `sd` | — | — | Euler a / Automatic | 7.0 (range 0–30) |
| **SDXL** | `sdxl` | `xl` | — | — | Euler a / Automatic | 5.0 (range 0–30) |
| **Flux.1** | `flux`, `nunchaku` | `flux` | `clip_l` + `t5xxl_fp16` | `ae.safetensors` | Euler / Simple | 1.0 (Distilled CFG 3.5) |
| **Flux2 Klein** | `flux2`, `klein-4b`, `klein-9b` | `klein` | `qwen_3_4b` / `qwen_3_8b` | `flux2-vae.safetensors` | Euler / Simple | 1.0 (fixed 4 steps) |
| **Anima** | `anima`, `wai-anima` | `anima` | `qwen_3_06b_base` | `qwen_image_vae.safetensors` | ER SDE / Beta | 4.0 (shift 3.0, 32 steps) |
| **Z-Image Turbo** | `z-image`, `z_image` | `zit` | `qwen_3_4b` | `ae.safetensors` | Euler / Beta | 1.0 (fixed, 8–9 steps) |
| **Krea2** | `krea2`, `krea-2` | `krea` | `qwen3vl_4b_fp8_scaled` | `qwen_image_vae.safetensors` | Euler / Simple | RAW: 4.5 / Turbo: 0.0 (fixed) |
| **Qwen-Image** | `qwen-image` | `qwen` | `qwen_2.5_vl_7b_fp8_scaled` | `qwen_image_vae.safetensors` | Euler / Simple | 4.0 (range 0–10, 30 steps) |
| **Wan** | `wan` | `wan` | — | — | Euler a / Automatic | 7.0 (range 0–30) |

*Note: In Forge Neo, place checkpoints in `models/Stable-diffusion/`, VAEs in `models/VAE/`, and text encoders in `models/text_encoder/`.*

### 2. Architecture-Aware Size Defaults

| Architecture | Default Min Size | Default Max Size | Hard Floor |
|---|---|---|---|
| **SD 1.5** | 512 | 2048 | 256 |
| **SDXL / Flux / Flux2 / Anima / Z-Image / Krea2 / Qwen** | 512 | 2048 | 512 |
| **Wan** | 256 | 1024 | 256 |

### 3. Dynamic UI Adaptation

- **Negative Prompt**: Automatically hidden for Flux, Flux2, Z-Image, and Krea2 Turbo. Displayed for SD, SDXL, Anima, Krea2 RAW, Qwen, and Wan.
- **Styles Section**: Collapsed by default; hidden entirely for Flux and Flux2.
- **CFG Scale Label**: Dynamically displays as "Distilled CFG" for Flux, "Guidance Scale" for Krea2/Qwen, or "CFG fixed" for Turbo models.
- **Turbo LoRA Auto-Adjustment**: Prompt tags like `<lora:*turbo*:*>`, `<lora:*hyper-sd*:*>`, `<lora:*lcm*:*>`, or `<lora:*alimama*:*>` automatically configure optimal steps and CFG.

---

## ✨ Features & Generation Modes

### Txt2Img (Text-to-Image)
- Prompt and Negative Prompt positioned at the top of the interface.
- Automatic model detection with tuned sampler, scheduler, steps, and CFG presets.
- Prompt Presets management (save, load, rename, delete).
- Collapsible Tiled high-resolution generation controls (tile size 512/768/1024, overlap 0–128 px).
- Batch count, batch size, and seed controls (fixed or random `-1`).

### Img2Img (Image-to-Image)
- Transforms active canvas selection or layer.
- **Smart Size**: Suggests step-aligned dimensions matching canvas aspect ratio.
- **Denoise Strength**: Slider with distilled model safety caps (`0.1–0.3` subtle adjustments, `0.3–0.5` moderate restyling, `0.5–0.7` major transformations, `0.7–1.0` full reinterpretation).

### Inpaint (Masked Inpainting)
- Seamless region filling: white paints inpaint area, transparent/black preserves canvas.
- **Quick Mask**: One-click mask layer creation, brush tool activation, and paint mode bootstrap.
- Zero-dimension bounds protection with automatic canvas bounds fallback.
- Invert mask, mask blur adjustment, and integrated Soft Inpainting.
- Layer visibility preservation (mask layer temporarily hidden for clean capture, then restored).

### Upscale & Post-Processing
- High-quality image scaling via Forge Neo's `extra-single-image` endpoint.
- Upscale by factor (e.g. 2x, 4x) or to target dimensions.
- Optional automatic canvas resizing to match upscaled output.

### Remove Background (RemBG)
- Integrated background extraction supporting u2net, isnet, and related models.
- Configurable alpha matting (foreground/background thresholds, erode size).
- Outputs as a transparent layer or isolated mask.

### Extensions (ControlNet & ADetailer)
- Multi-unit ControlNet configuration with model, preprocessor, weight, guidance bounds, and pixel-perfect options.
- Dynamic IP-Adapter reference image slot gated on backend capability.
- API-driven ADetailer face and hand detail restoration.

### Job Queue & History
- Non-blocking asynchronous job generation queue.
- Real-time queue status bar with error reporting and job cancellation.
- Generation history with thumbnails, metadata inspection, search filtering, and one-click full parameter **Reuse**.

---

## 🚀 Installation & Setup

### 1. Enable API on Forge Neo

In your Forge Neo root directory, ensure `webui-user.bat` (Windows) or `webui-user.sh` (Linux) includes `--api`:

```bat
set COMMANDLINE_ARGS=--api
```

Launch Forge Neo and verify it is accessible at `http://127.0.0.1:7860`.

### 2. Install Plugin into Krita

#### Standard Copy (Recommended)

1. Open Krita → **Settings > Manage Resources** → click **Open Resource Folder** (bottom right).
2. Navigate into the `pykrita` directory.
3. Copy both the `forge` folder and `forge.desktop` file into `pykrita`:
   ```
   <Krita-Resource-Folder>/pykrita/
   ├── forge/
   └── forge.desktop
   ```
4. Restart Krita.

#### Symlink / Development Setup

```bat
:: Windows (Command Prompt as Administrator)
mklink /j "%APPDATA%\krita\pykrita\forge" "V:\path\to\forge-sd-krita\forge"
mklink "%APPDATA%\krita\pykrita\forge.desktop" "V:\path\to\forge-sd-krita\forge.desktop"
```

```sh
# Linux
ln -s /path/to/forge-sd-krita/forge ~/.local/share/krita/pykrita/forge
ln -s /path/to/forge-sd-krita/forge.desktop ~/.local/share/krita/pykrita/forge.desktop
```

### 3. Activate Plugin in Krita

1. Open Krita → **Settings > Configure Krita... > Python Plugin Manager**.
2. Enable the checkbox for **forge SD Plugin for Krita**.
3. Restart Krita.
4. Enable the docker: **Settings > Dockers > Forge SD**.

---

## 🧭 User Guide & Workflow

1. **Connect**:
   - Open the **Settings** tab.
   - Enter your Forge Neo server URL (default: `http://127.0.0.1:7860`).
   - Click **Connect**. The status indicator turns green when connected. If offline, the status bar displays the connection error and generation buttons remain disabled.
2. **Text to Image**:
   - Switch to the **Txt2Img** tab.
   - Type your prompt into the top text box.
   - Select your checkpoint from the model dropdown (samplers and presets configure automatically).
   - Click **Generate**. Generated images are automatically inserted onto a new layer.
3. **Inpainting with Quick Mask**:
   - Open or create an artwork in Krita.
   - Switch to the **Inpaint** tab.
   - Click **Quick Mask** — this creates a `"Forge Mask"` layer and equips your brush tool.
   - Paint white over the area you want to replace.
   - Enter your prompt and click **Generate**.
4. **History & Reuse**:
   - Scroll to the **History** section at the bottom of any generation tab.
   - Browse previous generations or use the search bar.
   - Click **Reuse** to reload prompt, model, seed, CFG, sampler, and dimensions into the active tab.

---

## 🧪 Testing & Verification Guide

The codebase maintains a comprehensive automated unit test suite.

### 1. Running the Automated Suite

```bash
# Run all 1290 unit tests
python -m pytest tests/ -v
```

### 2. Test Suite Breakdown (1290 Tests across 41 Modules)

| Module | Tests | Focus Area |
|---|---|---|
| `test_model_registry.py` | 141 | 9-model family regex detection, forge presets, CFG profiles, and size defaults |
| `test_smart_resolution.py` | 130 | Step-aligned resolution suggestion algorithms |
| `test_ui_surface.py` | 92 | Widget and page construction integrity |
| `test_controlnet_dict_guards.py` | 83 | Non-dict and error-payload safety guards |
| `test_qt_compat_imports.py` | 63 | Explicit `qt_compat` symbol isolation across PyQt5/6 |
| `test_settings_schema_numeric_types.py` | 55 | Settings schema numeric conversions and type consistency |
| `test_controlnet_ip_adapter.py` | 48 | IP-Adapter capability gating and payload wiring |
| `test_generation_validation.py` | 46 | Client-side prompt, batch, step, and seed validation |
| `test_generation_plan.py` | 40 | Aspect ratio bounding and pixel alignment math |
| `test_payload_builder.py` | 37 | API payload formatting, model overrides, and image encoding |
| `test_settings_controller.py` | 35 | Settings migration, loading defaults, and debounced persistence |
| `test_flux_ui.py` | 35 | Flux dynamic sizing and control visibility rules |
| `test_scheduler_dropdown.py` | 34 | Scheduler dropdown options and preset default handling |
| `test_ux_polish.py` | 32 | Empty states, disabled tooltips, and loading indicator |
| `test_prompt_presets.py` | 29 | Prompt preset CRUD operations |
| `test_connection_errors.py` | 28 | Backend connection error detection and banner display |
| `test_seg_map.py` | 28 | Segmentation map color list rendering and search |
| `test_sd_api.py` | 26 | Backend API state machine, retry logic, and request dispatching |
| `test_progress_state.py` | 26 | Forge Neo progress polling parser |
| `test_interrogate_removed.py` | 24 | Verification of clean interrogate endpoint deprecation |
| `test_no_wheel_combo.py` | 21 | Mousewheel event filtering across dropdowns and spinboxes |
| `test_live_preview.py` | 20 | Live canvas preview layer management and 512px cap |
| `test_simplify_merged_into_settings.py` | 18 | Integrated Simplify UI section within Settings |
| `test_history_manager.py` | 18 | Generation history storage, search filtering, and TTL cleanup |
| `test_scheduler_default.py` | 17 | Model family scheduler preset defaults |
| `test_tiled_txt2img.py` | 17 | Tiled generation control wiring and options |
| `test_timer_cleanup.py` | 15 | Timer teardown on page and widget cleanup |
| `test_adetailer_models.py` | 13 | API-driven ADetailer model list retrieval |
| `test_denoise_turbo_guard.py` | 13 | Turbo model denoise strength capping |
| `test_tabs_top_rail.py` | 13 | Horizontal top-rail tab layout and navigation |
| `test_vae_sentinel_fix.py` | 13 | VAE None sentinel handling and backend synchronization |
| `test_quick_mask.py` | 12 | Quick Mask bootstrap, 0x0 bounds fallback, and paint mode |
| `test_ui_improvements.py` | 12 | Queue status lifecycle, cleanup cascading, and inpaint image validation |
| `test_cfg_scale_float.py` | 11 | Floating-point CFG scale serialization |
| `test_mask_layer_pixel_ops.py` | 9 | Mask layer clear, invert, and opacity operations |
| `test_mask_visibility.py` | 9 | Mask layer snapshot and restoration lifecycle |
| `test_task18_widget_todos.py` | 8 | Widget cleanup and error handling paths |
| `test_hr_additional_modules.py` | 6 | High-res fix text encoder and VAE module payload integrity |
| `test_krita_adapter_thread.py` | 5 | Concurrent thread guards in `run_as_thread()` |
| `test_collapsible_default.py` | 4 | Collapsible section default visibility and expansion |
| `test_models_history_reuse.py` | 4 | Complete history entry restoration |
| **Total** | **1290** | **All passing** |

### 3. Syntax Verification

```bash
python -m py_compile forge/*.py forge/*/*.py
```

---

## ⚠️ Known Behaviors & Considerations

- **Extension Live Testing**: ControlNet and ADetailer widgets include verified API request builders and error handlers, but full live validation depends on the installed Forge extensions and models on your local Forge Neo backend.
- **Single-Model Architecture**: Forge Neo loads one model checkpoint into VRAM at a time. Switching models triggers an unloading/loading cycle on the server.
- **Flux2 Checkpoint Scope**: Flux2 Klein 4B (`klein-4b`) and 9B (`klein-9b`) checkpoints are supported via the `klein` preset. Flux2 Dev 32B is not supported.

---

## 📐 Architecture Overview

```
forge/
├── __init__.py              Plugin entry point registered with Krita
├── forge.py                 Main docker widget, top-rail tabs & layout
├── qt_compat.py             PyQt5 / PyQt6 abstraction layer
├── settings_controller.py   Settings controller with debounced disk persistence
├── default_settings.json    Default configuration schema
├── adapters/
│   ├── sd_api.py            Forge API client, connection state machine & retries
│   └── krita_adapter.py     Krita document, layer, projection & mask operations
├── domain/
│   ├── model_registry.py    9-family detection, presets, CFG & size defaults
│   ├── payload_builder.py   Translates UI parameters to Forge Neo API payloads
│   ├── generation_plan.py   Dimension bounding, aspect ratio & resize math
│   ├── generation_validation.py Client-side input validation
│   ├── history_manager.py   Local generation history indexing & TTL cleanup
│   └── progress_state.py    Progress polling parser
├── pages/
│   ├── txt2img.py           Text-to-Image page
│   ├── img2img.py           Image-to-Image page
│   ├── inpaint.py           Inpaint page with Quick Mask & Soft Inpainting
│   ├── upscale.py           Single-image upscaler page
│   ├── rembg.py             Background removal page
│   ├── seg_map.py           Segmentation map color reference page
│   └── settings.py          Server connection, live preview & Simplify UI
├── extension_widgets/
│   ├── controlnet.py        Multi-unit ControlNet configuration
│   └── adetailer.py         ADetailer face & hand detailer controls
└── widgets/
    ├── generate.py          Job queue, status bar & generate execution
    ├── models.py            Model, VAE, text encoder & scheduler controls
    ├── prompts.py           Prompt & negative prompt text areas
    ├── prompt_presets.py    Prompt preset manager
    ├── mask.py              Quick Mask bootstrap, opacity & mask controls
    ├── history.py           Visual generation history & parameter reuse
    ├── no_wheel.py          Scroll-safe combo box, slider & spinbox widgets
    └── collapsible.py       Collapsible container panels
```

---

## 📜 License

This project is licensed under the **GNU General Public License v3.0**. See the [LICENSE](LICENSE) file for details.
