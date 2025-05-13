import asyncio
from aiortc import MediaStreamTrack
import av
import numpy as np
from pydub import AudioSegment
from collections import deque
import fractions
import time
import io

class SyntheticAudioTrack(MediaStreamTrack):
    kind = "audio"

    def __init__(self):
        super().__init__()
        self.sample_rate = 48000
        self.channels = 2
        self.frame_size = 960  # 20ms frame at 48kHz
        self.samples = deque()
        self.timestamp = 0
        self.time_base = fractions.Fraction(1, self.sample_rate)
        self.start_time = time.time()

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
        else:
            frame_data = [0] * needed_samples  # Silence

        frame = np.array(frame_data, dtype=np.int16).reshape((1, -1))
        audio_frame = av.AudioFrame.from_ndarray(frame, format='s16', layout='stereo')
        audio_frame.sample_rate = self.sample_rate
        audio_frame.pts = self.timestamp
        audio_frame.time_base = self.time_base

        self.timestamp += self.frame_size
        return audio_frame

    async def enqueue_audio_samples(self, audio_samples):
        try:
            self.samples.extend(audio_samples)
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
