import requests
# Submit batch calling job (POST /v1/convai/batch-calling/submit)

def submit_batch_call(phone_number: str, prompt: str, first_message: str | None = None):
    # Outbound call via twilio (POST /v1/convai/twilio/outbound-call)
    response = requests.post(
        "https://api.elevenlabs.io/v1/convai/twilio/outbound-call",
        headers={
            "xi-api-key": "sk_fc7f1a0ce90ac437fd5025edbf4799b25f30523955cb0ed7"
        },
        json={
            "agent_id": "agent_6601k60e1k4te7xahrmbkznjkqfr",
            "agent_phone_number_id": "phnum_2601k60mhsz4f1hvwms1m32tvy6p",
            "to_number": phone_number,
            "conversation_initiation_client_data": {
                "conversation_config_override": {
                    "agent": {
                        "prompt": {
                            "prompt": prompt
                        },
                        "first_message": first_message or "Hi, how are you today? Ready for your daily summary?"
                    }
                }
            }
        },
    )
    try:
        print(response.json())
    except Exception:
        print("Call API responded with non-JSON body, status:", response.status_code)