import numpy as np

def calculate_energy(audio_data):
    energy = np.sum(audio_data ** 2)

def vad(audio_data, energy_threshold=0.001):
    audio_data = np.asarray(audio_data, dtype=np.float32)
    #print(f"Max audio_data: ", np.max(audio_data))
        
    MAX_SAMPLE = 32767
    max_energy = len(audio_data) * (MAX_SAMPLE ** 2)
    energy = np.sum(audio_data ** 2)

    #print(f"{max_energy} : {energy}")
    
    return energy > max_energy * energy_threshold
