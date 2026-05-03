# Context Builder Placeholder

Future local LLM flow:

Browser asks the backend for relevant clinical, wearable, and journal context.
The backend returns a compact context packet. The browser sends that packet plus
the user prompt to a local LLM.

Do not implement prompt building, context packet generation, or LLM inference in
this task.
