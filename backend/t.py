import asyncio
import httpx


async def main():
    url = "http://localhost:8000/ainvoke"
    async with httpx.AsyncClient() as client:
        response = await client.post(
            url, json={"query": "define epistemic uncertainty"}
        )
        print(response.text)


asyncio.run(main())
