import os
import logging
import threading
import time
import whisper
import moviepy.editor as mp
from flask import Flask, request, jsonify, render_template, send_from_directory
from flask_socketio import SocketIO
from flask_cors import CORS

app = Flask(_name_, static_folder="uploads")
socketio = SocketIO(app, cors_allowed_origins="*")
CORS(app)

UPLOAD_FOLDER = "uploads"
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# Load Whisper model once for faster processing
whisper_model = whisper.load_model("base")

# Ensure the logging is set up
logging.basicConfig(level=logging.INFO)

def extract_audio(video_path, audio_path="uploads/audio.wav"):
    """Extracts audio from a video file."""
    video = mp.VideoFileClip(video_path)
    video.audio.write_audiofile(audio_path)
    return audio_path

def stream_subtitles(audio_path):
    """Streams subtitles in real-time using Whisper."""
    result = whisper_model.transcribe(audio_path, word_timestamps=True)
    
    for segment in result["segments"]:
        start_time = segment["start"]
        end_time = segment["end"]
        text = segment["text"]

        # Emit subtitle data with proper start and end times
        socketio.emit("subtitle", {"start": start_time, "end": end_time, "text": text})
        time.sleep(end_time - start_time)  # Simulate real-time streaming

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/upload", methods=["POST"])
def upload_video():
    """Handles video upload and starts real-time subtitle generation."""
    if "video" not in request.files:
        logging.error("No video file part in the request")
        return jsonify({"error": "No video uploaded"}), 400
    
    file = request.files["video"]
    if file.filename == "":
        logging.error("No selected file")
        return jsonify({"error": "No file selected"}), 400

    try:
        video_path = os.path.join(UPLOAD_FOLDER, file.filename)
        file.save(video_path)
        logging.info(f"Video saved at: {video_path}")

        audio_path = extract_audio(video_path)

        # Run subtitle streaming in a separate thread
        threading.Thread(target=stream_subtitles, args=(audio_path,)).start()

        return jsonify({"video_url": f"/uploads/{file.filename}"}), 200

    except Exception as e:
        logging.error(f"Error saving video: {str(e)}")
        return jsonify({"error": "Error saving video"}), 500

@app.route("/uploads/<filename>")
def uploaded_file(filename):
    """Serves uploaded videos."""
    return send_from_directory(UPLOAD_FOLDER, filename)

if _name_ == "_main_":
    socketio.run(app, debug=True)
