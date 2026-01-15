import re
from typing import AsyncGenerator, TypedDict


class TokenObject(TypedDict):
    token: str
    is_last: bool


class SentenceObject(TypedDict):
    sentence: str
    is_last: bool


# Regex to match sentence-ending punctuation
SENTENCE_END_RE = re.compile(r"([.!?])([\s\n]|$)")


async def sentence_stream(
    token_generator: AsyncGenerator[TokenObject, None]
) -> AsyncGenerator[SentenceObject, None]:
    """
    Converts a stream of token objects into a stream of sentence objects.
    
    Input: {token: str, is_last: bool}
    Output: {sentence: str, is_last: bool}
    
    When is_last token is received, flushes any remaining buffer and then
    yields an is_last sentence marker.
    """
    buffer = ""

    async for token_obj in token_generator:
        token = token_obj["token"]
        is_last = token_obj["is_last"]
        
        # If this is the last token marker
        if is_last:
            # Flush any remaining text in buffer first
            if buffer.strip():
                yield SentenceObject(sentence=buffer.strip(), is_last=False)
                buffer = ""
            # Then yield the is_last marker
            yield SentenceObject(sentence="", is_last=True)
            continue
        
        # Normal token processing
        buffer += token

        while True:
            match = SENTENCE_END_RE.search(buffer)
            if not match:
                break

            end_idx = match.end()
            sentence = buffer[:end_idx].strip()
            if sentence:
                yield SentenceObject(sentence=sentence, is_last=False)
            buffer = buffer[end_idx:]
