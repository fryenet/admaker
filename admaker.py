#!/usr/bin/env python3

"""
AI commercial generator using ElevenLabs, Black Forest Labs, OpenAI,
PiAPI/Wan, xAI/Grok, and FFmpeg.

Runtime settings and service credentials are loaded from a local .env file.
"""

from elevenlabs.client import ElevenLabs
import requests
import time
from openai import OpenAI
import os
import json
import math
import subprocess
import uuid
import shutil
import random
from pathlib import Path

from dotenv import load_dotenv




load_dotenv(Path(__file__).with_name(".env"))


def required_env(name):
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(
            f"Missing required setting: {name}. "
            "Copy .env.example to .env and add your credential."
        )
    return value


elevenlabs_api_key = required_env("ELEVENLABS_API_KEY")
black_forestlabs_key = required_env("BFL_API_KEY")
chatgpt_key = required_env("OPENAI_API_KEY")
piapi_key = required_env("PIAPI_API_KEY")
xai_api_key = required_env("XAI_API_KEY")

voices = [
    "AXdMgz6evoL7OPd7eU12",
    "eXpIbVcVbLo8ZJQDlDnl",
    "XwswTF89pZKbWpVX4A7R",
    "wWWn96OtTHu1sn8SRGEr"
]

public_data_dir = os.getenv(
    "PUBLIC_DATA_DIR",
    "/var/www/html/youradsmith/data"
)
public_base_url = os.getenv(
    "PUBLIC_BASE_URL",
    "https://youradsmith.com/data"
)

chatgpt_system_prompt = """
You are an expert commercial director and AI prompt engineer.

You create short commercial plans as STRICT JSON only.
Do not use markdown.
Do not explain anything outside the JSON.

CRITICAL RULES:
- Make exactly 3 scenes
- Each scene should have ONE clear subject and ONE simple action
- Prioritize stable, realistic motion over creativity
- Avoid crowds, chaos, fast movement, complicated interactions, and exaggerated acting
- Keep a premium ad feel
- If there is a recurring character, repeat the SAME defining traits across all scenes
- If there is a visible speaking character, set needs_lipsync to true
- Use speaker_type values: "human", "animal", or "none"

IMAGE PROMPT RULES:
- Describe the exact first frame of the shot
- Give strong visual details
- Keep it cinematic and realistic
- Repeat defining character details if recurring

VIDEO PROMPT RULES:
- Describe only simple visible motion
- One camera move max: static, slow push-in, slow pan, or slow orbit
- No complex choreography
- No story summary

NARRATION RULES:
- Short, punchy, persuasive
- One clear marketing point per scene

OUTPUT FORMAT:
{
  "title": "string",
  "style": "string",
  "target_audience": "string",
  "scenes": [
    {
      "scene_number": 1,
      "image_prompt": "string",
      "video_prompt": "string",
      "narration": "string",
      "on_screen_text": "string",
      "needs_lipsync": false,
      "speaker_type": "none"
    }
  ]
}
"""


def run_cmd(cmd):
    print("RUN:", " ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True)

    print("RETURN CODE:", result.returncode)

    if result.stdout.strip():
        print("STDOUT:")
        print(result.stdout)

    if result.stderr.strip():
        print("STDERR:")
        print(result.stderr)

    if result.returncode != 0:
        raise RuntimeError("Command failed.")

    return result


def atomic_write_bytes(final_path, content):
    os.makedirs(os.path.dirname(final_path), exist_ok=True)
    temp_path = final_path + ".tmp"
    with open(temp_path, "wb") as f:
        f.write(content)
    os.replace(temp_path, final_path)


def ensure_public_data_dir():
    os.makedirs(public_data_dir, exist_ok=True)


def get_public_url(filename):
    return f"{public_base_url.rstrip('/')}/{filename}"


def save_path_in_public_dir(filename):
    return os.path.join(public_data_dir, filename)


def make_run_id():
    return f"{int(time.time())}_{uuid.uuid4().hex[:8]}"


def make_asset_token():
    return uuid.uuid4().hex[:6]


def make_public_filename(run_id, kind, scene_number, extension):
    asset_token = make_asset_token()
    return f"{run_id}_{kind}_scene_{scene_number}_{asset_token}.{extension}"


def wait_for_local_file(path, timeout=10, sleep_seconds=0.5, min_bytes=1):
    start = time.time()

    while time.time() - start < timeout:
        if os.path.exists(path):
            try:
                if os.path.getsize(path) >= min_bytes:
                    return True
            except OSError:
                pass
        time.sleep(sleep_seconds)

    return False


def wait_for_public_file(url, timeout=20, sleep_seconds=2, method="GET", min_bytes=1):
    start = time.time()
    attempt = 0

    while time.time() - start < timeout:
        attempt += 1
        cache_busted_url = f"{url}?v={int(time.time())}_{attempt}"

        try:
            if method.upper() == "HEAD":
                r = requests.head(cache_busted_url, timeout=10, allow_redirects=True)
                if r.status_code == 200:
                    content_length = int(r.headers.get("Content-Length", "0") or "0")
                    if content_length >= min_bytes:
                        return True
            else:
                r = requests.get(cache_busted_url, timeout=10, allow_redirects=True)
                if r.status_code == 200 and len(r.content) >= min_bytes:
                    return True
        except Exception:
            pass

        time.sleep(sleep_seconds)

    return False


def get_media_duration(file_path):
    cmd = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        file_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        print(result.stdout)
        print(result.stderr)
        raise RuntimeError(f"Could not get duration for {file_path}")

    return float(result.stdout.strip())


def get_audio_duration(file_path):
    return get_media_duration(file_path)


def text_to_speech(text, output_file="output.mp3", voice_id=None):
    client = ElevenLabs(api_key=elevenlabs_api_key)

    if not voice_id:
        raise ValueError("voice_id must be provided")

    audio = client.text_to_speech.convert(
        text=text,
        voice_id=voice_id,
        model_id="eleven_multilingual_v2"
    )

    os.makedirs(os.path.dirname(output_file), exist_ok=True)

    with open(output_file, "wb") as f:
        for chunk in audio:
            f.write(chunk)

    return output_file


def ask_chatgpt(prompt, model="gpt-4o", max_tokens=2000):
    client = OpenAI(api_key=chatgpt_key)

    messages = []

    if chatgpt_system_prompt:
        messages.append({
            "role": "system",
            "content": chatgpt_system_prompt
        })

    messages.append({
        "role": "user",
        "content": prompt
    })

    response = client.chat.completions.create(
        model=model,
        messages=messages,
        max_tokens=max_tokens
    )

    return response.choices[0].message.content


def build_flux_reference_images(first_anchor_url=None, previous_last_frame_url=None):
    refs = []

    if first_anchor_url:
        refs.append(first_anchor_url)

    if previous_last_frame_url and previous_last_frame_url != first_anchor_url:
        refs.append(previous_last_frame_url)

    return refs[:8]


def generate_image(prompt, output_file="output.png", reference_images=None):
    headers = {
        "x-key": black_forestlabs_key,
        "Content-Type": "application/json",
        "accept": "application/json"
    }

    data = {
        "prompt": prompt,
        "width": 1024,
        "height": 1536
    }

    if reference_images:
        for i, img in enumerate(reference_images[:8]):
            key = "input_image" if i == 0 else f"input_image_{i+1}"
            data[key] = img

    response = requests.post(
        "https://api.bfl.ai/v1/flux-2-pro-preview",
        json=data,
        headers=headers
    )

    print("FLUX STATUS:", response.status_code)
    print("FLUX BODY:", response.text)
    response.raise_for_status()

    job = response.json()
    polling_url = job["polling_url"]

    print("Generating Flux image...")

    while True:
        result = requests.get(polling_url, headers=headers).json()
        status = result.get("status")
        print(status)

        if status == "Ready":
            output = result.get("result", {})
            image_url = output.get("sample")
            break

        if status in ["Failed", "Error"]:
            raise Exception(result)

        time.sleep(1)

    img = requests.get(image_url)
    img.raise_for_status()

    atomic_write_bytes(output_file, img.content)

    print("Saved:", output_file)
    return output_file


def poll_piapi_task(task_id, headers, timeout=900):
    start = time.time()
    last_status = None

    while True:
        if time.time() - start > timeout:
            raise TimeoutError(f"Task {task_id} timed out.")

        status_res = requests.get(
            f"https://api.piapi.ai/api/v1/task/{task_id}",
            headers=headers,
            timeout=60
        )
        status_res.raise_for_status()

        data = status_res.json()["data"]
        status = data.get("status", "").lower()

        if status != last_status:
            print(f"Status: {status}")
            last_status = status
        else:
            print(".", end="", flush=True)

        if status == "completed":
            print("\nTask completed!")
            return data

        if status in ["failed", "error", "cancelled"]:
            print("\nFull API failure response:")
            print(json.dumps(data, indent=2))
            raise Exception(f"Task failed: {data}")

        time.sleep(3)


def download_file(url, output_file):
    response = requests.get(url, timeout=120)
    response.raise_for_status()
    atomic_write_bytes(output_file, response.content)
    return output_file


def mux_audio_to_video(video_file, audio_file, output_file, shortest=True):
    cmd = [
        "ffmpeg",
        "-y",
        "-i", video_file,
        "-i", audio_file,
        "-c:v", "copy",
        "-c:a", "aac",
        "-b:a", "192k",
        "-map", "0:v:0",
        "-map", "1:a:0"
    ]

    if shortest:
        cmd.append("-shortest")

    cmd.append(output_file)

    run_cmd(cmd)

    if not os.path.exists(output_file):
        raise RuntimeError(f"Muxed output video not created: {output_file}")

    if os.path.getsize(output_file) == 0:
        raise RuntimeError(f"Muxed output video is empty: {output_file}")

    return output_file


def append_black_tail(video_file, output_file, tail_seconds=2):
    if not os.path.exists(video_file):
        raise RuntimeError(f"Video file does not exist: {video_file}")

    if os.path.getsize(video_file) == 0:
        raise RuntimeError(f"Video file is empty: {video_file}")

    probe_cmd = [
        "ffprobe",
        "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height,r_frame_rate",
        "-of", "json",
        video_file
    ]
    probe_result = subprocess.run(probe_cmd, capture_output=True, text=True)

    if probe_result.returncode != 0:
        raise RuntimeError(f"Could not probe video dimensions/fps for {video_file}")

    probe_data = json.loads(probe_result.stdout)
    streams = probe_data.get("streams", [])
    if not streams:
        raise RuntimeError(f"No video stream found in {video_file}")

    stream = streams[0]
    width = int(stream.get("width", 720))
    height = int(stream.get("height", 1280))
    fps = stream.get("r_frame_rate", "30/1")

    filter_complex = (
        f"[1:v]fps={fps},format=yuv420p,trim=duration={tail_seconds}[black];"
        f"[0:v][black]concat=n=2:v=1:a=0[v]"
    )

    cmd = [
        "ffmpeg",
        "-y",
        "-i", video_file,
        "-f", "lavfi",
        "-i", f"color=c=black:s={width}x{height}:r={fps}",
        "-filter_complex", filter_complex,
        "-map", "[v]",
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-an",
        output_file
    ]

    run_cmd(cmd)

    if not os.path.exists(output_file):
        raise RuntimeError(f"Black-tail output video not created: {output_file}")

    if os.path.getsize(output_file) == 0:
        raise RuntimeError(f"Black-tail output video is empty: {output_file}")

    return output_file


def extract_last_frame(video_file, output_image):
    if not os.path.exists(video_file):
        raise RuntimeError(f"Video file does not exist: {video_file}")

    if os.path.getsize(video_file) == 0:
        raise RuntimeError(f"Video file is empty: {video_file}")

    os.makedirs(os.path.dirname(output_image), exist_ok=True)

    temp_dir = os.path.join(os.path.dirname(video_file), "frame_extract_tmp")
    os.makedirs(temp_dir, exist_ok=True)

    temp_output = os.path.join(
        temp_dir,
        f"lastframe_{uuid.uuid4().hex[:8]}.png"
    )

    attempts = [
        {
            "label": "seek from end 0.5s",
            "cmd": [
                "ffmpeg",
                "-y",
                "-hide_banner",
                "-loglevel", "error",
                "-sseof", "-0.5",
                "-i", video_file,
                "-frames:v", "1",
                "-update", "1",
                temp_output
            ]
        },
        {
            "label": "seek from end 1.0s",
            "cmd": [
                "ffmpeg",
                "-y",
                "-hide_banner",
                "-loglevel", "error",
                "-sseof", "-1.0",
                "-i", video_file,
                "-frames:v", "1",
                "-update", "1",
                temp_output
            ]
        },
        {
            "label": "seek using duration - 0.5s",
            "cmd": None
        }
    ]

    duration = None
    try:
        duration = get_media_duration(video_file)
    except Exception as e:
        print(f"Warning: could not get duration for fallback seek: {e}")

    if duration is not None:
        seek_time = max(duration - 0.5, 0)
        attempts[2]["cmd"] = [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel", "error",
            "-ss", str(seek_time),
            "-i", video_file,
            "-frames:v", "1",
            "-update", "1",
            temp_output
        ]
    else:
        attempts.pop()

    last_error = None

    for attempt in attempts:
        print(f"Trying frame extraction: {attempt['label']}")

        if os.path.exists(temp_output):
            try:
                os.remove(temp_output)
            except OSError:
                pass

        result = subprocess.run(
            attempt["cmd"],
            capture_output=True,
            text=True
        )

        print("RETURN CODE:", result.returncode)
        if result.stdout.strip():
            print("STDOUT:")
            print(result.stdout)
        if result.stderr.strip():
            print("STDERR:")
            print(result.stderr)

        if result.returncode == 0 and os.path.exists(temp_output) and os.path.getsize(temp_output) > 0:
            shutil.copy2(temp_output, output_image)

            if not os.path.exists(output_image) or os.path.getsize(output_image) == 0:
                raise RuntimeError(f"Extracted temp frame existed, but final copy failed: {output_image}")

            print("Last frame saved:", output_image)
            return output_image

        last_error = RuntimeError(
            f"Frame extraction attempt failed: {attempt['label']}\n"
            f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
        )

    raise last_error or RuntimeError("Last frame extraction failed for unknown reason.")


def wan26_image2video_with_audio(
    prompt,
    start_image_url,
    audio_url,
    output_file="output.mp4",
    duration=5,
    resolution="720p",
    max_retries=3
):
    headers = {
        "x-api-key": piapi_key,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    if not wait_for_public_file(start_image_url):
        raise RuntimeError(f"Image not publicly reachable: {start_image_url}")

    if not wait_for_public_file(audio_url):
        raise RuntimeError(f"Audio not publicly reachable: {audio_url}")

    last_error = None

    for attempt in range(1, max_retries + 1):
        print(f"\nwan26_image2video_with_audio attempt {attempt}/{max_retries}")

        payload = {
            "model": "Wan",
            "task_type": "wan26-img2video",
            "input": {
                "prompt": prompt,
                "image": start_image_url,
                "audio_url": audio_url,
                "audio": True,
                "duration": int(duration),
                "resolution": resolution
            }
        }

        print("Submitting Wan 2.6 job...")
        print(json.dumps(payload, indent=2))

        try:
            res = requests.post(
                "https://api.piapi.ai/api/v1/task",
                headers=headers,
                json=payload,
                timeout=60
            )

            if not res.ok:
                print("HTTP STATUS:", res.status_code)
                print("RESPONSE TEXT:", res.text)
                res.raise_for_status()

            task = res.json()["data"]
            task_id = task["task_id"]

            print(f"Task ID: {task_id}")
            data = poll_piapi_task(task_id, headers)

            output = data.get("output", {})
            video_url = output.get("video_url") or output.get("video")

            if not video_url:
                raise Exception(f"No video URL in Wan response: {data}")

            print("Downloading Wan video...")
            download_file(video_url, output_file)

            print(f"Saved: {output_file}")
            return output_file, task_id, video_url

        except Exception as e:
            last_error = e
            print(f"\nAttempt {attempt} failed: {e}")

            if attempt < max_retries:
                print("Retrying in 5 seconds...")
                time.sleep(5)

    raise last_error


def poll_xai_video_request(request_id, timeout=900):
    start = time.time()
    last_status = None

    headers = {
        "Authorization": f"Bearer {xai_api_key}"
    }

    while True:
        if time.time() - start > timeout:
            raise TimeoutError(f"xAI video request {request_id} timed out.")

        res = requests.get(
            f"https://api.x.ai/v1/videos/{request_id}",
            headers=headers,
            timeout=60
        )
        res.raise_for_status()

        data = res.json()
        status = data.get("status", "").lower()

        if status != last_status:
            print(f"xAI status: {status}")
            last_status = status
        else:
            print(".", end="", flush=True)

        if status == "done":
            print("\nxAI video ready!")
            return data

        if status in ["failed", "expired"]:
            print("\nFull xAI failure response:")
            print(json.dumps(data, indent=2))
            raise Exception(f"xAI video request failed: {data}")

        time.sleep(5)


def grok_image2video(
    prompt,
    start_image_url,
    output_file="grok_output.mp4",
    duration_seconds=5,
    aspect_ratio="9:16",
    resolution="720p",
    max_retries=3
):
    if not wait_for_public_file(start_image_url):
        raise RuntimeError(f"Start image not publicly reachable: {start_image_url}")

    headers = {
        "Authorization": f"Bearer {xai_api_key}",
        "Content-Type": "application/json"
    }

    last_error = None

    for attempt in range(1, max_retries + 1):
        print(f"\ngrok_image2video attempt {attempt}/{max_retries}")

        payload = {
            "model": "grok-imagine-video",
            "prompt": prompt,
            "image": {
                "url": start_image_url
            },
            "duration": int(duration_seconds),
            "aspect_ratio": aspect_ratio,
            "resolution": resolution
        }

        print("Submitting Grok video job...")
        print(json.dumps(payload, indent=2))

        try:
            res = requests.post(
                "https://api.x.ai/v1/videos/generations",
                headers=headers,
                json=payload,
                timeout=60
            )

            if not res.ok:
                print("HTTP STATUS:", res.status_code)
                print("RESPONSE TEXT:", res.text)
                res.raise_for_status()

            request_id = res.json()["request_id"]
            print(f"Request ID: {request_id}")

            data = poll_xai_video_request(request_id)

            video_url = data.get("video", {}).get("url")
            if not video_url:
                raise Exception(f"No video.url in xAI response: {data}")

            print("Downloading Grok video...")
            download_file(video_url, output_file)

            print(f"Saved: {output_file}")
            return output_file, request_id, video_url

        except Exception as e:
            last_error = e
            print(f"\nAttempt {attempt} failed: {e}")

            if attempt < max_retries:
                print("Retrying in 5 seconds...")
                time.sleep(5)

    raise last_error


def combine_videos(video_files, output_file="final_commercial.mp4"):
    if not video_files:
        raise ValueError("No video files provided.")

    list_file = "concat_list.txt"

    with open(list_file, "w", encoding="utf-8") as f:
        for video in video_files:
            abs_path = os.path.abspath(video).replace("\\", "/")
            f.write(f"file '{abs_path}'\n")

    cmd = [
        "ffmpeg",
        "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", list_file,
        "-c:v", "libx264",
        "-c:a", "aac",
        "-pix_fmt", "yuv420p",
        output_file
    ]

    run_cmd(cmd)

    if not os.path.exists(output_file):
        raise RuntimeError(f"Final combined video not created: {output_file}")

    if os.path.getsize(output_file) == 0:
        raise RuntimeError(f"Final combined video is empty: {output_file}")

    print("Final combined video saved:", output_file)
    return output_file


def combine_videos_no_audio(video_files, output_file="final_video_only.mp4"):
    if not video_files:
        raise ValueError("No video files provided.")

    list_file = "concat_video_only_list.txt"

    with open(list_file, "w", encoding="utf-8") as f:
        for video in video_files:
            abs_path = os.path.abspath(video).replace("\\", "/")
            f.write(f"file '{abs_path}'\n")

    cmd = [
        "ffmpeg",
        "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", list_file,
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-an",
        output_file
    ]

    run_cmd(cmd)

    if not os.path.exists(output_file):
        raise RuntimeError(f"Combined video-only output not created: {output_file}")

    if os.path.getsize(output_file) == 0:
        raise RuntimeError(f"Combined video-only output is empty: {output_file}")

    print("Combined video-only file saved:", output_file)
    return output_file


def apply_final_fade(video_file, output_file, fade_seconds=1.0):
    duration = get_media_duration(video_file)
    fade_start = max(duration - fade_seconds, 0)

    cmd = [
        "ffmpeg",
        "-y",
        "-i", video_file,
        "-vf", f"fade=t=out:st={fade_start}:d={fade_seconds}",
        "-af", f"afade=t=out:st={fade_start}:d={fade_seconds}",
        "-c:v", "libx264",
        "-c:a", "aac",
        "-pix_fmt", "yuv420p",
        output_file
    ]

    run_cmd(cmd)

    if not os.path.exists(output_file):
        raise RuntimeError(f"Final faded video not created: {output_file}")

    if os.path.getsize(output_file) == 0:
        raise RuntimeError(f"Final faded video is empty: {output_file}")

    return output_file


def build_full_ad_narration(scenes):
    lines = []
    for scene in scenes:
        line = (scene.get("narration") or "").strip()
        if line:
            lines.append(line)
    return "\n\n".join(lines)


def allocate_grok_scene_durations(scenes, total_audio_duration, min_scene_seconds=3):
    word_counts = []
    for scene in scenes:
        narration = (scene.get("narration") or "").strip()
        word_counts.append(max(1, len(narration.split())))

    total_words = sum(word_counts)
    if total_words <= 0:
        return [min_scene_seconds for _ in scenes]

    durations = []
    remaining = total_audio_duration

    for idx, wc in enumerate(word_counts):
        if idx == len(word_counts) - 1:
            duration = max(min_scene_seconds, math.ceil(remaining))
        else:
            share = total_audio_duration * (wc / total_words)
            duration = max(min_scene_seconds, round(share))
            remaining -= duration

        durations.append(int(duration))

    total_allocated = sum(durations)
    target_total = max(len(scenes) * min_scene_seconds, math.ceil(total_audio_duration))
    if total_allocated < target_total:
        durations[-1] += (target_total - total_allocated)

    return durations


def clean_video_prompt(prompt, mode="general"):
    prompt = prompt.strip().rstrip(".")

    base_rules = [
        "One clear subject.",
        "One simple realistic action.",
        "Premium commercial quality.",
        "Stable realistic motion.",
        "No sudden movement.",
        "No chaotic motion.",
        "No exaggerated acting.",
        "No crowds.",
        "No fast action.",
        "Vertical ad composition.",
        "Maintain the subject's identity and wardrobe.",
        "Maintain product shape and label consistency."
    ]

    if mode == "wan":
        mode_rules = [
            "Talking-to-camera delivery should be subtle and natural.",
            "Minimal head movement.",
            "Gentle facial expression changes only.",
            "Body remains mostly still.",
            "Static camera or very slow push-in only."
        ]
    else:
        mode_rules = [
            "Simple motion only.",
            "Static camera, slow push-in, or slow pan only.",
            "No dramatic camera movement.",
            "No scene transformation."
        ]

    return f"{prompt}. " + " ".join(base_rules + mode_rules)


def validate_plan(plan):
    scenes = plan.get("scenes", [])
    if len(scenes) != 3:
        raise ValueError("Plan must contain exactly 3 scenes.")

    allowed_speakers = {"human", "animal", "none"}

    for idx, scene in enumerate(scenes, start=1):
        for key in ["image_prompt", "video_prompt", "narration", "on_screen_text"]:
            if key not in scene or not isinstance(scene[key], str) or not scene[key].strip():
                raise ValueError(f"Scene {idx} missing valid '{key}'.")

        if scene.get("speaker_type") not in allowed_speakers:
            raise ValueError(f"Scene {idx} has invalid speaker_type.")

        if not isinstance(scene.get("needs_lipsync"), bool):
            raise ValueError(f"Scene {idx} needs_lipsync must be boolean.")

        vp = scene["video_prompt"].lower()
        banned = [
            "crowd", "running", "dancing", "explosion", "fight",
            "chaotic", "rapid cuts", "camera whip", "spinning"
        ]
        if any(word in vp for word in banned):
            raise ValueError(f"Scene {idx} video_prompt is too chaotic for this pipeline.")


def generate_ad_plan(ad_for, ad_about, ad_details=""):
    prompt = f"""
Create a high-quality commercial plan.

The ad is for: {ad_for}
The ad is about: {ad_about}
Creative direction: {ad_details if ad_details else "None"}

IMPORTANT:
- Prioritize video stability over creativity
- Keep scenes simple and visually strong
- Make it feel like a premium vertical ad
- Use shots that work well for image-guided video
- 3 scenes total
- Each scene = ONE subject + ONE action
- Keep motion minimal and realistic
- No complex interactions
- If a visible character is speaking to camera, set needs_lipsync to true
- Use speaker_type human, animal, or none

Return JSON only.
"""

    response = ask_chatgpt(prompt)
    print("ChatGPT response:")
    print(response)

    cleaned = response.strip()

    if cleaned.startswith("```json"):
        cleaned = cleaned[7:]
    if cleaned.startswith("```"):
        cleaned = cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]

    plan = json.loads(cleaned.strip())
    validate_plan(plan)
    return plan


def save_scene_debug(output_dir, run_id, scene_number, payload):
    path = os.path.join(output_dir, f"{run_id}_scene_{scene_number}_debug.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)


def build_commercial_from_plan(plan, output_dir="ad_output", final_output="final_commercial.mp4", video_mode="wan"):
    ensure_public_data_dir()
    os.makedirs(output_dir, exist_ok=True)

    scenes = plan.get("scenes", [])
    if not scenes:
        raise ValueError("No scenes found in plan.")

    if not voices:
        raise ValueError("voices list is empty.")

    run_id = make_run_id()
    selected_voice = random.choice(voices)

    print("Run ID:", run_id)
    print("Selected voice:", selected_voice)
    print("Video mode:", video_mode)

    scene_videos = []
    first_anchor_url = None
    previous_last_frame_url = None

    full_ad_audio_file = None
    full_ad_audio_url = None
    grok_scene_durations = None

    if video_mode == "grok":
        full_ad_audio_name = make_public_filename(run_id, "fullad_audio", 0, "mp3")
        full_ad_audio_file = save_path_in_public_dir(full_ad_audio_name)
        full_ad_audio_url = get_public_url(full_ad_audio_name)

        full_ad_narration = build_full_ad_narration(scenes)

        print("Generating full-ad Grok narration once for consistent voice tone...")
        text_to_speech(
            full_ad_narration,
            output_file=full_ad_audio_file,
            voice_id=selected_voice
        )

        if not wait_for_local_file(full_ad_audio_file, timeout=10, min_bytes=100):
            raise RuntimeError(f"Full ad audio not created locally: {full_ad_audio_file}")

        if not wait_for_public_file(full_ad_audio_url, timeout=30, sleep_seconds=2, method="GET", min_bytes=100):
            raise RuntimeError(f"Full ad audio not publicly reachable: {full_ad_audio_url}")

        full_audio_duration = get_audio_duration(full_ad_audio_file)
        print(f"Full-ad narration duration: {full_audio_duration:.2f}s")

        grok_scene_durations = allocate_grok_scene_durations(
            scenes,
            total_audio_duration=full_audio_duration,
            min_scene_seconds=3
        )
        print("Allocated Grok scene durations:", grok_scene_durations)

    for i, scene in enumerate(scenes, start=1):
        print("\n==============================")
        print(f"Processing scene {i}")
        print("==============================")

        image_prompt = scene.get("image_prompt", "")
        video_prompt = clean_video_prompt(
            scene.get("video_prompt", ""),
            mode=video_mode
        )
        narration = scene.get("narration", "")

        public_image_name = make_public_filename(run_id, "image", i, "png")
        public_audio_name = make_public_filename(run_id, "audio", i, "mp3")
        public_last_frame_name = make_public_filename(run_id, "lastframe", i, "png")

        raw_video_name = make_public_filename(run_id, "rawvideo", i, "mp4")
        final_scene_video_name = make_public_filename(run_id, "video", i, "mp4")

        public_image_file = save_path_in_public_dir(public_image_name)
        public_audio_file = save_path_in_public_dir(public_audio_name)
        public_last_frame_file = save_path_in_public_dir(public_last_frame_name)

        raw_video_file = os.path.join(output_dir, raw_video_name)
        final_scene_video_file = os.path.join(output_dir, final_scene_video_name)

        image_url = get_public_url(public_image_name)
        audio_url = get_public_url(public_audio_name)
        last_frame_url = get_public_url(public_last_frame_name)

        print("Generating Flux anchor image...")

        flux_refs = build_flux_reference_images(
            first_anchor_url=first_anchor_url if i > 1 else None,
            previous_last_frame_url=previous_last_frame_url if i > 1 else None
        )

        print("Flux reference images:", flux_refs)

        generate_image(
            image_prompt,
            output_file=public_image_file,
            reference_images=flux_refs if flux_refs else None
        )

        if not wait_for_local_file(public_image_file, timeout=10, min_bytes=100):
            raise RuntimeError(f"Image not created locally: {public_image_file}")

        if not wait_for_public_file(image_url, timeout=30, sleep_seconds=2, method="GET", min_bytes=100):
            raise RuntimeError(f"Image not publicly reachable: {image_url}")

        if i == 1:
            first_anchor_url = image_url

        if video_mode == "wan":
            print("Generating speech for Wan scene...")

            text_to_speech(
                narration,
                output_file=public_audio_file,
                voice_id=selected_voice
            )

            if not wait_for_local_file(public_audio_file, timeout=10, min_bytes=100):
                raise RuntimeError(f"Audio not created locally: {public_audio_file}")

            if not wait_for_public_file(audio_url, timeout=30, sleep_seconds=2, method="GET", min_bytes=100):
                raise RuntimeError(f"Audio not publicly reachable: {audio_url}")

            spoken_duration = get_audio_duration(public_audio_file)
            scene_duration = 5

            if spoken_duration > 5.0:
                print(f"WARNING: Wan mode audio is {spoken_duration:.2f}s but video duration is fixed at 5s.")

            print(f"Spoken narration duration: {spoken_duration:.2f}s")
            print(f"Scene duration: {scene_duration}s")
            print("Image URL:", image_url)
            print("Audio URL:", audio_url)
        else:
            scene_duration = grok_scene_durations[i - 1]
            spoken_duration = None

            print(f"Grok scene duration allocated from full-ad TTS: {scene_duration}s")
            print("Image URL:", image_url)
            print("Full audio URL:", full_ad_audio_url)

        save_scene_debug(output_dir, run_id, i, {
            "scene_number": i,
            "image_prompt": image_prompt,
            "video_prompt": video_prompt,
            "narration": narration,
            "spoken_duration": spoken_duration,
            "image_url": image_url,
            "audio_url": audio_url if video_mode == "wan" else full_ad_audio_url,
            "scene_duration": scene_duration,
            "video_mode": video_mode,
            "first_anchor_url": first_anchor_url,
            "previous_last_frame_url": previous_last_frame_url
        })

        if video_mode == "wan":
            print("Generating video with Wan 2.6 talking character mode...")
            wan26_image2video_with_audio(
                prompt=video_prompt,
                start_image_url=image_url,
                audio_url=audio_url,
                output_file=final_scene_video_file,
                duration=5,
                resolution="720p"
            )
        elif video_mode == "grok":
            print("Generating Grok video-only scene...")
            grok_image2video(
                prompt=video_prompt,
                start_image_url=image_url,
                output_file=raw_video_file,
                duration_seconds=scene_duration,
                aspect_ratio="9:16",
                resolution="720p"
            )

            if not os.path.exists(raw_video_file):
                raise RuntimeError(f"Raw Grok video missing: {raw_video_file}")

            if os.path.getsize(raw_video_file) == 0:
                raise RuntimeError(f"Raw Grok video is empty: {raw_video_file}")

            final_scene_video_file = raw_video_file
        else:
            raise ValueError("video_mode must be 'wan' or 'grok'")

        if not os.path.exists(final_scene_video_file):
            raise RuntimeError(f"Final scene video missing before frame extraction: {final_scene_video_file}")

        if os.path.getsize(final_scene_video_file) == 0:
            raise RuntimeError(f"Final scene video is empty before frame extraction: {final_scene_video_file}")

        print("Extracting last frame for continuity...")
        extract_last_frame(final_scene_video_file, public_last_frame_file)

        if not wait_for_local_file(public_last_frame_file, timeout=5, min_bytes=50):
            raise RuntimeError(f"Last frame was not created locally: {public_last_frame_file}")

        print("Last frame extracted locally:", public_last_frame_file)

        if wait_for_public_file(last_frame_url, timeout=30, sleep_seconds=2, method="GET", min_bytes=50):
            previous_last_frame_url = last_frame_url
            print("Last frame is publicly reachable:", last_frame_url)
        else:
            print(f"Warning: last frame exists locally but is not publicly reachable yet: {last_frame_url}")
            previous_last_frame_url = None

        scene_videos.append(final_scene_video_file)

    final_video_name = f"{run_id}_{final_output}"

    if video_mode == "wan":
        final_video_path = os.path.join(output_dir, final_video_name)

        print("\nCombining all Wan scene videos...")
        combine_videos(scene_videos, output_file=final_video_path)
        return final_video_path

    combined_video_only_name = make_public_filename(run_id, "combined_video_only", 0, "mp4")
    combined_video_only_file = os.path.join(output_dir, combined_video_only_name)

    combined_with_black_name = make_public_filename(run_id, "combined_video_blacktail", 0, "mp4")
    combined_with_black_file = os.path.join(output_dir, combined_with_black_name)

    muxed_final_name = make_public_filename(run_id, "combined_muxed", 0, "mp4")
    muxed_final_file = os.path.join(output_dir, muxed_final_name)

    final_video_path = os.path.join(output_dir, final_video_name)

    print("\nCombining Grok scene videos into one video-only file...")
    combine_videos_no_audio(scene_videos, output_file=combined_video_only_file)

    print("Appending 2-second black tail only to the end of the entire Grok ad...")
    append_black_tail(
        video_file=combined_video_only_file,
        output_file=combined_with_black_file,
        tail_seconds=2
    )

    print("Muxing full-ad narration once at the end...")
    mux_audio_to_video(
        video_file=combined_with_black_file,
        audio_file=full_ad_audio_file,
        output_file=muxed_final_file,
        shortest=False
    )

    print("Applying fade only to the very end of the final Grok ad...")
    apply_final_fade(
        video_file=muxed_final_file,
        output_file=final_video_path,
        fade_seconds=1.0
    )

    return final_video_path


def main():
    print("=== AI Commercial Generator ===")
    print("1 = Talking character (Flux + Wan 2.6 + attached audio)")
    print("2 = Grok video ad (Flux + Grok video + ElevenLabs audio mux)")

    mode_choice = input("Choose video mode (1 or 2): ").strip()
    ad_for = input("What is the ad for? ").strip()
    ad_about = input("What is the ad about? ").strip()
    ad_details = input(
        "Any extra details or style notes? "
        "(example: funny, talking cat, vertical TikTok style, luxury, dramatic): "
    ).strip()

    if not ad_for:
        print("You need to enter what the ad is for.")
        return

    if not ad_about:
        print("You need to enter what the ad is about.")
        return

    if mode_choice == "1":
        video_mode = "wan"
    elif mode_choice == "2":
        video_mode = "grok"
    else:
        print("Invalid option. Use 1 or 2.")
        return

    print("\nGenerating ad plan...")
    plan = generate_ad_plan(ad_for, ad_about, ad_details)

    print("\nAd plan created:")
    print(json.dumps(plan, indent=2))

    print("\nBuilding final commercial...")
    final_video = build_commercial_from_plan(
        plan,
        video_mode=video_mode
    )

    print("\nDone!")
    print("Final commercial:", final_video)


if __name__ == "__main__":
    main()