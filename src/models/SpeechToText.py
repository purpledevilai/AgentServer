import copy
import asyncio
from typing import Optional, Callable
from lib.vad import vad
from lib.create_wav_from_pcm import create_wav_from_pcm

class SpeechToText:

    def __init__(
            self,
            on_speech_detected: Optional[Callable[[str], None]] = None,
            vad_threshold: float = 0.0001,
            silence_duration_ms: int = 1000,
        ):
        # callbacks
        self.on_speech_detected = on_speech_detected

        # Configuration
        self.vad_threshold = vad_threshold
        self.silence_duration_ms = silence_duration_ms

        # State variables
        self.pcm_samples = []
        self.has_begun_speaking = False
        self.start_speech_index = 0
        self.silence_sample_count = 0



    def add_audio_data(self, audio_data, sample_rate):

        # Add audio data to the buffer
        sample_index = len(self.pcm_samples)
        self.pcm_samples.extend(audio_data)

        # Detect if frame is speech
        has_voice = vad(audio_data=audio_data, energy_threshold=self.vad_threshold)

        # If speech detected...
        if has_voice:
            # Turn on has_begun speeking, if not already, and reset silence count
            if not self.has_begun_speaking:
                self.has_begun_speaking = True
                self.speech_start_index = sample_index
            self.silence_sample_count = 0 # Reset silence count if speaking
            return # Do nothing else
        
        # No speech detected
        if not self.has_begun_speaking:
            # No speech detected and not speaking: do nothing
            return
        
        # Increment silence count
        self.silence_sample_count += len(audio_data)

        # Determine if there has been enough silence
        silence_samples_to_wait = int((self.silence_duration_ms / 1000) * sample_rate)
        if self.silence_sample_count < silence_samples_to_wait:
            # Still in silence: do nothing
            return

        # Speech has ended: mark end index
        end_speech_index = len(self.pcm_samples) - 1

        # Make a deep copy of the pcm samples for transcription - so we can safely clear pcm samples
        detected_audio = copy.deepcopy(self.pcm_samples[self.start_speech_index:end_speech_index])

        # Start transcribing detected section of audio
        asyncio.create_task(self.attempt_transcription_on_audio_segment(
            pcm_samples=detected_audio,
            sample_rate=sample_rate
        ))

        # Reset state
        self.pcm_samples = []
        self.has_begun_speaking = False
        self.start_speech_index = 0
        self.silence_sample_count = 0
                

    async def attempt_transcription_on_audio_segment(self, pcm_samples, sample_rate):

        # Create wav file from pcm samples
        file_path = create_wav_from_pcm(pcm_samples=pcm_samples, sample_rate=sample_rate)
        print("detected an audio segment")

    