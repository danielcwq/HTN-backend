import cohere
co = cohere.ClientV2(api_key="nFdUCIfojuOcXRZ8I5yZlfqU9aEU8cj6nWYkAzwF")

res = co.chat(
    model="command-a-reasoning-08-2025",
    messages=[
        {
            "role": "user",
            "content": "Which is bigger, 9.9 or 9.11?",
        }
    ],
)

print(res)
#need to find a way to include reasoning traces if needed, but maybe fast inference is the thing right now 