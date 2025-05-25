from typing import Callable
import numpy as np


class SoundCalibrator:

    def __init__(
            self,
            on_measurement: Callable[[float], None],
            samples_per_chunk: int = 960,
            sample_rate: int = 48000,
            calibration_duration: int = 5
        ):
        self.energy_samples = []
        self.on_measurement = on_measurement
        self.samples_per_chunk = samples_per_chunk
        self.sample_rate = sample_rate
        self.calibration_duration = calibration_duration  # seconds
        self.clb_energy_sample_len = (sample_rate / samples_per_chunk) * calibration_duration
        

    def add_audio_data(self, audio_data):
        # Calculate energy
        energy = np.sum(audio_data ** 2)
        self.energy_samples.append(energy)
        
        # If over calibration
        if len(self.energy_samples) > self.clb_energy_sample_len:
            avg_energy = np.array(self.energy_samples).mean()
            self.on_measurement(avg_energy)
            self.energy_samples = []
            

    