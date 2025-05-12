import os
import requests
import tempfile
from pydub import AudioSegment


def text_to_wav_file(text, output_path=None):
    try:
        voice_id = "21m00Tcm4TlvDq8ikWAM"#"IKne3meq5aSn9XLyUdCD"
        response = requests.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
            headers={
                "Accept": "audio/mpeg",
                "Content-Type": "application/json",
                "xi-api-key": os.getenv('ELEVENLABS_API_KEY')
            },
            json={
                "text": text,
                "model_id": "eleven_monolingual_v1",
                "voice_settings": {
                    "stability": 0.5,
                    "similarity_boost": 0.5
                }
            },
            stream=True
        )

        if response.status_code != 200:
            raise Exception(f"ElevenLabs API error: {response.status_code} {response.text}")

        # Save the MP3 stream to a temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as temp_mp3_file:
            for chunk in response.iter_content(chunk_size=1024):
                if chunk:
                    temp_mp3_file.write(chunk)
            temp_mp3_path = temp_mp3_file.name

        # Define output WAV file path
        if output_path is None:
            output_path = tempfile.mktemp(suffix=".wav")

        # Convert MP3 to WAV
        audio = AudioSegment.from_mp3(temp_mp3_path)
        audio.export(output_path, format="wav")

        return output_path

    except Exception as e:
        raise Exception(f"Error converting text to WAV: {e}")

    finally:
        if 'temp_mp3_path' in locals() and os.path.exists(temp_mp3_path):
            os.remove(temp_mp3_path)
