# Squat Scan

A small local web app that estimates squat depth and posture from an uploaded image or MP4 video. It uses MediaPipe Pose to detect body landmarks, OpenCV to process media, and a browser interface to show the preview and results.

> This is an experimental pose-estimation demo, not medical advice or a substitute for coaching. Camera angle, lighting, occlusion, and clothing can affect its estimates.

## Features

- Analyze a JPG or PNG image, or an MP4 video.
- Show a pose overlay and knee/back angle estimates.
- Summarize detected repetitions and estimated depth for videos.
- Run locally with Flask.

## Requirements

- Python with support for the pinned MediaPipe version (the project was run with Python 3.12).
- `pip`.

## Setup

Clone the repository, then open a terminal in the project directory.

### Windows PowerShell

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### macOS / Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## Run

Start the Flask development server from the project directory:

```bash
python app.py
```

Open [http://127.0.0.1:5000](http://127.0.0.1:5000), select a JPG, PNG, or MP4 file, and click **Analyze**. Press `Ctrl+C` in the terminal to stop the server.

The server accepts uploads up to 100 MB. Video analysis samples frames to keep processing bounded; results are estimates and may vary with the recording.

## Project structure

```text
.
├── app.py                 # Flask routes and pose/video analysis
├── requirements.txt       # Python dependencies
└── static/
    ├── index.html         # App page
    ├── app.js             # Upload flow, playback overlay, and result rendering
    └── style.css          # Layout and visual styles
```

## Troubleshooting

- If `python` is not found on Windows, try `py -3.12 app.py`.
- If a dependency fails to install, confirm that your Python version is supported by the pinned MediaPipe release, then recreate the virtual environment and install `requirements.txt` again.
- For more reliable pose estimates, use a clear side view with the full body visible and good lighting.

## License

No license is currently specified. Add a `LICENSE` file before redistributing this project under open-source terms.
