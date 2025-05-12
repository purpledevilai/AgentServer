import uuid
import pyttsx3
engine = pyttsx3.init()

def text_to_speech(text: str):
    try:
        # Set properties before saving
        wav_path = f"/app/wav_files/{uuid.uuid4()}.wav"
        text = f"   {text.strip()}    "
        engine.save_to_file(text, wav_path)
        engine.runAndWait()
        return wav_path
    except Exception as e:
        raise Exception(f"Error converting text to speech: {e}")