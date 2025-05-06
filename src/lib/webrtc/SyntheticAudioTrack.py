from aiortc import MediaStreamTrack
import av
from pydub import AudioSegment
import numpy as np
import asyncio
from collections import deque
import fractions

class SyntheticAudioTrack(MediaStreamTrack):
    kind = "audio"

    def __init__(self):
        super().__init__()
        self.sample_rate = 48000
        self.channels = 2  # Stereo
        self.samples = deque()  # Store flat interleaved int16 samples
        self.timestamp = 0
        self.silence = np.zeros(960 * self.channels, dtype=np.int16)
        self.lock = asyncio.Lock()

    async def recv(self):
        await asyncio.sleep(0.02)

        async with self.lock:
            if len(self.samples) >= 960 * self.channels:
                frame_samples = [self.samples.popleft() for _ in range(960 * self.channels)]
                frame = np.array(frame_samples, dtype=np.int16)
            else:
                frame = self.silence

        try:
            # reshape to (1, samples) for interleaved s16 format
            frame = frame.reshape((1, 960 * self.channels))
            audio_frame = av.AudioFrame.from_ndarray(frame, format='s16', layout='stereo')
            audio_frame.sample_rate = self.sample_rate

            audio_frame.pts = self.timestamp
            audio_frame.time_base = fractions.Fraction(1, self.sample_rate)
            self.timestamp += 960

            return audio_frame

        except Exception as e:
            print(f"Error creating audio frame: {e}")


    async def enqueue_wav(self, wav_path):
        # Load audio using pydub
        audio = AudioSegment.from_wav(wav_path)

        # Ensure stereo
        if audio.channels == 1:
            audio = audio.set_channels(2)
        elif audio.channels != 2:
            raise ValueError("Only mono or stereo WAV files are supported.")

        # Resample if necessary
        if audio.frame_rate != self.sample_rate:
            audio = audio.set_frame_rate(self.sample_rate)

        # Get raw PCM data
        samples = np.frombuffer(audio.raw_data, dtype=np.int16)

        async with self.lock:
            self.samples.extend(samples)
