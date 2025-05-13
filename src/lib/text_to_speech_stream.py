import asyncio
import os

import numpy as np
from elevenlabs.client import ElevenLabs
from elevenlabs import VoiceSettings
from scipy.signal import resample_poly

def resample_pcm(pcm: np.ndarray, src_rate: int, target_rate: int) -> np.ndarray:
    """
    Resample a flat interleaved stereo PCM buffer.
    """
    # Reshape: (N frames, 2 channels)
    frames = pcm.reshape(-1, 2)

    # Resample each channel
    left = resample_poly(frames[:, 0], target_rate, src_rate)
    right = resample_poly(frames[:, 1], target_rate, src_rate)

    # Stack and interleave
    resampled = np.column_stack((left, right)).astype(np.int16).flatten()
    return resampled

client = ElevenLabs(api_key=os.getenv('ELEVENLABS_API_KEY'))

def text_to_speech_stream(text: str):
    # Configure voice settings as needed
    voice_settings = VoiceSettings(
        stability=0.75,
        similarity_boost=0.75,
        style=0.5,
        use_speaker_boost=True
    )

    # Initiate streaming TTS request
    audio_stream = client.text_to_speech.convert_as_stream(
        text=text,
        voice_id="21m00Tcm4TlvDq8ikWAM",  # Replace with your desired voice ID
        model_id="eleven_multilingual_v2",
        voice_settings=voice_settings,
        output_format="pcm_22050"  # Ensure this matches the format expected by pydub
    )

    # Process the streaming audio chunks
    buffer = bytearray()

    for chunk in audio_stream:
        if not isinstance(chunk, bytes):
            continue
        
        samples = np.frombuffer(chunk, dtype=np.int16)

        resampled = resample_poly(samples, up=48000, down=22050)  # shape: (n',)
        resampled = resampled.astype(np.int16)  # convert back to int16

        # Stack left and right copies side by side, then flatten:
        stereo = np.column_stack((resampled, resampled)).flatten()

        yield stereo
