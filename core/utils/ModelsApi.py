from google.genai import Client
from dotenv import load_dotenv
import os
load_dotenv()
class Model:
    @staticmethod
    def gemini(prompt,modelname="gemini-2.0-flash", temperature=0.2):
        try:
            client = Client(api_key=os.getenv('GEMINI_API_KEY'))
            response = client.models.generate_content(
                model=modelname,
                contents=prompt)
            return response.text
        except Exception as e:
            raise Exception(f"Error in gemini method: {str(e)}")
    def gpt(self, modelname, prompt, temperature=0.2):
        try:
            pass
        except Exception as e:
            raise Exception(f"Error in gpt method: {str(e)}")