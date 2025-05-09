import wave
import numpy as np
import uuid


def create_wav_from_pcm(pcm_samples, sample_rate):
    file_path = f"/app/wav_files/{uuid.uuid4()}.wav"
    with wave.open(file_path, "wb") as wf:
        wf.setnchannels(1)  # Mono
        wf.setsampwidth(2)  # 16-bit PCM
        wf.setframerate(sample_rate)
        wf.writeframes(np.array(pcm_samples, dtype=np.int16).tobytes())
        return file_path