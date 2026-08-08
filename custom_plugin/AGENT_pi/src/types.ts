/**
 * sidecar 内部契约类型 — 与 Python 侧 app/agent/pi_sidecar/events.py 的常量对齐
 *
 * HTTP API:
 *   GET  /health       → HealthResponse
 *   GET  /info         → InfoResponse
 *   POST /chat         → ChatResponse（完整回复）
 *   POST /chat/stream  → NDJSON 流（StreamLine 每行一条）
 *   POST /abort        → { ok: boolean }
 */

/** 请求消息（Python 侧 role 化历史注入的载荷） */
export interface ChatMessage {
	role: "user" | "assistant";
	content: string;
}

/** 采样参数（top_p 不被 pi-ai 支持，收到即忽略并在 /info 能力标志中声明） */
export interface ChatOptions {
	temperature?: number;
	max_tokens?: number;
}

export interface ChatRequest {
	/** 请求标识，用于 /abort 定位；缺省由 sidecar 生成并在响应头 X-Request-Id 返回 */
	request_id?: string;
	system_prompt?: string;
	/** 完整对话历史（含本轮用户消息，最后一条必须是 user） */
	messages: ChatMessage[];
	options?: ChatOptions;
	/** 后端生成的受控工具上下文；不接受生活记忆或完整聊天历史 */
	tool_context?: ToolRuntimeContext;
}

export interface ToolRuntimeContext {
	role_name_en: string;
	stable_user_id: string;
	developer_session_id?: string;
	client_id?: string;
}

export interface ToolCallInfo {
	name: string;
	args: unknown;
	is_error: boolean;
}

export interface ChatResponse {
	content: string;
	tool_calls: ToolCallInfo[];
	usage: { input: number; output: number };
	stop_reason: string;
}

/** NDJSON 流式行类型 */
export type StreamLine =
	| { type: "delta"; content: string }
	| { type: "thinking"; content: string }
	| { type: "tool"; phase: "start" | "end"; name: string; args?: unknown; is_error?: boolean }
	| { type: "done"; content_full: string; usage: { input: number; output: number }; stop_reason: string }
	| { type: "error"; message: string };

export interface HealthResponse {
	status: "ok";
	pi_version: string;
	provider: string;
	model: string;
}

export interface InfoResponse {
	pi_version: string;
	provider: string;
	model: string;
	tools: string[];
	capabilities: {
		temperature: boolean;
		max_tokens: boolean;
		top_p: boolean;
		streaming: boolean;
	};
}
