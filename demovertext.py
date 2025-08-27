import vertexai
from vertexai.generative_models import GenerativeModel
import env

PROJECT_ID = env.PROJECT_ID
REGION = env.REGION

vertexai.init(project=PROJECT_ID, location=REGION)

# model = GenerativeModel("gemini-2.0-flash-001")
model = GenerativeModel("gemini-2.0-flash-lite")

response = model.generate_content(
    "Saluda!"
)

print(response.text)
#pip install google-cloud-aiplatform