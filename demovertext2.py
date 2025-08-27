import vertexai
from vertexai.generative_models import GenerativeModel
import env

vertexai.init(project=env.PROJECT_ID, location=env.REGION)

model = GenerativeModel("gemini-2.0-flash-lite")
responses = model.generate_content(
    "Cuentame una historia se muy emotiva y alegre ", stream=True
)

for response in responses:
    print("Block recibido:")
    print(response.text)