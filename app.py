import os
import tempfile
import base64

import cv2
import numpy as np
from flask import Flask, jsonify, request, send_from_directory
import mediapipe as mp

app = Flask(__name__, static_folder="static")
app.config["MAX_CONTENT_LENGTH"] = 100 * 1024 * 1024
POSE = mp.solutions.pose


def angle(a, b, c):
    a, b, c = (np.array(p) for p in (a, b, c))
    v1, v2 = a - b, c - b
    return float(np.degrees(np.arctan2(v2[1], v2[0]) - np.arctan2(v1[1], v1[0])) % 360)


def pose_result(image, pose, forced_side=None):
    result = pose.process(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
    if not result.pose_landmarks:
        return None
    lm = result.pose_landmarks.landmark
    sides = (("LEFT", POSE.PoseLandmark.LEFT_SHOULDER.value, POSE.PoseLandmark.LEFT_HIP.value,
              POSE.PoseLandmark.LEFT_KNEE.value, POSE.PoseLandmark.LEFT_ANKLE.value),
             ("RIGHT", POSE.PoseLandmark.RIGHT_SHOULDER.value, POSE.PoseLandmark.RIGHT_HIP.value,
              POSE.PoseLandmark.RIGHT_KNEE.value, POSE.PoseLandmark.RIGHT_ANKLE.value))
    side_name, *ids = next((s[0], *s[1:]) for s in sides if s[0] == forced_side) if forced_side else max(sides, key=lambda side: np.mean([lm[i].visibility for i in side[2:]]))
    points = [lm[i] for i in ids]
    knee = angle(*[(p.x, p.y) for p in points[1:]])
    knee = min(knee, 360 - knee)
    shoulder, hip, joint, ankle = points
    back = float(np.degrees(np.arctan2(abs(shoulder.x - hip.x), abs(shoulder.y - hip.y))))
    confidence = float(np.mean([p.visibility for p in points[1:]]))
    depth = verdict(confidence, knee)
    color = {"GOOD": (255, 229, 0), "SHALLOW": (214, 43, 255),
             "NEEDS REVIEW": (0, 179, 255)}[depth]
    h, w = image.shape[:2]
    xy = [(int(p.x * w), int(p.y * h)) for p in points]
    overlay = image.copy()
    for a, b in ((0, 1), (1, 2), (2, 3)):
        cv2.line(overlay, xy[a], xy[b], color, 2, cv2.LINE_AA)
    for x, y in xy:
        cv2.circle(overlay, (x, y), 4, color, -1, cv2.LINE_AA)
    scale = .5
    labels = ((f"KNEE {round(knee)} deg", (xy[2][0] + 10, xy[2][1] + 18)),
              (f"BACK {round(back)} deg", (xy[1][0] + 10, xy[1][1] - 10)))
    for text, origin in labels:
        cv2.putText(overlay, text, origin, cv2.FONT_HERSHEY_SIMPLEX, scale,
                    (0, 0, 0), 3, cv2.LINE_AA)
        cv2.putText(overlay, text, origin, cv2.FONT_HERSHEY_SIMPLEX, scale,
                    color, 1, cv2.LINE_AA)
    annotated = cv2.addWeighted(overlay, .75, image, .25, 0)
    return {"angle": knee, "back": back, "confidence": confidence, "annotated": annotated,
            "side": side_name, "pts": [[round(p.x, 3), round(p.y, 3)] for p in points]}


def encoded(image):
    ok, data = cv2.imencode(".jpg", image)
    if not ok:
        raise ValueError("Could not encode annotated image.")
    return base64.b64encode(data).decode("ascii")


def posture(back):
    return "BACK OK" if back <= 45 else "LEANING FORWARD"


def verdict(confidence, minimum):
    return "GOOD" if minimum <= 100 else "SHALLOW"


@app.get("/")
def index():
    return send_from_directory("static", "index.html")


@app.post("/analyze")
def analyze():
    upload = request.files.get("file")
    if not upload or not upload.filename:
        return jsonify(error="Choose an image or MP4 video."), 400
    ext = os.path.splitext(upload.filename)[1].lower()
    if ext not in (".jpg", ".jpeg", ".png", ".mp4"):
        return jsonify(error="Supported formats are JPG, PNG, and MP4."), 400
    suffix = ext
    path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
            upload.save(f)
            path = f.name
        with POSE.Pose(static_image_mode=ext != ".mp4", model_complexity=1, smooth_landmarks=True,
                       min_detection_confidence=0.6, min_tracking_confidence=0.6) as pose:
            if ext != ".mp4":
                image = cv2.imread(path)
                item = pose_result(image, pose) if image is not None else None
                if item is None:
                    return jsonify(error="No person detected. Use a clear full-body image."), 422
                a, back, conf = item["angle"], item["back"], item["confidence"]
                return jsonify(type="image", angle=round(a, 1), back_angle=round(back, 1),
                               confidence=round(conf, 2), verdict=verdict(conf, a),
                               posture=posture(back), annotated=encoded(item["annotated"]))
            side_scores = {"LEFT": [], "RIGHT": []}
            cap = cv2.VideoCapture(path)
            probe = POSE.Pose(static_image_mode=False, model_complexity=1, smooth_landmarks=True,
                              min_detection_confidence=0.6, min_tracking_confidence=0.6)
            frame = sampled = 0
            while cap.isOpened():
                ok, image = cap.read()
                if not ok: break
                if frame % 2 == 0 and sampled < 300:
                    sampled += 1
                    if image.shape[1] > 640: image = cv2.resize(image, (640, round(image.shape[0] * 640 / image.shape[1])))
                    result = probe.process(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
                    if result.pose_landmarks:
                        lm = result.pose_landmarks.landmark
                        for name, ids in (("LEFT", (POSE.PoseLandmark.LEFT_HIP.value, POSE.PoseLandmark.LEFT_KNEE.value, POSE.PoseLandmark.LEFT_ANKLE.value)), ("RIGHT", (POSE.PoseLandmark.RIGHT_HIP.value, POSE.PoseLandmark.RIGHT_KNEE.value, POSE.PoseLandmark.RIGHT_ANKLE.value))):
                            side_scores[name].append(float(np.mean([lm[j].visibility for j in ids])))
                frame += 1
            cap.release(); probe.close()
            chosen_side = max(side_scores, key=lambda side: np.mean(side_scores[side]) if side_scores[side] else 0)
            cap = cv2.VideoCapture(path)
            fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
            angles, confidences, backs, frames, samples, frame, sampled = [], [], [], [], [], 0, 0
            while cap.isOpened():
                ok, image = cap.read()
                if not ok:
                    break
                if frame % 2 == 0 and sampled < 300:
                    sampled += 1
                    height, width = image.shape[:2]
                    if width > 640:
                        image = cv2.resize(image, (640, round(height * 640 / width)))
                    item = pose_result(image.copy(), pose, chosen_side)
                    if item:
                        angles.append(item["angle"]); confidences.append(item["confidence"])
                        backs.append(item["back"]); frames.append(item["annotated"])
                        samples.append(dict(t=round(frame / fps, 3), knee=round(item["angle"], 3),
                                            back=round(item["back"], 3), vis=round(item["confidence"], 3),
                                            pts=item["pts"]))
                frame += 1
            cap.release()
            if samples:
                raw_pts = np.asarray([s["pts"] for s in samples], dtype=float)
                for joint in range(raw_pts.shape[1]):
                    for axis in range(2):
                        series = raw_pts[:, joint, axis].copy()
                        for i, s in enumerate(samples):
                            if s["vis"] < 0.5 and i: series[i] = series[i - 1]
                        ema = np.empty_like(series); ema[0] = series[0]
                        for i in range(1, len(series)): ema[i] = 0.4 * series[i] + 0.6 * ema[i - 1]
                        padded = np.pad(ema, (2, 2), mode="edge")
                        filtered = np.array([np.median(padded[i:i + 5]) for i in range(len(ema))])
                        for i, s in enumerate(samples): s["pts"][joint][axis] = round(float(filtered[i]), 3)
        if not angles:
            return jsonify(error="No person detected. Use a clear video with a visible full body."), 422
        padded_angles = np.pad(angles, (1, 1), mode="edge")
        smooth_angles = np.convolve(padded_angles, np.ones(3) / 3, mode="valid").tolist()
        reps, low, low_i, state = [], smooth_angles[0], 0, "down"
        for i, a in enumerate(smooth_angles[1:], 1):
            if a < low:
                low, low_i = a, i
            if state == "down" and a > low + 10:
                conf = float(np.mean(confidences[max(0, i - 10):i + 1]))
                bottom = samples[low_i]
                reps.append(dict(rep=len(reps) + 1, min_angle=round(low, 1),
                                 back_angle=round(backs[low_i], 1),
                                 confidence=round(conf, 2), verdict=("GOOD" if low <= 100 or bottom["pts"][1][1] >= bottom["pts"][2][1] else "SHALLOW"),
                                 posture=posture(backs[low_i]), t=round(low_i * 2 / fps, 3)))
                state, low, low_i = "up", a, i
            elif state == "up" and a < low - 10:
                state, low, low_i = "down", a, i
        deepest = int(np.argmin(smooth_angles))
        return jsonify(type="video", reps=reps, angles=[round(a, 1) for a in angles],
                       total_reps=len(reps), back_angle=round(backs[deepest], 1),
                       annotated=encoded(frames[deepest]), frames=samples, fps=round(fps, 3))
    except Exception as exc:
        return jsonify(error=f"Could not analyze file: {exc}"), 400
    finally:
        if path and os.path.exists(path):
            os.unlink(path)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
