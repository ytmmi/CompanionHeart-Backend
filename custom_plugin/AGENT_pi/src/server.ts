/**
 * CompanionHeart Agent Sidecar — 无状态 HTTP 服务（pi-agent-core 直嵌）
 *
 * 启动: node dist/server.js --port 8300
 * 配置经环境变量注入（见 providers.ts 的 env 契约），由后端
 * app/agent/pi_sidecar/engine.py 在 PluginManager 启动时传入。
 *
 * 端点:
 *   GET  /health       健康检查（PluginManager 就绪探测）
 *   GET  /info         模型/provider/工具/能力标志
 *   POST /chat         非流式，完整回复
 *   POST /chat/stream  NDJSON 流（application/x-ndjson）
 *   POST /abort        中断进行中的请求 { request_id }
 */
import { createServer, type IncomingMessage, type ServerResponse } from "node:http";
import { randomUUID } from "node:crypto";
import { abortRequest, runChat } from "./agent-runner.ts";
import { buildProviderRuntime, type ProviderRuntime } from "./providers.ts";
import { TOOL_NAMES } from "./tools.ts";
import type { ChatRequest, HealthResponse, InfoResponse, StreamLine } from "./types.ts";

const PI_VERSION = "0.82.1"; // 与 package.json 中 pinned 的 pi-agent-core 版本一致

// ── 启动参数 ──
function parsePort(): number {
	const idx = process.argv.indexOf("--port");
	if (idx >= 0 && process.argv[idx + 1]) return Number(process.argv[idx + 1]);
	return Number(process.env.AGENT_SIDECAR_PORT ?? 8300);
}

// ── Provider 运行时（启动时构建一次） ──
let runtime: ProviderRuntime;
try {
	runtime = buildProviderRuntime();
} catch (e) {
	console.error(`[sidecar] provider 初始化失败: ${(e as Error).message}`);
	process.exit(1);
}

// ── 工具集：白名单在 tools.ts 硬编码（安全边界） ──
const TOOLS: string[] = TOOL_NAMES;

// ── HTTP 工具函数 ──
function sendJson(res: ServerResponse, status: number, body: unknown): void {
	const data = JSON.stringify(body);
	res.writeHead(status, { "Content-Type": "application/json; charset=utf-8" });
	res.end(data);
}

async function readJsonBody<T>(req: IncomingMessage): Promise<T> {
	const chunks: Buffer[] = [];
	for await (const chunk of req) chunks.push(chunk as Buffer);
	const raw = Buffer.concat(chunks).toString("utf-8");
	return JSON.parse(raw) as T;
}

function validateChatRequest(body: ChatRequest): string | null {
	if (!Array.isArray(body.messages) || body.messages.length === 0) {
		return "messages 不能为空";
	}
	const last = body.messages[body.messages.length - 1];
	if (last.role !== "user") return "messages 最后一条必须是 user";
	for (const m of body.messages) {
		if (m.role !== "user" && m.role !== "assistant") return `不支持的 role: ${m.role}`;
		if (typeof m.content !== "string" || m.content.length === 0) return "消息 content 必须为非空字符串";
	}
	if (body.tool_context) {
		if (!/^[a-z][a-z0-9_-]{1,63}$/.test(body.tool_context.role_name_en)) return "tool_context 角色不合法";
		if (!/^[A-Za-z0-9][A-Za-z0-9._:@+-]{0,255}$/.test(body.tool_context.stable_user_id)) return "tool_context 用户不合法";
		if (body.tool_context.developer_session_id && !/^[0-9a-f]{32}$/.test(body.tool_context.developer_session_id)) return "developer session 不合法";
		if (body.tool_context.client_id && !/^[A-Za-z0-9][A-Za-z0-9._:@+-]{0,255}$/.test(body.tool_context.client_id)) return "developer client 不合法";
	}
	return null;
}

// ── 路由处理 ──
async function handleChat(req: IncomingMessage, res: ServerResponse, stream: boolean): Promise<void> {
	let body: ChatRequest;
	try {
		body = await readJsonBody<ChatRequest>(req);
	} catch {
		sendJson(res, 400, { detail: "请求体不是合法 JSON" });
		return;
	}
	const invalid = validateChatRequest(body);
	if (invalid) {
		sendJson(res, 400, { detail: invalid });
		return;
	}

	const requestId = body.request_id ?? randomUUID();

	if (!stream) {
		try {
			const result = await runChat({
				runtime,
				requestId,
				systemPrompt: body.system_prompt ?? "",
				messages: body.messages,
				options: body.options,
				toolContext: body.tool_context,
			});
			res.setHeader("X-Request-Id", requestId);
			sendJson(res, 200, {
				content: result.content,
				tool_calls: result.toolCalls,
				usage: result.usage,
				stop_reason: result.stopReason,
			});
		} catch (e) {
			sendJson(res, 500, { detail: (e as Error).message });
		}
		return;
	}

	// NDJSON 流式
	res.writeHead(200, {
		"Content-Type": "application/x-ndjson; charset=utf-8",
		"Cache-Control": "no-cache",
		"X-Request-Id": requestId,
	});
	const writeLine = (line: StreamLine) => {
		res.write(JSON.stringify(line) + "\n");
	};
	// 客户端断连 → 中断 agent
	req.on("close", () => {
		if (!res.writableEnded) abortRequest(requestId);
	});

	try {
		const result = await runChat({
			runtime,
			requestId,
			systemPrompt: body.system_prompt ?? "",
			messages: body.messages,
			options: body.options,
			toolContext: body.tool_context,
			onLine: writeLine,
		});
		writeLine({
			type: "done",
			content_full: result.content,
			usage: result.usage,
			stop_reason: result.stopReason,
		});
	} catch (e) {
		writeLine({ type: "error", message: (e as Error).message });
	} finally {
		res.end();
	}
}

// ── 服务器 ──
const server = createServer(async (req, res) => {
	const url = req.url ?? "/";
	try {
		if (req.method === "GET" && url === "/health") {
			const body: HealthResponse = {
				status: "ok",
				pi_version: PI_VERSION,
				provider: runtime.providerId,
				model: runtime.model.id,
			};
			sendJson(res, 200, body);
		} else if (req.method === "GET" && url === "/info") {
			const body: InfoResponse = {
				pi_version: PI_VERSION,
				provider: runtime.providerId,
				model: runtime.model.id,
				tools: TOOLS,
				capabilities: { temperature: true, max_tokens: true, top_p: false, streaming: true },
			};
			sendJson(res, 200, body);
		} else if (req.method === "POST" && url === "/chat") {
			await handleChat(req, res, false);
		} else if (req.method === "POST" && url === "/chat/stream") {
			await handleChat(req, res, true);
		} else if (req.method === "POST" && url === "/abort") {
			const body = await readJsonBody<{ request_id?: string }>(req).catch(() => ({}) as { request_id?: string });
			if (!body.request_id) {
				sendJson(res, 400, { detail: "缺少 request_id" });
			} else {
				sendJson(res, 200, { ok: abortRequest(body.request_id) });
			}
		} else {
			sendJson(res, 404, { detail: "Not Found" });
		}
	} catch (e) {
		if (!res.headersSent) sendJson(res, 500, { detail: (e as Error).message });
		else if (!res.writableEnded) res.end();
	}
});

const port = parsePort();
server.listen(port, "127.0.0.1", () => {
	console.log(`[sidecar] CompanionHeart agent sidecar 已启动: http://127.0.0.1:${port} (provider=${runtime.providerId}, model=${runtime.model.id})`);
});

// ── 优雅退出 ──
for (const sig of ["SIGINT", "SIGTERM"] as const) {
	process.on(sig, () => {
		server.close(() => process.exit(0));
		// 兜底：3s 未关完强制退出
		setTimeout(() => process.exit(0), 3000).unref();
	});
}
