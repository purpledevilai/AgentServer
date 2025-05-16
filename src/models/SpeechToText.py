import asyncio
import os
import uuid
from typing import Optional, Callable
from lib.vad import vad
from models.TranscriptionService import TranscriptionService
import time

class SpeechToText:

    def __init__(
            self,
            on_speech_detected: Optional[Callable[[str], None]] = None,
            vad_threshold: float = 0.001,
            silence_duration_ms: int = 1000,
        ):
        # callbacks
        self.on_speech_detected = on_speech_detected

        # Configuration
        self.vad_threshold = vad_threshold
        self.silence_duration_ms = silence_duration_ms

        # Connect to Transcription service
        self.transcription_service = TranscriptionService(
            transcription_service_url=os.environ["TRANSCRIPTION_SERVER_URL"],
        )

        # State variables
        self.speaking = False
        self.silence_sample_count = 0
        self.current_transcribe_id = None
        self.is_finalizing = False


    async def connect_to_transcription_service(self):
        # Connect to the transcription service
        await self.transcription_service.connect()


    async def add_audio_data(self, audio_data, sample_rate):
        try:
            # VAD
            has_voice = vad(audio_data=audio_data, energy_threshold=self.vad_threshold)
            #print(f"VAD: {has_voice}")
            if has_voice:
                print(f"Speaking...")
                if not self.speaking:
                    self.speaking = True
                    self.current_transcribe_id = f"{uuid.uuid4()}"
                self.silence_sample_count = 0
                await self.transcription_service.add_audio_data(self.current_transcribe_id, audio_data)
            else:
                if self.speaking:
                    await self.transcription_service.add_audio_data(self.current_transcribe_id, audio_data)
                    self.silence_sample_count += len(audio_data)
                    silence_samples_to_wait = int((self.silence_duration_ms / 1000) * sample_rate)
                    if self.silence_sample_count >= silence_samples_to_wait:
                        # Enough silence detected
                        asyncio.create_task(self.finalize_transcript(self.current_transcribe_id, sample_rate))
                        # Reset state
                        self.speaking = False
                        self.silence_sample_count = 0
                        self.current_transcribe_id = None
        except Exception as e:
            print(f"Error durring vad: {e}")
            raise e
                

    async def finalize_transcript(self, transcribe_id, sample_rate):

        start = time.time()
        # Get transcription
        text = await self.transcription_service.finalize_transcription(transcribe_id, sample_rate)
        end = time.time()
        print(f"Transcription time {end - start:.4f} seconds")

        # If the transcription is not empty and not just a thank you, send it to the callback
        if text and text.strip() not in ("Thank you.", ".", "", ".  .  .  ."):
            # Emit the final transcription
            if self.on_speech_detected:
                self.on_speech_detected(text)

    def close(self):
        # Close the transcription service connection
        self.transcription_service.close()
        print("Closed transcription service connection")

    