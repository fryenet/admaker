# AdMaker

AdMaker is a Python command-line tool for creating short AI-generated video
commercials. It coordinates text generation, image generation, speech
generation, video generation, and FFmpeg-based media processing in one
workflow.

The main script is:

```text
admaker.py
```

## Features

- Generates structured three-scene commercial plans
- Creates anchor images for each scene
- Generates narration audio
- Supports Wan-based image-to-video generation
- Supports Grok-based video generation
- Preserves visual continuity between scenes
- Combines scene videos into a final commercial
- Uses FFmpeg and FFprobe for media processing
- Supports configurable public asset hosting

## Services used

AdMaker integrates with:

- OpenAI
- ElevenLabs
- Black Forest Labs
- PiAPI / Wan
- xAI / Grok

## Ubuntu 24.04 setup

Install Python, Git, FFmpeg, and virtual-environment support:

```bash
sudo apt update
sudo apt install -y python3 python3-venv git ffmpeg
```

Enter the project directory:

```bash
cd admaker
```

Create a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Install Python dependencies:

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## Configuration

AdMaker reads service credentials and server-specific settings from a local
`.env` file.

Create it from the included example:

```bash
cp .env.example .env
nano .env
```

Add your service credentials:

```text
ELEVENLABS_API_KEY=...
BFL_API_KEY=...
OPENAI_API_KEY=...
PIAPI_API_KEY=...
XAI_API_KEY=...
```

The `.env` file is excluded by `.gitignore`.

## Public asset hosting

Some video-generation services need to access generated images and audio from
a public URL.

Configure these values in `.env`:

```text
PUBLIC_DATA_DIR=/var/www/html/youradsmith/data
PUBLIC_BASE_URL=https://youradsmith.com/data
```

`PUBLIC_DATA_DIR` is the local directory where generated assets are written.

`PUBLIC_BASE_URL` is the public URL that serves files from that directory.

## Run AdMaker

Activate the virtual environment:

```bash
source .venv/bin/activate
```

Run the program:

```bash
python admaker.py
```

The program will ask:

```text
1 = Talking character
2 = Grok video ad
```

It will then ask what the advertisement is for, what it is about, and any
creative direction you want to provide.

## Output

Generated working files are stored in:

```text
ad_output/
```

The final commercial is also written to that output directory.

Generated media files and working files are excluded from Git by default.

## Git setup

Before the first commit, verify the repository contents:

```bash
git status --ignored
```

Your local `.env` file should appear under ignored files.

Initialize the repository:

```bash
git init -b main
git add .
git status
git commit -m "Initial release"
```

## Create a private GitHub repository

```bash
gh repo create admaker --private --source=. --remote=origin --push
```

## Create a public GitHub repository

```bash
gh repo create admaker --public --source=. --remote=origin --push
```

## Future updates

After making changes:

```bash
git add .
git commit -m "Describe the change"
git push
```

## Project files

```text
admaker.py
.env.example
.gitignore
requirements.txt
README.md
LICENSE
```

## License

An MIT license template is included. Replace `YOUR NAME` in `LICENSE` before
publishing if you want to use the MIT license.

If you prefer to keep the project proprietary, remove the `LICENSE` file or
replace it with the license terms you want to use.
