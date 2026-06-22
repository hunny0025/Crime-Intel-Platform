import { NextResponse } from 'next/server';

export async function POST(request: Request) {
  try {
    const { query, caseId } = await request.json();

    const apiKey = process.env.ANTHROPIC_API_KEY;
    
    const tools = [
      {
        name: "record_investigative_action",
        description: "Record a proposed investigative action to be pursued.",
        input_schema: {
          type: "object",
          properties: {
            action_type: {
              type: "string",
              enum: ["review_contradiction", "pursue_evidence_gap", "review_high_attention_entity"],
              description: "The type of action to take"
            },
            target_ref: {
              type: "string",
              description: "The ID of the target contradiction, gap, or entity"
            },
            priority_score: {
              type: "number",
              description: "Calculated priority score (0.0 to 1.0)"
            }
          },
          required: ["action_type", "target_ref", "priority_score"]
        }
      },
      {
        name: "add_case_diary_note",
        description: "Add a manual note to the case diary.",
        input_schema: {
          type: "object",
          properties: {
            record_type: {
              type: "string",
              enum: ["decision_made", "lead_status_changed"],
              description: "Type of manual diary entry"
            },
            description: {
              type: "string",
              description: "Human-readable description of the note"
            },
            actor: {
              type: "string",
              description: "The investigator or system agent name"
            },
            reasoning: {
              type: "string",
              description: "Detailed reasoning or notes"
            }
          },
          required: ["record_type", "description", "actor"]
        }
      }
    ];

    let proposed_actions: any[] = [];
    let responseText = "";

    if (apiKey) {
      // Call Anthropic Claude Messages API
      const response = await fetch('https://api.anthropic.com/v1/messages', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'x-api-key': apiKey,
          'anthropic-version': '2023-06-01'
        },
        body: JSON.stringify({
          model: 'claude-3-sonnet-20240229',
          max_tokens: 1024,
          messages: [{ role: 'user', content: query }],
          tools: tools
        })
      });

      if (response.ok) {
        const data = await response.json();
        responseText = data.content
          .filter((c: any) => c.type === 'text')
          .map((c: any) => c.text)
          .join('\n');

        const toolUses = data.content.filter((c: any) => c.type === 'tool_use');
        for (const tu of toolUses) {
          proposed_actions.push({
            tool: tu.name,
            parameters: tu.input
          });
        }
      } else {
        const errorText = await response.text();
        console.error("Anthropic API error:", errorText);
        // Fallback to mock/heuristics on API failure
        proposed_actions = parseQueryHeuristics(query);
        responseText = `API Error, fallback used.`;
      }
    } else {
      // Fallback heuristics when ANTHROPIC_API_KEY is not defined
      proposed_actions = parseQueryHeuristics(query);
      responseText = `Heuristics fallback response for query: "${query}"`;
    }

    return NextResponse.json({
      response: responseText,
      proposed_actions: proposed_actions
    });
  } catch (err: any) {
    return NextResponse.json({ error: err.message }, { status: 500 });
  }
}

function parseQueryHeuristics(query: string): any[] {
  const actions: any[] = [];
  const q = String(query).toLowerCase();

  if (q.includes("record action") || q.includes("investigative action") || q.includes("propose action")) {
    actions.push({
      tool: "record_investigative_action",
      parameters: {
        action_type: q.includes("gap") ? "pursue_evidence_gap" : "review_contradiction",
        target_ref: "00000000-0000-0000-0000-000000000000",
        priority_score: 0.85
      }
    });
  }

  if (q.includes("add diary note") || q.includes("case diary") || q.includes("add note")) {
    actions.push({
      tool: "add_case_diary_note",
      parameters: {
        record_type: "decision_made",
        description: "Manual note added via Copilot: " + query.substring(0, 100),
        actor: "investigator",
        reasoning: "Note captured from Copilot chat interface"
      }
    });
  }

  return actions;
}
