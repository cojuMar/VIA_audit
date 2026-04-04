export interface Conversation {
  id: string;
  title: string;
  user_identifier: string | null;
  status: 'active' | 'archived';
  message_count: number;
  total_input_tokens: number;
  total_output_tokens: number;
  created_at: string;
  updated_at: string;
}

export interface Message {
  id: string;
  conversation_id: string;
  role: 'user' | 'assistant' | 'tool_result';
  content: string;
  tool_calls: string[];
  input_tokens: number | null;
  output_tokens: number | null;
  latency_ms: number | null;
  created_at: string;
}

export interface ChatResponse {
  conversation_id: string;
  message_id: string;
  content: string;
  tool_calls_made: string[];
  input_tokens: number;
  output_tokens: number;
  latency_ms: number;
}

export interface ReportRequest {
  report_type: string;
  title: string | null;
  natural_language_request: string;
  conversation_id: string | null;
}

export interface Report {
  id: string;
  report_type: string;
  title: string;
  content: string;
  format: string;
  model_used: string;
  generation_time_ms: number;
  generated_at: string;
}

export interface AgentTool {
  name: string;
  description: string;
}

export interface ConversationStats {
  total_conversations: number;
  total_messages: number;
  total_tool_calls: number;
  avg_tools_per_message: number;
  most_used_tools: Array<{ tool_name: string; count: number }>;
  feedback_avg_rating: number | null;
}

export interface FeedbackCreate {
  message_id: string;
  conversation_id: string;
  rating: number;
  feedback_type?: string;
  comment?: string;
}
