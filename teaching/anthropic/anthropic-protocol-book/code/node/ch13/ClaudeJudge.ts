/**
 * Chapter 13: Claude-as-Judge — RAG output quality evaluation (TypeScript).
 *
 * Uses Claude to evaluate RAG-generated answers across multiple dimensions:
 *   - Faithfulness: Is the answer grounded in the provided context?
 *   - Relevance: Does the answer address the user's query?
 *   - Completeness: Does the answer cover all key information in the context?
 *
 * Each method returns a structured object with a score (0.0-1.0) and
 * detailed reasoning.
 */

// ---------------------------------------------------------------------------
// Evaluation prompt templates
// ---------------------------------------------------------------------------

const FAITHFULNESS_PROMPT = `\
You are an expert evaluator of RAG (Retrieval-Augmented Generation) systems.
Your task is to evaluate whether an answer is FAITHFUL to the provided context.

A faithful answer:
- Contains ONLY claims that are directly supported by the context
- Does NOT add information not present in the context
- Does NOT contradict the context
- Correctly represents the context's information

Score the faithfulness on a scale of 0.0 to 1.0:
  1.0: Every claim is directly supported by the context, no hallucinations
  0.7-0.9: Mostly faithful, minor unsupported details
  0.4-0.6: Mixed, some claims supported, some not
  0.1-0.3: Mostly unfaithful, significant hallucinations
  0.0: Completely contradicts the context or has no relation to it

---

CONTEXT:
{context}

---

ANSWER:
{answer}

---

Output your evaluation in valid JSON format:
{
  "score": <float between 0.0 and 1.0>,
  "reasoning": "<brief explanation of the score>",
  "supported_claims": ["<claim 1>", "<claim 2>"],
  "unsupported_claims": ["<claim 1>", "<claim 2>"]
}`;

const RELEVANCE_PROMPT = `\
You are an expert evaluator of RAG (Retrieval-Augmented Generation) systems.
Your task is to evaluate whether an answer is RELEVANT to the user's query.

A relevant answer:
- Directly addresses the user's question
- Provides useful information related to the query
- Does NOT wander off-topic
- Does NOT include irrelevant details

Score the relevance on a scale of 0.0 to 1.0:
  1.0: Perfectly addresses the query, every part of the answer is relevant
  0.7-0.9: Mostly relevant, minor off-topic elements
  0.4-0.6: Partially relevant, significant off-topic content
  0.1-0.3: Mostly irrelevant
  0.0: Completely unrelated to the query

---

QUERY:
{query}

---

ANSWER:
{answer}

---

Output your evaluation in valid JSON format:
{
  "score": <float between 0.0 and 1.0>,
  "reasoning": "<brief explanation of the score>",
  "relevant_parts": ["<relevant part 1>", "<relevant part 2>"],
  "irrelevant_parts": ["<irrelevant part 1>"]
}`;

const COMPLETENESS_PROMPT = `\
You are an expert evaluator of RAG (Retrieval-Augmented Generation) systems.
Your task is to evaluate whether an answer is COMPLETE with respect to the context.

A complete answer:
- Covers ALL key information present in the context that relates to the query
- Does NOT miss important facts, data points, or arguments from the context
- Provides a thorough response without significant omissions

Score the completeness on a scale of 0.0 to 1.0:
  1.0: Covers all key information from the context, no omissions
  0.7-0.9: Covers most key information, minor omissions
  0.4-0.6: Covers some key information, significant omissions
  0.1-0.3: Covers little key information from the context
  0.0: Misses all key information from the context

---

CONTEXT:
{context}

---

ANSWER:
{answer}

---

Output your evaluation in valid JSON format:
{
  "score": <float between 0.0 and 1.0>,
  "reasoning": "<brief explanation of the score>",
  "covered_points": ["<point 1>", "<point 2>"],
  "missed_points": ["<missed point 1>", "<missed point 2>"]
}`;

const COMPREHENSIVE_PROMPT = `\
You are an expert evaluator of RAG (Retrieval-Augmented Generation) systems.
Your task is to perform a COMPREHENSIVE evaluation of a RAG-generated answer.

Evaluate on THREE dimensions:

1. FAITHFULNESS: Is every claim grounded in the provided context? (1.0 = all claims supported)
2. RELEVANCE: Does the answer directly address the query? (1.0 = perfectly on-topic)
3. COMPLETENESS: Does the answer cover all key information in the context? (1.0 = no omissions)

---

QUERY:
{query}

---

CONTEXT:
{context}

---

ANSWER:
{answer}

---

Output your evaluation in valid JSON format:
{
  "faithfulness": {
    "score": <float 0.0-1.0>,
    "reasoning": "<brief explanation>"
  },
  "relevance": {
    "score": <float 0.0-1.0>,
    "reasoning": "<brief explanation>"
  },
  "completeness": {
    "score": <float 0.0-1.0>,
    "reasoning": "<brief explanation>"
  },
  "overall_score": <float 0.0-1.0, average of the three scores>,
  "overall_assessment": "<1-2 sentence summary of the quality>"
}`;

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface SingleEvaluation {
  score: number;
  reasoning: string;
  [key: string]: unknown;
}

export interface ComprehensiveEvaluation {
  faithfulness: SingleEvaluation;
  relevance: SingleEvaluation;
  completeness: SingleEvaluation;
  overall_score: number;
  overall_assessment: string;
}

export interface TestCase {
  query: string;
  answer: string;
  context: string;
}

export interface BatchResult extends ComprehensiveEvaluation {
  test_case: TestCase;
}

// ---------------------------------------------------------------------------
// Judge configuration
// ---------------------------------------------------------------------------

export interface JudgeConfig {
  apiKey: string;
  baseUrl?: string;
  apiVersion?: string;
  judgeModel?: string;
  maxTokens?: number;
  temperature?: number;
}

const DEFAULT_CONFIG: Required<Omit<JudgeConfig, "apiKey">> = {
  baseUrl: "https://api.anthropic.com/v1/messages",
  apiVersion: "2023-06-01",
  judgeModel: "claude-sonnet-4-20250514",
  maxTokens: 512,
  temperature: 0.0,
};

// ---------------------------------------------------------------------------
// ClaudeJudge
// ---------------------------------------------------------------------------

export class ClaudeJudge {
  private readonly config: Required<JudgeConfig>;

  constructor(config: JudgeConfig) {
    if (!config.apiKey) {
      throw new Error(
        "apiKey must be provided or set via ANTHROPIC_API_KEY environment variable",
      );
    }
    this.config = { ...DEFAULT_CONFIG, ...config };
  }

  // ----------------------------------------------------------------
  // Single-dimension evaluations
  // ----------------------------------------------------------------

  async evaluateFaithfulness(
    answer: string,
    context: string,
  ): Promise<SingleEvaluation> {
    const prompt = FAITHFULNESS_PROMPT.replace("{context}", context).replace(
      "{answer}",
      answer,
    );
    return this.callClaude(prompt) as Promise<SingleEvaluation>;
  }

  async evaluateRelevance(
    answer: string,
    query: string,
  ): Promise<SingleEvaluation> {
    const prompt = RELEVANCE_PROMPT.replace("{query}", query).replace(
      "{answer}",
      answer,
    );
    return this.callClaude(prompt) as Promise<SingleEvaluation>;
  }

  async evaluateCompleteness(
    answer: string,
    context: string,
  ): Promise<SingleEvaluation> {
    const prompt = COMPLETENESS_PROMPT.replace("{context}", context).replace(
      "{answer}",
      answer,
    );
    return this.callClaude(prompt) as Promise<SingleEvaluation>;
  }

  // ----------------------------------------------------------------
  // Comprehensive evaluation
  // ----------------------------------------------------------------

  async comprehensiveEval(
    query: string,
    answer: string,
    context: string,
  ): Promise<ComprehensiveEvaluation> {
    const prompt = COMPREHENSIVE_PROMPT.replace("{query}", query)
      .replace("{context}", context)
      .replace("{answer}", answer);
    return this.callClaude(prompt) as Promise<ComprehensiveEvaluation>;
  }

  // ----------------------------------------------------------------
  // Batch evaluation
  // ----------------------------------------------------------------

  async evaluateBatch(
    testCases: readonly TestCase[],
  ): Promise<BatchResult[]> {
    const results: BatchResult[] = [];
    for (const tc of testCases) {
      const result = await this.comprehensiveEval(
        tc.query,
        tc.answer,
        tc.context,
      );
      results.push({ ...result, test_case: tc });
    }
    return results;
  }

  // ----------------------------------------------------------------
  // Internal: Claude API call
  // ----------------------------------------------------------------

  private async callClaude(prompt: string): Promise<Record<string, unknown>> {
    const cfg = this.config;

    const resp = await fetch(cfg.baseUrl, {
      method: "POST",
      headers: {
        "x-api-key": cfg.apiKey,
        "anthropic-version": cfg.apiVersion,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        model: cfg.judgeModel,
        max_tokens: cfg.maxTokens,
        temperature: cfg.temperature,
        messages: [
          {
            role: "user",
            content: [{ type: "text", text: prompt }],
          },
        ],
      }),
    });

    if (!resp.ok) throw new Error(`Claude API error: ${resp.status}`);
    const data = (await resp.json()) as {
      content: { type: string; text: string }[];
    };

    let text = "";
    for (const block of data.content) {
      if (block.type === "text") text += block.text;
    }

    return parseJsonResponse(text);
  }
}

// ---------------------------------------------------------------------------
// JSON response parsing
// ---------------------------------------------------------------------------

export function parseJsonResponse(text: string): Record<string, unknown> {
  // Try to extract JSON from markdown code block
  const codeBlockMatch = text.match(/```(?:json)?\s*\n?(.*?)\n?```/s);
  const jsonText = codeBlockMatch ? codeBlockMatch[1]!.trim() : text;

  try {
    return JSON.parse(jsonText) as Record<string, unknown>;
  } catch {
    // Try to find a JSON object in the text
    const objectMatch = text.match(/\{.*\}/s);
    if (objectMatch) {
      try {
        return JSON.parse(objectMatch[0]) as Record<string, unknown>;
      } catch {
        // fall through
      }
    }
  }

  return {
    score: 0.0,
    reasoning: `Failed to parse JSON from response: ${text.slice(0, 200)}`,
  };
}

// ---------------------------------------------------------------------------
// Retrieval quality metrics (no LLM needed)
// ---------------------------------------------------------------------------

export interface RetrievalMetrics {
  recall_at_k: number;
  precision_at_k: number;
  mrr: number;
  k: number;
}

export function computeRetrievalMetrics(
  retrievedIds: readonly string[],
  relevantIds: ReadonlySet<string>,
  k?: number,
): RetrievalMetrics {
  const kVal = k ?? retrievedIds.length;
  const retrievedAtK = retrievedIds.slice(0, kVal);
  const hitsAtK = retrievedAtK.filter((id) => relevantIds.has(id));

  const recall = hitsAtK.length / Math.max(relevantIds.size, 1);
  const precision = hitsAtK.length / Math.max(retrievedAtK.length, 1);

  let mrr = 0.0;
  for (let i = 0; i < retrievedIds.length; i++) {
    if (relevantIds.has(retrievedIds[i]!)) {
      mrr = 1.0 / (i + 1);
      break;
    }
  }

  return {
    recall_at_k: recall,
    precision_at_k: precision,
    mrr,
    k: kVal,
  };
}
