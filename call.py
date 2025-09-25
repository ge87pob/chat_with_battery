import requests
# Submit batch calling job (POST /v1/convai/batch-calling/submit)

def submit_batch_call(phone_number: str, prompt: str):
    # Outbound call via twilio (POST /v1/convai/twilio/outbound-call)
    response = requests.post(
    "https://api.elevenlabs.io/v1/convai/twilio/outbound-call",
    headers={
        "xi-api-key": "sk_fc7f1a0ce90ac437fd5025edbf4799b25f30523955cb0ed7"
    },
    json={
        "agent_id": "agent_6601k60e1k4te7xahrmbkznjkqfr",
        "agent_phone_number_id": "phnum_6501k60m532te3wrtb3f0qbma12x",
        "to_number": phone_number,
        "conversation_initiation_client_data": {
            "conversation_config_override": {
                "agent": {
                    "prompt": {
                        "prompt": prompt
            },
                    "first_message": "Hi, how are you today? Ready for your daily summary?"
                    }
            }
        }
    },
    )
    print(response.json())