import os
import flask
from flask_sock import Sock
from google.cloud import speech
from google.oauth2 import service_account
import queue
import threading

# --- Load Google Cloud credentials ---
# Recommended for Render: use environment variable GOOGLE_APPLICATION_CREDENTIALS
# So no need to hardcode path
client = speech.SpeechClient()

# --- Flask app setup ---
app = flask.Flask(__name__)
sock = Sock(app)

@app.route("/")
def index():
    return flask.send_file("index.html")

@sock.route("/audio")
def audio(ws):
    audio_q = queue.Queue()

    # Thread to receive binary audio from browser
    def receive_audio():
        while True:
            data = ws.receive()
            if data is None:
                break
            audio_q.put(data)
        audio_q.put(None)  # end marker

    threading.Thread(target=receive_audio, daemon=True).start()

    # --- Google Speech Recognition Config ---
    config = speech.RecognitionConfig(
        encoding=speech.RecognitionConfig.AudioEncoding.WEBM_OPUS,
        sample_rate_hertz=48000,
        language_code="en-US",
        enable_automatic_punctuation=True,
    )

    streaming_config = speech.StreamingRecognitionConfig(
        config=config,
        interim_results=True,   # get live partials
        single_utterance=False  # don’t stop on silence
    )

    # Generator to yield audio chunks
    def request_generator():
        while True:
            chunk = audio_q.get()
            if chunk is None:
                break
            yield speech.StreamingRecognizeRequest(audio_content=chunk)

    try:
        responses = client.streaming_recognize(streaming_config, request_generator())

        # --- Handle Streaming Results ---
        for response in responses:
            for result in response.results:
                transcript = result.alternatives[0].transcript

                if result.is_final:
                    # Only send final, stable results
                    ws.send("[FINAL]" + transcript)
                else:
                    # Send interim results for live display
                    ws.send("[INTERIM]" + transcript)

    except Exception as e:
        print("Streaming error:", e)
    finally:
        ws.close()

if __name__ == "__main__":
    # Bind to dynamic port (Render sets PORT environment variable)
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
