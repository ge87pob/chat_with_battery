# ElevenLabs Conversational AI Agent - Advanced Setup

## Install ConvAI CLI
```bash
npm install -g @elevenlabs/convai-cli
```

## Initialize Project
```bash
cd elevenlabs_agent
convai init
```

## Authenticate
- Option A (interactive):
```bash
convai login
```
- Option B (non-interactive, set in shell):
```bash
export ELEVENLABS_API_KEY=YOUR_KEY
./setup_convai.sh
```

## Create Agent
```bash
convai add agent "My Assistant" --template assistant
```

## Configure Agent
- Voice: choose or clone in ElevenLabs dashboard
- LLM: select Claude/GPT/Gemini or custom server
- Knowledge Base: add up to 5 items (20MB / 300k chars for non-enterprise)
- Tools: add webhooks/client tools for APIs, DBs, notifications

## Sync
```bash
convai sync
```

## Twilio Integration (optional)
1. Import and verify your Twilio number in ElevenLabs
2. Provide Twilio SID and Auth Token
3. Assign number to your agent for calls

## Troubleshooting
- If `convai` not found, ensure npm global bin is on PATH: `npm bin -g`
- Node >= 16 and npm >= 8 required
- Re-run `./setup_convai.sh` after setting `ELEVENLABS_API_KEY`
