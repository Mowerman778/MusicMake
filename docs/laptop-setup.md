# Running MusicMake on your laptop (GPU) with VS Code

Your laptop runs two programs side by side:

```
┌───────────────────────────┐        ┌──────────────────────────────┐
│ ACE-Step 1.5  (port 8001) │ ◄────► │ MusicMake  (port 8765)       │ ◄── your browser
│ the GPU song engine       │        │ library, player, Studio      │
└───────────────────────────┘        └──────────────┬───────────────┘
                                                    │ runs when needed
                                     soundcraft-cli (Studio) · Demucs (stems) · ffmpeg (MP3)
```

Without ACE-Step running, MusicMake still works. It uses the CPU-only Sketch engine instead.

## 1. Before you start

| You need | Windows | macOS | Linux |
|---|---|---|---|
| Git | `winget install Git.Git` | `xcode-select --install` | `sudo apt install git` |
| Python 3.11 or 3.12 | [python.org](https://www.python.org/downloads/) (tick *Add to PATH*) | `brew install python@3.12` | `sudo apt install python3.12-venv` |
| NVIDIA driver (NVIDIA GPUs) | [nvidia.com/drivers](https://www.nvidia.com/drivers) | — (Apple Silicon uses MLX) | your distro's driver |
| ffmpeg (MP3, uploads) | `winget install Gyan.FFmpeg` | `brew install ffmpeg` | `sudo apt install ffmpeg` |
| Rust (only for Studio) | [rustup.rs](https://rustup.rs) (it installs the C++ build tools it needs) | [rustup.rs](https://rustup.rs) | [rustup.rs](https://rustup.rs) |
| VS Code + Claude extension | [code.visualstudio.com](https://code.visualstudio.com), then install **Claude Code** from the Extensions view | same | same |

Check the GPU with `nvidia-smi` in a terminal. It should list your card.

## 2. Get the code

In VS Code: **Ctrl+Shift+P → Git: Clone**, then paste `https://github.com/Mowerman778/MusicMake`.
Pick a parent folder such as `Documents\Music`, then **Open** it. Or in a terminal:

```sh
git clone https://github.com/Mowerman778/MusicMake
cd MusicMake
code .
```

VS Code will offer the recommended extensions (Claude Code, Python): accept.

## 3. Set everything up (one command)

Open the terminal in VS Code (**Ctrl+`**) and run:

```powershell
# Windows
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
```

```sh
# macOS / Linux
./scripts/setup.sh
```

The script:

1. creates `.venv` and installs MusicMake's Python packages;
2. installs PyTorch with CUDA and Demucs (stems);
3. clones **ACE-Step 1.5** next to MusicMake (`../ACE-Step-1.5`) and installs it with `uv`;
4. builds SoundCraft's `soundcraft-cli` for Studio, if Rust is installed (about 10 minutes, once);
5. runs `python -m musicmake doctor`, which ends with a ✔/○ list of what's ready.

Skip parts with `-NoStudio`, `-NoAceStep` or `-NoStems` (`--no-studio` and so on on macOS/Linux).
If your GPU needs a different PyTorch build, set `TORCH_INDEX` first (see
[pytorch.org](https://pytorch.org/get-started/locally/)).

Then pick the interpreter: **Ctrl+Shift+P → Python: Select Interpreter → `.venv`**.

## 4. Run it

**Terminal → Run Task… → Start everything.** This starts ACE-Step and MusicMake, each in its own
terminal panel. Then open **http://127.0.0.1:8765**.

- The first ACE-Step start downloads its models (several GB) and takes a few minutes. The panel
  shows when it's listening on port 8001.
- In MusicMake, the header reads **ACE-Step connected** when it's found. Leave the engine on
  **Auto**.
- Choose the ACE-Step model for your card in `../ACE-Step-1.5/.env` (copy `.env.example`):

| GPU memory | Set in `.env` |
|---|---|
| 6 GB or less | `ACESTEP_CONFIG_PATH=acestep-v15-turbo` (the language model is off by default) |
| 6–12 GB | `ACESTEP_CONFIG_PATH=acestep-v15-turbo` and `ACESTEP_LM_MODEL_PATH=acestep-5Hz-lm-0.6B` |
| 12–16 GB | `ACESTEP_CONFIG_PATH=acestep-v15-turbo` and `ACESTEP_LM_MODEL_PATH=acestep-5Hz-lm-1.7B` |

Other tasks: **MusicMake doctor**, **Run tests**. To debug, open **Run and Debug** (Ctrl+Shift+D)
and pick **MusicMake (auto engine)**. Breakpoints in `musicmake/*.py` work.

## 5. Keep up with progress

Changes made in a cloud session arrive on GitHub. To get them, use **Source Control → … → Pull**
(or `git pull`), then restart the **Start MusicMake** task. Your songs live in `data/`, which git
ignores, so pulling never touches them.

## 6. Working with Claude in VS Code

Open the Claude panel and ask in plain words, for example:

- "Run the doctor and fix anything that's missing."
- "Make a 2-minute lofi song through the API and tell me how long ACE-Step took."
- "Add a Studio button that splits a region into its own track."

Claude reads [`CLAUDE.md`](../CLAUDE.md) first, which explains the layout, how to run and test
it, and this project's rules.

## Troubleshooting

| Symptom | Fix |
|---|---|
| Header says "Sketch mode" although ACE-Step runs | Wait until its panel shows the API listening; check http://127.0.0.1:8001/health |
| ACE-Step runs out of GPU memory | Use the smaller models from the table above; close other GPU apps |
| Stems are slow | `python -m musicmake doctor` shows whether Demucs uses CUDA; reinstall torch with the CUDA index if not |
| Studio says SoundCraft is missing | Install Rust, then `cargo install --locked --git https://github.com/storytold/soundcraft soundcraft-cli`; restart MusicMake |
| `setup.ps1` is blocked | Run it with `powershell -ExecutionPolicy Bypass -File scripts\setup.ps1` |
| MP3 download fails | Install ffmpeg and restart VS Code so it's on PATH |
