# def first_occurrence_end(text, substrings):
#     indices = [(text.find(sub) + len(sub))
#                for sub in substrings if text.find(sub) != -1]
#     # Return the lowest index, or -1 if no match is found
#     return min(indices) if indices else -1


# async def sentence_stream(token_generator):
#     text = ''
#     async for token in token_generator:
#         text += token
#         split_index = first_occurrence_end(
#             text, [". ", "! ", "? ", ".\n", "!\n", "?\n"]
#         )
#         if split_index != -1:
#             yield text[:split_index]
#             text = text[split_index:]
#     if text:
#         yield text

import re
from typing import AsyncGenerator


# Regex to match sentence-ending punctuation
SENTENCE_END_RE = re.compile(r"([.!?])([\s\n]|$)")

async def sentence_stream(token_generator: AsyncGenerator[str, None]) -> AsyncGenerator[str, None]:
    buffer = ""

    async for token in token_generator:
        buffer += token

        while True:
            match = SENTENCE_END_RE.search(buffer)
            if not match:
                break

            end_idx = match.end()
            sentence = buffer[:end_idx].strip()
            if sentence:
                yield sentence
            buffer = buffer[end_idx:]

    # Flush any remaining text at the end
    if buffer.strip():
        yield buffer.strip()