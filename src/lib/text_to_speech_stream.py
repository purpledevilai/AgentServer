import asyncio
import os
from typing import AsyncGenerator
import numpy as np
from elevenlabs.client import ElevenLabs
from elevenlabs import VoiceSettings
from scipy.signal import resample_poly

client = ElevenLabs(api_key=os.getenv('ELEVENLABS_API_KEY'))

async def text_to_speech_stream(text: str, voice_id: str):

    if not voice_id:
        voice_id = "5egO01tkUjEzu7xSSE8M"  # Default voice ID if not provided

    voice_settings = VoiceSettings(
        stability=0.75,
        similarity_boost=0.75,
        style=0.5,
        use_speaker_boost=True
    )

    loop = asyncio.get_event_loop()

    # Use a thread to avoid blocking the event loop with ElevenLabs call
    stream = await loop.run_in_executor(None, lambda: client.text_to_speech.convert_as_stream(
        text=text,
        voice_id=voice_id,
        model_id="eleven_multilingual_v2",
        voice_settings=voice_settings,
        output_format="pcm_48000"
    ))

    # Now parse stream in executor too
    def process_stream():
        for chunk in stream:
            if not isinstance(chunk, bytes):
                continue
            samples = np.frombuffer(chunk, dtype=np.int16)
            stereo = np.column_stack((samples, samples)).flatten()
            # resampled = resample_poly(samples, up=48000, down=22050).astype(np.int16)
            # stereo = np.column_stack((resampled, resampled)).flatten()
            yield stereo

    # Use executor to yield PCM chunks without blocking event loop
    for pcm_chunk in await loop.run_in_executor(None, lambda: list(process_stream())):
        yield pcm_chunk
