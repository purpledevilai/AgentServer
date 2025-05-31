import asyncio
from typing import Callable
from aiortc import MediaStreamTrack
import av
import numpy as np
from pydub import AudioSegment
from collections import deque
import fractions
import time

class SyntheticAudioTrack(MediaStreamTrack):
    kind = "audio"

    def __init__(self):
        super().__init__()
        self.sample_rate = 48000
        self.channels = 2
        self.frame_size = 960  # 20ms frame at 48kHz
        self.samples = deque()
        self.sentence_ids = deque()
        self.timestamp = 0
        self.time_base = fractions.Fraction(1, self.sample_rate)
        self.start_time = time.time()
        self.on_is_speaking_sentence: Callable[[str], None] = lambda sentence_id: print(f"Is speaking sentence: {sentence_id}")
        self.on_stoped_speaking: Callable[[], None] = lambda: print("Stopped speaking")
        self.current_sentence_id = None
        self.validating_speaking_stop = False

    def on(self, event: str, callback: Callable):
        if event == "is_speaking_sentence":
            self.on_is_speaking_sentence = callback
        elif event == "stoped_speaking":
            self.on_stoped_speaking = callback
        else:
            raise ValueError(f"Unknown event: {event}")

    async def recv(self):
        # Wait until it's time to send the next 20ms frame
        elapsed = time.time() - self.start_time
        expected_ts = self.timestamp * self.time_base
        sleep_time = float(expected_ts - elapsed)
        if sleep_time > 0:
            await asyncio.sleep(sleep_time)

        # Get 20ms worth of samples or silence
        needed_samples = self.frame_size * self.channels
        if len(self.samples) >= needed_samples:
            frame_data = [self.samples.popleft() for _ in range(needed_samples)]
            chunk_sentence_ids = [self.sentence_ids.popleft() for _ in range(needed_samples)]
            if self.current_sentence_id is None or chunk_sentence_ids[-1] != self.current_sentence_id:
                self.current_sentence_id = chunk_sentence_ids[-1]
                self.on_is_speaking_sentence(self.current_sentence_id)
        else:
            frame_data = [0] * needed_samples  # Silence
            if self.current_sentence_id is not None:
                self.current_sentence_id = None
                asyncio.create_task(self.possible_speaking_stop())
                
        frame = np.array(frame_data, dtype=np.int16).reshape((1, -1))
        audio_frame = av.AudioFrame.from_ndarray(frame, format='s16', layout='stereo')
        audio_frame.sample_rate = self.sample_rate
        audio_frame.pts = self.timestamp
        audio_frame.time_base = self.time_base

        self.timestamp += self.frame_size
        return audio_frame
    
    async def possible_speaking_stop(self):
        if self.validating_speaking_stop:
            return
        self.validating_speaking_stop = True
        await asyncio.sleep(1)  # Wait a bit to see if more samples come in
        if len(self.samples) < (self.frame_size * self.channels):
            self.on_stoped_speaking()
        self.validating_speaking_stop = False

    def enqueue_audio_samples(self, audio_samples, sentence_id=None):
        try:
            self.samples.extend(audio_samples)
            if sentence_id is not None:
                self.sentence_ids.extend([sentence_id] * len(audio_samples))
        except Exception as e:
            print(f"[enqueue_audio_samples] Error: {e}")
            raise

    async def enqueue_wav(self, wav_path):
        try:
            audio = AudioSegment.from_wav(wav_path)

            if audio.channels != self.channels:
                audio = audio.set_channels(self.channels)
            if audio.frame_rate != self.sample_rate:
                audio = audio.set_frame_rate(self.sample_rate)

            samples = np.frombuffer(audio.raw_data, dtype=np.int16)
            self.samples.extend(samples)

        except Exception as e:
            print(f"[enqueue_wav] Error: {e}")
            raise

    def is_speaking(self):
        return len(self.samples) > (self.frame_size * self.channels)
