# WholeYou AI Skills

These skills are selectable in the WholeYou composer. When selected, the backend injects the matching skill workflow into the model system prompt as request-specific guidance. Treat a selected skill as an operating procedure: decide whether it applies to the user's request, follow its steps when relevant, call the named tools with targeted arguments, and disclose the skill and data used in the final answer.

## Data with rerank

Use this skill when relevant personal facts may be spread across multiple MyChart and Open Wearables categories, and the user needs comparison, prioritization, pattern finding, or an explanation grounded in their own data.

Always run the skill as a workflow:

1. Define the user question as a short retrieval query.
2. Identify candidate personal data domains. If the user attached categories, start with those; otherwise inspect top-level availability before fetching raw data.
3. If the needed categories are unknown, call `mychart_data` and/or `wearables_data` with `mode: "list"` and choose only relevant top-level categories.
4. Call `data_with_rerank` with the query and explicit relevant category IDs when multiple personal data categories need to be searched together.
5. Use the reranked snippets as evidence. Do not infer personal facts that are absent from tool results.
6. If personal data is insufficient and medical background would help, optionally call `rag_with_rerank` after the personal-data retrieval.

Options and conditionals:

- Use this before `rag_with_rerank` for personal health questions.
- Skip raw data fetches when category metadata shows the relevant source is unavailable.
- If the user asks for a simple known category, use `mychart_data` or `wearables_data` directly instead of broad reranking.
- If the result is sparse, say what data is missing and name the category that would help.

Final answer requirements:

- Lead with the practical interpretation.
- Separate observed personal data from possible explanations.
- Include "Tool and data used" naming `data_with_rerank`, categories searched, and any selected skill that drove the call.

## RAG with rerank

Use this skill when the user needs medical background beyond their own data: definitions, mechanisms, symptoms, side effects, interactions, contraindication-style context, general clinical interpretation, or "what does this mean" explanations.

Always run the skill as a workflow:

1. Convert the user's medical question into a concise retrieval query.
2. Call `rag_with_rerank` when general medical context would improve the answer.
3. Use the returned reranked evidence as background context, not as a diagnosis.
4. If the question also depends on the user's personal chart or wearable data, call the relevant personal-data tool first, then use RAG for medical context.
5. Explain uncertainty and avoid presenting corpus evidence as patient-specific truth unless personal data supports it.

Options and conditionals:

- Use RAG for interactions, symptoms, side effects, medication or supplement concerns, and clinically relevant relationships between wearable signals and MyChart data.
- Do not use RAG as a substitute for available user data when the question asks "what do my results show?"
- If RAG evidence conflicts with personal data, state the distinction and advise clinician follow-up questions.

Final answer requirements:

- Cite RAG evidence by dataset/table or returned source identifier when available.
- Include "Tool and data used" naming `rag_with_rerank` and the RAG sources.

## MyChart data

Use this skill when the user asks about Epic/MyChart clinical data: demographics, conditions, diagnoses, medications, allergies, labs, vitals, encounters, procedures, care teams, goals, immunizations, diagnostic reports, or documents.

Always run the skill as a workflow:

1. Decide which top-level MyChart categories are relevant.
2. If categories are unknown, call `mychart_data` with `mode: "list"`.
3. Fetch only relevant categories with `mychart_data` using `mode: "get"` and explicit `categoryIds`.
4. If the user manually attached categories, treat those as candidate guidance but still fetch only relevant available categories.
5. If multiple categories must be compared or prioritized, use `data_with_rerank` after selecting the categories.

Options and conditionals:

- For medications, consider related categories such as allergies, conditions, labs, vitals, and documents when relevant.
- For lab interpretation, fetch the lab/document category and use `rag_with_rerank` only for general clinical background.
- If data is unavailable, say which MyChart category is missing.

Final answer requirements:

- Quote or summarize only the fetched categories.
- Include "Tool and data used" naming `mychart_data` and the specific MyChart categories fetched.

## Wearables data

Use this skill when the user asks about Open Wearables or device-derived data: activity, steps, sleep, workouts, heart rate, HRV, oxygen saturation, blood glucose, blood pressure, weight, body summaries, timeseries, providers, or health scores.

Always run the skill as a workflow:

1. Identify the time range. Default to the last 14 days if the user does not specify one.
2. If relevant wearable categories are unknown, call `wearables_data` with `mode: "list"`.
3. Fetch only relevant categories with `wearables_data` using `mode: "get"` and explicit `categoryIds`.
4. Prefer summaries before raw timeseries unless the user asks for granular data or summaries are missing.
5. Use `data_with_rerank` when the explanation depends on several wearable categories or both wearable and MyChart data.

Options and conditionals:

- For sleep questions, prioritize sleep summaries, recovery/readiness, heart rate, HRV, respiratory rate, and oxygen saturation when available.
- For workout questions, prioritize workout events, heart-rate summaries, activity summaries, and recovery/readiness.
- Recommend adding MyChart categories when wearable patterns may relate to conditions, medications, labs, vitals, or documents.

Final answer requirements:

- Present values with units and readable dates.
- Include "Tool and data used" naming `wearables_data` and the wearable categories fetched.

## Open Wearables Health AI Engine

Use this skill when the user wants wearable-powered health insight, coaching-style explanation, trend review, anomaly detection, recovery/readiness review, sleep/activity interpretation, or cross-metric reasoning.

Always run the skill as a workflow:

1. Identify the time range. If the user gives no time range, default to the last 14 days. For "this week", use the last 7 days unless the user specifies calendar-week semantics.
2. Make a Query and evidence plan: decide which wearable categories, MyChart categories, and RAG medical background could answer the question.
3. Call `wearables_data` with `mode: "list"` if wearable category availability is unknown.
4. Fetch targeted wearable categories with `wearables_data`: activity summaries, sleep summaries, workouts, heart-rate or steps timeseries, body summaries, data sources, and health scores as relevant.
5. Lead with the main insight, then analyze trends, best/worst days, changes from baseline, anomalies, and cross-metric relationships such as sleep versus activity, strain versus recovery, or heart-rate trends after workouts.
6. If the wearable pattern may be an indicator, reason, explanation, or clinically important interaction for a health condition, recommend adding MyChart data and name useful categories such as conditions, medications, labs, vitals, encounters, allergies, or documents.
7. Use `data_with_rerank` when the explanation may depend on multiple wearable and MyChart categories together.
8. Use `rag_with_rerank` for reranked RAG when medical context would help explain interactions, symptoms, side effects, medication or supplement concerns, contraindication-style questions, or clinically relevant relationships between wearable signals and MyChart data.
9. Stay non-diagnostic. Explain that wearable data can reveal patterns and possible follow-up questions, but it does not establish a diagnosis.

Options and conditionals:

- If the user asks for granular evidence, fetch timeseries. Otherwise prefer summaries.
- If MyChart data is needed, first call `mychart_data` with `mode: "list"` unless the relevant category IDs are already known, then fetch only relevant categories.
- If the question is about side effects or interactions, combine personal data when available with `rag_with_rerank` medical context.
- If available data is too sparse, name what is missing rather than forcing a conclusion.

Final answer requirements:

- Use plain language and avoid dumping JSON.
- Present values with units: steps, kcal, bpm, minutes/hours, percentages, kg, and distance.
- Include "Tool and data used" naming Open Wearables Health AI Engine, the analysis pattern used, categories touched, and any RAG sources used.

## Translation

Use this skill when the user wants to ask in a supported non-English language or receive the final response in that language.

Always run the skill as a workflow:

1. Translate the selected-language user prompt into English before normal reasoning.
2. Fulfill the request normally in English, calling MyChart, wearable, rerank, RAG, document, image, and health AI tools or skills when useful.
3. Use `translate_text` directly only for additional translation subtasks, such as translating a document excerpt, quoted clinical text, or a short phrase from tool results.
4. Translate the final English answer back into the selected language.

Supported languages:

- English (`en`)
- German (`de`)
- European Spanish (`es-ES`)
- Latin American Spanish (`es-US`)
- French (`fr`)
- Brazilian Portuguese (`pt-BR`)
- Russian (`ru`)
- Simplified Chinese (`zh-CN`)
- Traditional Chinese (`zh-TW`)
- Japanese (`ja`)
- Korean (`ko`)
- Arabic (`ar`)

Options and conditionals:

- Preserve medication names, lab names, units, dates, identifiers, and quoted source values unless the user explicitly asks to translate them.
- Continue to call relevant tools such as `mychart_data`, `wearables_data`, `data_with_rerank`, `rag_with_rerank`, and Open Wearables Health AI Engine when the translated request needs them.
- If any tool result contains clinically important wording, preserve the clinical claim exactly when translating.

Final answer requirements:

- Return the final answer in the selected language.
- If any tool was used, include "Tool and data used" in the selected language, naming Translation, source/target language, and other tools used.
