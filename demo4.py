import os
import threading
import pyaudio
from six.moves import queue
from google.cloud import speech_v1p1beta1 as speech
from google.oauth2 import service_account
import tkinter as tk
from tkinter import scrolledtext

# Audio recording parameters
RATE = 16000
CHUNK = int(RATE / 10)  # 100ms

# Replace with the path to your Google Cloud service account JSON key file
service_account_file = 'demo.json'
credentials = service_account.Credentials.from_service_account_file(service_account_file)

class MicrophoneStream:
    def __init__(self, rate, chunk):
        self._rate = rate
        self._chunk = chunk
        self._buff = queue.Queue()
        self.closed = True

    def __enter__(self):
        self._audio_interface = pyaudio.PyAudio()
        self._audio_stream = self._audio_interface.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=self._rate,
            input=True,
            frames_per_buffer=self._chunk,
            stream_callback=self._fill_buffer,
        )
        self.closed = False
        return self

    def __exit__(self, type, value, traceback):
        self._audio_stream.stop_stream()
        self._audio_stream.close()
        self.closed = True
        self._buff.put(None)
        self._audio_interface.terminate()

    def _fill_buffer(self, in_data, frame_count, time_info, status_flags):
        self._buff.put(in_data)
        return None, pyaudio.paContinue

    def generator(self):
        while not self.closed:
            chunk = self._buff.get()
            if chunk is None:
                return
            data = [chunk]

            while True:
                try:
                    chunk = self._buff.get(block=False)
                    if chunk is None:
                        return
                    data.append(chunk)
                except queue.Empty:
                    break

            yield b"".join(data)

import re

class TranscriptionApp:
    def __init__(self, master):
        self.master = master
        self.master.title("Live Audio Transcription")
        
        self.start_button = tk.Button(master, text="Start Recording", command=self.start_recording)
        self.start_button.pack(pady=10)
        
        self.stop_button = tk.Button(master, text="Stop Recording", command=self.stop_recording, state=tk.DISABLED)
        self.stop_button.pack(pady=10)
        
        self.transcription_text = scrolledtext.ScrolledText(master, wrap=tk.WORD, width=50, height=15)
        self.transcription_text.pack(pady=10)
        
        self.is_recording = False
        self.thread = None
        self.transcribed_text = ""
        self.last_transcript = ""
        self.buffer = []

    def start_recording(self):
        self.is_recording = True
        self.start_button.config(state=tk.DISABLED)
        self.stop_button.config(state=tk.NORMAL)
        self.thread = threading.Thread(target=self.transcribe_audio)
        self.thread.start()

    def stop_recording(self):
        self.is_recording = False
        self.start_button.config(state=tk.NORMAL)
        self.stop_button.config(state=tk.DISABLED)

    def clean_text(self, text):
        """Cleans up the text by removing repeated words and filler phrases."""
        # Remove extra spaces and unwanted characters
        text = re.sub(r'\s+', ' ', text).strip()
        # Remove repeated phrases
        text = re.sub(r'(\b\w+\b)(\s+\1)+', r'\1', text)
        # Remove unnecessary filler words
        text = re.sub(r'\b(uh|um|like)\b', '', text)
        # Remove duplicated phrases or segments
        text = re.sub(r'(\b\w+\b)(\s+\1)+', r'\1', text)
        return text

    def transcribe_audio(self):
        client = speech.SpeechClient(credentials=credentials)
        config = speech.RecognitionConfig(
            encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
            sample_rate_hertz=RATE,
            language_code="en-US",
        )
        streaming_config = speech.StreamingRecognitionConfig(
            config=config,
            interim_results=True,
        )

        with MicrophoneStream(RATE, CHUNK) as stream:
            audio_generator = stream.generator()
            requests = (speech.StreamingRecognizeRequest(audio_content=content) for content in audio_generator)
            responses = client.streaming_recognize(config=streaming_config, requests=requests)

            for response in responses:
                if not self.is_recording:
                    break
                if not response.results:
                    continue
                result = response.results[0]
                if not result.alternatives:
                    continue
                
                # Get the latest transcript
                transcript = result.alternatives[0].transcript

                # Use a buffer to accumulate results
                self.buffer.append(transcript)
                combined_text = ' '.join(self.buffer)
                
                # Clean and deduplicate the text
                clean_text = self.clean_text(combined_text)
                
                # Check if cleaned text differs from last displayed text
                if clean_text != self.transcribed_text:
                    self.transcribed_text = clean_text
                    self.transcription_text.delete(1.0, tk.END)
                    self.transcription_text.insert(tk.END, self.transcribed_text)
                    self.transcription_text.see(tk.END)


if __name__ == "__main__":  
    root = tk.Tk()
    app = TranscriptionApp(root)
    root.mainloop()
