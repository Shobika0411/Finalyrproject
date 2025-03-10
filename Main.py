import os
import json
import time
import wave
import asyncio
import shutil
import subprocess
from fastapi import FastAPI, WebSocket, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from vosk import Model, KaldiRecognizer

app = FastAPI()

# Paths
UPLOAD_DIR = "backend/audio"
FRONTEND_PATH = "C:/Users/ccs/Desktop/sign/backend/frontend.html"
VOSK_MODEL_PATH = "C:/Users/ccs/Desktop/sign/backend/models/vosk-model-small-en-us-0.15"

# Ensure directories exist
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Check if VOSK model exists
if not os.path.exists(VOSK_MODEL_PATH):
    raise RuntimeError(f" Vosk model not found at {VOSK_MODEL_PATH}. Download it from https://alphacephei.com/vosk/models and place it correctly.")

# Serve frontend HTML
@app.get("/", response_class=FileResponse)
async def serve_html():
    if os.path.exists(FRONTEND_PATH):
        return FRONTEND_PATH
    raise HTTPException(status_code=404, detail="Frontend file not found")

# Convert uploaded audio to WAV format
def convert_audio_to_wav(input_audio, output_wav):
    try:
        subprocess.run(["ffmpeg", "-i", input_audio, "-ac", "1", "-ar", "16000", output_wav, "-y"], check=True)
        print(f" Audio converted: {output_wav}")
        return output_wav
    except subprocess.CalledProcessError as e:
        print(f" FFmpeg conversion failed: {e}")
        raise HTTPException(status_code=500, detail="Audio conversion failed")

# Real-time transcription with subtitle buffering
async def transcribe_audio(websocket: WebSocket, audio_path):
    print(f"Starting transcription for: {audio_path}")

    if not os.path.exists(audio_path):
        await websocket.send_text(json.dumps({"subtitle": " Error: Audio file missing"}))
        return

    try:
        model = Model(VOSK_MODEL_PATH)
        wf = wave.open(audio_path, "rb")
        recognizer = KaldiRecognizer(model, wf.getframerate())
        recognizer.SetWords(True)

        sentence_buffer = []
        last_sent_time = time.time()

        while True:
            data = wf.readframes(4000)
            if not data:
                print(" No more audio data to process.")
                break

            if recognizer.AcceptWaveform(data):
                result = json.loads(recognizer.Result())
                if "result" in result:
                    words = [word_info["word"] for word_info in result["result"]]
                    sentence_buffer.extend(words)

            # Send subtitles every 1.5 seconds or if buffer has 5+ words
            if (time.time() - last_sent_time > 1.5 and sentence_buffer) or len(sentence_buffer) >= 5:
                full_sentence = " ".join(sentence_buffer)
                await websocket.send_text(json.dumps({"subtitle": full_sentence}))
                print(f"📢 Sent subtitle: {full_sentence}")
                sentence_buffer = []
                last_sent_time = time.time()

        # Send remaining words
        if sentence_buffer:
            await websocket.send_text(json.dumps({"subtitle": " ".join(sentence_buffer)}))

        await websocket.send_text(json.dumps({"subtitle": ""}))  # End signal
        print(" Transcription complete.")
    except Exception as e:
        print(f" Error during transcription: {e}")
        await websocket.send_text(json.dumps({"subtitle": f"Error: {str(e)}"}))

# API to upload audio files
@app.post("/upload/")
async def upload_file(file: UploadFile = File(...)):
    # Validate file type
    if not file.filename.lower().endswith(('.wav', '.mp3', '.mp4', '.m4a', '.aac', '.ogg')):
        raise HTTPException(status_code=400, detail=" Unsupported file type. Please upload an audio file.")

    file_path = os.path.join(UPLOAD_DIR, file.filename)

    with open(file_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    print(f" Uploaded file: {file_path}")

    # Convert to WAV
    wav_path = os.path.join(UPLOAD_DIR, "converted_audio.wav")
    convert_audio_to_wav(file_path, wav_path)

    return {"message": " File uploaded and converted successfully", "wav_path": wav_path}

# WebSocket for real-time subtitle streaming
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    print(" WebSocket connection established")
    await websocket.accept()
    audio_path = os.path.join(UPLOAD_DIR, "converted_audio.wav")
    await transcribe_audio(websocket, audio_path)
    print(" WebSocket connection closed")
    await websocket.close()
