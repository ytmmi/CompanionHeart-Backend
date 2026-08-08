/**
 * Agent 运行器 — 每请求构建一次性 Agent（无状态，用完即弃）
 *
 * 记忆分离要点：sidecar 不引入 pi 的 harness/session/compaction，
 * 历史由 Python 侧每轮以 role 化 messages 传入 initialState.messages。
 */
import { Agent, type AgentMessage } from "@earendil-works/pi-agent-core";
import type { Context, Model, SimpleStreamOptions } from "@earendil-works/pi-ai";
import type { ProviderRuntime } from "./providers.ts";
import { createPetTools } from "./tools.ts";
import type { ChatMessage, ChatOptions, StreamLine, ToolCallInfo, ToolRuntimeContext } from "./types.ts";

/** 进行中请求注册表：request_id → AbortController（/abort 用） */
export const activeRequests = new Map<string, AbortController>();

/** Python 传入的 role 化历史 → pi AgentMessage[]（最后一条 user 由 prompt() 单独发送） */
function toAgentMessages(history: ChatMessage[], model: Model<any>): AgentMessage[] {
	let ts = 1;
	return history.map((m) => {
		if (m.role === "user") {
			return { role: "user", content: m.content, timestamp: ts++ } as AgentMessage;
		}
		// 历史 assistant 消息：补齐 provider 元数据（不参与计费/展示，仅满足消息结构）
		return {
			role: "assistant",
			content: [{ type: "text", text: m.content }],
			timestamp: ts++,
			api: model.api,
			provider: model.provider,
			model: model.id,
			usage: {
				input: 0,
				output: 0,
				cacheRead: 0,
				cacheWrite: 0,
				cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 },
			},
			stopReason: "stop",
		} as unknown as AgentMessage;
	});
}

export interface RunChatParams {
	runtime: ProviderRuntime;
	requestId: string;
	systemPrompt: string;
	/** 完整历史，最后一条必须是 user（本轮输入） */
	messages: ChatMessage[];
	options?: ChatOptions;
	toolContext?: ToolRuntimeContext;
	/** 每条流式行的回调（NDJSON 输出）；非流式调用传 undefined */
	onLine?: (line: StreamLine) => void | Promise<void>;
}

export interface RunChatResult {
	content: string;
	toolCalls: ToolCallInfo[];
	usage: { input: number; output: number };
	stopReason: string;
}

export async function runChat(params: RunChatParams): Promise<RunChatResult> {
	const { runtime, requestId, systemPrompt, messages, options, toolContext, onLine } = params;

	const last = messages[messages.length - 1];
	if (!last || last.role !== "user") {
		throw new Error("messages 最后一条必须是 user（本轮输入）");
	}
	const history = messages.slice(0, -1);

	const sampling: Partial<SimpleStreamOptions> = {};
	if (options?.temperature !== undefined) sampling.temperature = options.temperature;
	if (options?.max_tokens !== undefined) sampling.maxTokens = options.max_tokens;

	const agent = new Agent({
		initialState: {
			systemPrompt,
			model: runtime.model,
			tools: createPetTools(toolContext),
			messages: toAgentMessages(history, runtime.model),
		},
		streamFn: (model: Model<any>, context: Context, opts?: SimpleStreamOptions) =>
			runtime.models.streamSimple(model, context, {
				...opts,
				...sampling,
				apiKey: runtime.apiKey,
			}),
	});

	const controller = new AbortController();
	activeRequests.set(requestId, controller);
	controller.signal.addEventListener("abort", () => agent.abort(), { once: true });

	let content = "";
	const toolCalls: ToolCallInfo[] = [];
	const toolArgsById = new Map<string, unknown>();
	const usage = { input: 0, output: 0 };
	let stopReason = "stop";

	agent.subscribe(async (event) => {
		switch (event.type) {
			case "message_update": {
				const e = event.assistantMessageEvent;
				if (e.type === "text_delta") {
					content += e.delta;
					await onLine?.({ type: "delta", content: e.delta });
				} else if (e.type === "thinking_delta") {
					await onLine?.({ type: "thinking", content: e.delta });
				}
				break;
			}
			case "message_end": {
				const msg = event.message as any;
				if (msg.role === "assistant") {
					usage.input += msg.usage?.input ?? 0;
					usage.output += msg.usage?.output ?? 0;
					if (msg.stopReason) stopReason = msg.stopReason;
				}
				break;
			}
			case "tool_execution_start":
				toolArgsById.set(event.toolCallId, event.args);
				await onLine?.({ type: "tool", phase: "start", name: event.toolName, args: event.args });
				break;
			case "tool_execution_end": {
				const args = toolArgsById.get(event.toolCallId);
				toolCalls.push({ name: event.toolName, args, is_error: event.isError });
				await onLine?.({ type: "tool", phase: "end", name: event.toolName, is_error: event.isError });
				break;
			}
		}
	});

	try {
		await agent.prompt(last.content);
	} finally {
		activeRequests.delete(requestId);
	}

	// abort / 上游错误在最终 assistant 消息上体现为 stopReason + errorMessage
	const finalMsg = agent.state.messages[agent.state.messages.length - 1] as any;
	if (finalMsg?.stopReason) stopReason = finalMsg.stopReason;
	if (stopReason === "error") {
		throw new Error(finalMsg?.errorMessage ?? "LLM 请求失败");
	}

	return { content, toolCalls, usage, stopReason };
}

export function abortRequest(requestId: string): boolean {
	const controller = activeRequests.get(requestId);
	if (!controller) return false;
	controller.abort();
	return true;
}
