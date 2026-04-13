import edge_tts
import asyncio

async def main():
    voices = await edge_tts.list_voices()
    telugu = [v for v in voices if "te-IN" in v["ShortName"]]
    for v in telugu:
        print(v["ShortName"], "-", v["Gender"])

asyncio.run(main())