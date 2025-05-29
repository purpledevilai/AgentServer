from typing import Callable
import numpy as np


class SoundCalibrator:

    def __init__(
            self,
            samples_per_chunk: int = 960,
            sample_rate: int = 48000,
            calibration_duration: int = 5
        ):
        self.energy_samples = []
        self.samples_per_chunk = samples_per_chunk
        self.sample_rate = sample_rate
        self.calibration_duration = calibration_duration  # seconds
        self.clb_energy_sample_len = (sample_rate / samples_per_chunk) * calibration_duration
        self.on_measurement: Callable[[float], None] = lambda measurement: print(f"Calibration Measurment: {measurement}")
        
    def on(self, event: str, callback: Callable):
        if event == "measurement":
            self.on_measurement = callback
        else:
            raise ValueError(f"Unknown event: {event}")

    def add_audio_data(self, audio_data):
        # Calculate energy
        energy = np.sum(audio_data ** 2)
        self.energy_samples.append(energy)
        
        # If over calibration
        if len(self.energy_samples) > self.clb_energy_sample_len:
            avg_energy = np.array(self.energy_samples).mean()
            self.on_measurement(avg_energy)
            self.energy_samples = []
            

    