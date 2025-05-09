import asyncio
import numpy as np
from deepgram import DeepgramClient, LiveTranscriptionEvents, LiveOptions
from lib.vad import vad
from lib.webrtc.functions.till_true import till_true

class DeepgramSTT:
    def __init__(self, sample_rate, on_text, vad_threshold=0.0001, silence_duration_ms=1000):
        self.sample_rate = sample_rate
        self.on_text = on_text
        self.vad_threshold = vad_threshold
        self.silence_duration_ms = silence_duration_ms

        self.speaking = False
        self.silence_sample_count = 0
        self.latest_final_transcript = ""
        self.connection = None
        self.awaiting_next_transcript = False

        self._setup_deepgram()

    def _setup_deepgram(self):
        self.deepgram = DeepgramClient()
        self.connection = self.deepgram.listen.live.v("1")
        self.connection.on(LiveTranscriptionEvents.Transcript, self._on_transcript)
        options = LiveOptions(
            model="nova-2",
            language="en-US",
            encoding="linear16",
            sample_rate=self.sample_rate,
            channels=1,
            punctuate=True,
            interim_results=False,  # Only get final results
        )
        if not self.connection.start(options):
            raise RuntimeError("Failed to start Deepgram connection")

    def add_audio_data(self, audio_data):
        # Convert list of PCM samples to bytes and send to Deepgram
        arr = np.array(audio_data, dtype=np.int16)
        audio_bytes = arr.tobytes()
        self.connection.send(audio_bytes)

        # VAD logic
        has_voice = vad(audio_data=audio_data, energy_threshold=self.vad_threshold)
        #print(f"VAD: {has_voice}")
        if has_voice:
            if not self.speaking:
                self.speaking = True
            self.silence_sample_count = 0
        else:
            if self.speaking:
                self.silence_sample_count += len(audio_data)
                silence_samples_to_wait = int((self.silence_duration_ms / 1000) * self.sample_rate)
                if self.silence_sample_count >= silence_samples_to_wait and not self.awaiting_next_transcript:
                    # Enough silence detected, emit the latest final transcript
                    self.awaiting_next_transcript = True
                    asyncio.create_task(self._wait_for_and_return_transcript())


    async def _wait_for_and_return_transcript(self):
        await till_true(lambda: self.latest_final_transcript != "")
        self.on_text(self.latest_final_transcript)
        self.latest_final_transcript = ""
        self.speaking = False
        self.silence_sample_count = 0
        self.awaiting_next_transcript = False


    def _on_transcript(self, _, result, **kwargs):
        # Only store final transcripts
        if result.is_final:
            sentence = result.channel.alternatives[0].transcript
            if sentence:
                self.latest_final_transcript = sentence
                print(f"on transcript: {sentence}")

    def finish(self):
        self.connection.finish()