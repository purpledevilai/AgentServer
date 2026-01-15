import asyncio
from typing import Callable, Optional
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
        
        # Three co-length arrays for audio data
        self.samples = deque()
        self.sentence_ids = deque()
        self.is_lasts = deque()
        
        self.timestamp = 0
        self.time_base = fractions.Fraction(1, self.sample_rate)
        self.start_time = time.time()
        
        # Callbacks
        self.on_is_speaking_sentence: Callable[[int], None] = lambda sentence_id: print(f"Is speaking sentence: {sentence_id}")
        self.on_stoped_speaking: Callable[[], None] = lambda: print("Stopped speaking")
        self.on_invocation_audio_complete: Callable[[], None] = lambda: print("Invocation audio complete")
        
        self.current_sentence_id: Optional[int] = None
        
        # Interruption support
        self.paused = False
        self.completed_sentence_ids: set[int] = set()  # Track fully played sentences

    def on(self, event: str, callback: Callable):
        if event == "is_speaking_sentence":
            self.on_is_speaking_sentence = callback
        elif event == "stoped_speaking":
            self.on_stoped_speaking = callback
        elif event == "invocation_audio_complete":
            self.on_invocation_audio_complete = callback
        else:
            raise ValueError(f"Unknown event: {event}")

    async def recv(self):
        # Wait until it's time to send the next 20ms frame
        elapsed = time.time() - self.start_time
        expected_ts = self.timestamp * self.time_base
        sleep_time = float(expected_ts - elapsed)
        if sleep_time > 0:
            await asyncio.sleep(sleep_time)

        needed_samples = self.frame_size * self.channels
        
        # First: Check if we have fewer samples than needed (end of audio or empty)
        if len(self.samples) <= needed_samples:
            # Dequeue whatever is left
            remaining_count = len(self.samples)
            if remaining_count > 0:
                remaining_samples = [self.samples.popleft() for _ in range(remaining_count)]
                remaining_sentence_ids = [self.sentence_ids.popleft() for _ in range(remaining_count)]
                remaining_is_lasts = [self.is_lasts.popleft() for _ in range(remaining_count)]
                
                # Check if any is_last flags are True
                if any(remaining_is_lasts):
                    self.on_invocation_audio_complete()
                
                # Track sentence completion
                if self.current_sentence_id is not None:
                    self.completed_sentence_ids.add(self.current_sentence_id)
                    self.current_sentence_id = None
                    self.on_stoped_speaking()
            
            # Output silence
            frame_data = [0] * needed_samples
            
        # Second: Check if paused
        elif self.paused:
            # Output silence, don't dequeue
            frame_data = [0] * needed_samples
            
        # Third: Normal playback
        else:
            # Dequeue from all 3 arrays
            frame_data = [self.samples.popleft() for _ in range(needed_samples)]
            chunk_sentence_ids = [self.sentence_ids.popleft() for _ in range(needed_samples)]
            chunk_is_lasts = [self.is_lasts.popleft() for _ in range(needed_samples)]
            
            # Check for sentence transitions
            new_sentence_id = chunk_sentence_ids[-1]
            if self.current_sentence_id != new_sentence_id:
                # Previous sentence completed, new one starting
                if self.current_sentence_id is not None:
                    self.completed_sentence_ids.add(self.current_sentence_id)
                self.current_sentence_id = new_sentence_id
                if new_sentence_id is not None:
                    self.on_is_speaking_sentence(self.current_sentence_id)
                
        frame = np.array(frame_data, dtype=np.int16).reshape((1, -1))
        audio_frame = av.AudioFrame.from_ndarray(frame, format='s16', layout='stereo')
        audio_frame.sample_rate = self.sample_rate
        audio_frame.pts = self.timestamp
        audio_frame.time_base = self.time_base

        self.timestamp += self.frame_size
        return audio_frame

    def pause(self):
        """Pause audio playback - output silence instead of dequeuing."""
        self.paused = True

    def resume(self):
        """Resume audio playback - continue dequeuing samples."""
        self.paused = False

    def clear_queue(self):
        """Clear all pending audio samples."""
        self.samples.clear()
        self.sentence_ids.clear()
        self.is_lasts.clear()
        self.current_sentence_id = None

    def get_completed_sentence_ids(self) -> set[int]:
        """Get the set of sentence IDs that have been fully played."""
        return self.completed_sentence_ids.copy()

    def reset_completed_sentences(self):
        """Clear the set of completed sentence IDs."""
        self.completed_sentence_ids.clear()

    def has_audio(self) -> bool:
        """Check if there are samples in the queue."""
        return len(self.samples) > 0

    def enqueue_audio_samples(self, audio_samples, sentence_id, is_last: bool = False):
        """
        Enqueue audio samples with associated sentence_id and is_last flag.
        
        Args:
            audio_samples: PCM audio samples to enqueue
            sentence_id: The sentence ID these samples belong to (can be None for is_last marker)
            is_last: True if this marks the end of an invocation
        """
        try:
            sample_count = len(audio_samples) if len(audio_samples) > 0 else 1
            
            if len(audio_samples) > 0:
                self.samples.extend(audio_samples)
            else:
                # For is_last marker with no audio, add a single placeholder
                self.samples.append(0)
            
            self.sentence_ids.extend([sentence_id] * sample_count)
            self.is_lasts.extend([is_last] * sample_count)
                
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
